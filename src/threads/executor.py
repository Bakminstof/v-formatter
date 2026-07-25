from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import suppress
from multiprocessing import cpu_count
from queue import Queue, ShutDown
from threading import Event, Lock, Thread
from typing import Callable

from loguru import logger
from PySide6.QtCore import QCoreApplication, QEvent, QObject

from core.mixins import ReprMixin
from processes import ManagedProcessProtocol, ProcessResult, ProcessState

MANAGED_PROCESS_FINISHED_EVENT_TYPE = QEvent.Type(QEvent.Type.User + 1)
DEFAULT_MAX_PROCESS_WORKERS = min(cpu_count() * 2, 32)


class ProcessFinishedEvent(QEvent):
    def __init__(
        self,
        title: str | None,
        result: ProcessResult | None | Exception,
        meta: dict | None = None,
    ) -> None:
        super().__init__(MANAGED_PROCESS_FINISHED_EVENT_TYPE)
        self.title = title
        self.result = result
        self.meta = meta or {}


class ProcessQueueExecutorThread(Thread, ReprMixin):
    def __init__(
        self,
        gui_receiver: QObject,
        queue: Queue[
            tuple[
                ManagedProcessProtocol | None,
                list[Callable[[ManagedProcessProtocol], None]] | None,
            ]
        ],
    ) -> None:
        super().__init__(daemon=True)

        self.__queue = queue
        self.__gui_receiver = gui_receiver

        self.__process: ManagedProcessProtocol | None = None
        self.__process_callbacks: list[Callable[[ManagedProcessProtocol], None]] = []

        self.__lock = Lock()
        self.__manager = ProcessManagerThread()
        self.__started = False

    @property
    def process(self) -> ManagedProcessProtocol | None:
        return self.__process or None

    def put(
        self,
        p: ManagedProcessProtocol,
        on_finish: (
            Callable[[ManagedProcessProtocol], None]
            | list[Callable[[ManagedProcessProtocol], None]]
            | None
        ) = None,
    ) -> None:
        if self.__queue.is_shutdown:
            return

        if on_finish is None:
            callbacks = []
        elif callable(on_finish):
            callbacks = [on_finish]
        else:
            callbacks = on_finish

        callbacks: list[Callable[[ManagedProcessProtocol], None]]

        self.__queue.put((p, callbacks))

    def run(self) -> None:
        logger.debug("[{}] Start", self)

        self.__started = True
        self.__manager.start()

        while self.__started:
            try:
                p, callbacks = self.__queue.get()
            except ShutDown:
                break

            if p is None:
                logger.debug("[{}] Received stop flag, stopping", self)
                self.__queue.task_done()
                break

            self.__process = p
            self.__process_callbacks = callbacks or []

            try:
                res = p.run()
            except Exception as e:
                logger.error("[{}]: {}", p.title, str(e))
                res = e
            finally:
                self.__queue.task_done()

            self.__invoke_callbacks(self.__process_callbacks, p)

            event = ProcessFinishedEvent(p.title, res, p.metadata)
            QCoreApplication.postEvent(self.__gui_receiver, event)

        logger.debug("[{}] Finished", self)

    def stop(self) -> None:
        logger.debug("[{}] Stopping", self)

        self.stop_current_process(block=True)
        self.__stop_manager()
        self.__stop_queue()

        logger.debug("[{}] Stopped", self)

    def __stop_manager(self) -> None:
        with self.__lock:
            if self.__manager.is_alive():
                self.__manager.stop()

    def __stop_queue(self) -> None:
        if self.__queue.is_shutdown:
            return

        self.__queue.put((None, None))
        self.__queue.shutdown(immediate=True)

    def dispose(self) -> None:
        self.__process = None

    @property
    def running(self) -> bool:
        if not self.__process:
            return False

        return self.__process.result.state is ProcessState.RUNNING

    def __stop_process(self) -> None:
        if not self.__process:
            return

        with self.__lock:
            if not self.__process.result.state is ProcessState.RUNNING:
                return

            title = self.__process.title if self.process else None

            logger.debug(
                "[{}] Stopping process: {!r}",
                self,
                title,
            )

            self.__process.stop()

            logger.debug(
                "[{}] Stopped process: {!r}",
                self,
                title,
            )

    def stop_current_process(self, block: bool = False) -> None:
        if block:
            self.__stop_process()
        else:
            self.__manager.put(self.__stop_process)

    def add_on_finish_callbacks(
        self,
        *callbacks: Callable[[ManagedProcessProtocol], None],
    ) -> None:
        with self.__lock:
            self.__process_callbacks.extend(self.__normalize_callbacks(*callbacks))

    @staticmethod
    def __normalize_callbacks(
        *on_finish_callbacks: Callable[[ManagedProcessProtocol], None],
    ) -> list[Callable[[ManagedProcessProtocol], None]]:
        return [i for i in on_finish_callbacks if callable(i)]

    def __invoke_callbacks(
        self,
        callbacks: list[Callable[[ManagedProcessProtocol], None]],
        process: ManagedProcessProtocol,
    ) -> None:
        for cb in callbacks:
            cb_name = getattr(cb, "__qualname__", None) or getattr(cb, "__name__", str(cb))

            logger.debug("[{}] Invoke callback: {}", self, cb_name)

            try:
                cb(process)
            except Exception as e:
                logger.exception("[{}] Callback error: {}", self, str(e), exc_info=e)


class ProcessPoolExecutorThread(Thread, ReprMixin):
    def __init__(
        self,
        gui_receiver: QObject,
        queue: Queue[
            tuple[
                ManagedProcessProtocol | None,
                list[Callable[[ManagedProcessProtocol], None]] | None,
            ]
        ],
        max_workers: int = DEFAULT_MAX_PROCESS_WORKERS,
    ) -> None:
        super().__init__(daemon=True)

        self.__queue = queue
        self.__gui_receiver = gui_receiver
        self.__max_workers = max_workers

        self.__active: dict[
            Future,
            tuple[
                ManagedProcessProtocol,
                list[Callable[[ManagedProcessProtocol], None]],
            ],
        ] = {}
        self.__lock = Lock()
        self.__started = False
        self.__stop_event = Event()

        self.__manager = ProcessManagerThread()

    @property
    def processes(
        self,
    ) -> dict[
        Future,
        tuple[
            ManagedProcessProtocol,
            list[Callable[[ManagedProcessProtocol], None]],
        ],
    ]:
        return self.__active

    def put(
        self,
        p: ManagedProcessProtocol,
        on_finish: (
            Callable[[ManagedProcessProtocol], None]
            | list[Callable[[ManagedProcessProtocol], None]]
            | None
        ) = None,
    ) -> None:
        if self.__queue.is_shutdown:
            return

        if on_finish is None:
            callbacks = []
        elif callable(on_finish):
            callbacks = [on_finish]
        else:
            callbacks = on_finish

        callbacks: list[Callable[[ManagedProcessProtocol], None]]

        self.__queue.put((p, callbacks))

    def run(self) -> None:
        logger.debug("[{}] Start", self)

        self.__started = True
        self.__manager.start()

        with ThreadPoolExecutor(max_workers=self.__max_workers) as executor:
            while not self.__stop_event.is_set():
                try:
                    p, callbacks = self.__queue.get()
                except ShutDown:
                    break

                if p is None:
                    logger.debug("[{}] Received stop flag", self)
                    self.__queue.task_done()
                    break

                callbacks = callbacks or []

                future = executor.submit(self.__execute_process, p, callbacks)

                with self.__lock:
                    self.__active[future] = (p, callbacks)

                self.__queue.task_done()

            self._wait_active()

        logger.debug("[{}] Finished", self)

    def __execute_process(
        self,
        process: ManagedProcessProtocol,
        callbacks: list[Callable[[ManagedProcessProtocol], None]],
    ) -> None:
        title = process.title if process else None

        try:
            res = process.run()
        except Exception as e:
            logger.error("[{}]: {}", title, str(e))
            res = e
        finally:
            with self.__lock:
                to_remove = [fut for fut, (proc, _) in self.__active.items() if proc is process]

                for fut in to_remove:
                    del self.__active[fut]

        self.__invoke_callbacks(callbacks, process)

        event = ProcessFinishedEvent(title, res, process.metadata)
        QCoreApplication.postEvent(self.__gui_receiver, event)

    def add_on_finish_callbacks(
        self,
        process: ManagedProcessProtocol,
        *callbacks: Callable[[ManagedProcessProtocol], None],
    ) -> None:
        with self.__lock:
            for proc, existing_callbacks in self.__active.values():
                if proc is process:
                    existing_callbacks.extend(self.__normalize_callbacks(*callbacks))
                    logger.debug(
                        "[{}] Added on finish callbacks for process: {}",
                        self,
                        process,
                    )
                    break
            else:
                logger.error(
                    "[{}] Adding on finish callbacks fail! Not found process: {}", self, process
                )

    def __stop_manager(self) -> None:
        with self.__lock:
            if self.__manager.is_alive():
                self.__manager.stop()

    def stop_all_processes(self, block: bool = False) -> None:
        logger.debug("[{}] Stopping all processes", self)

        with self.__lock:
            for process, _ in self.__active.values():
                try:
                    if block:
                        process.stop()
                    else:
                        self.__manager.put(process.stop)

                except Exception as e:
                    logger.error("[{}] Error stopping process: {}", self, e)

    def stop(self) -> None:
        logger.debug("[{}] Stopping", self)

        self.stop_all_processes(block=True)
        self.__stop_manager()
        self.__stop_queue()

        logger.debug("[{}] Stopped", self)

    @property
    def running(self) -> bool:
        return any([p.result.state is ProcessState.RUNNING for p, _ in self.__active.values()])

    def stop_process(self, process: ManagedProcessProtocol) -> None:
        with self.__lock:
            for future, (proc, _) in self.__active.items():
                if proc is process:
                    try:
                        process.stop()
                    except Exception as e:
                        logger.error("[{}] Error stopping process: {}", self, e)
                    break

    def _wait_active(self) -> None:
        while not self.__stop_event.is_set():
            with self.__lock:
                if not self.__active:
                    break

            self.__stop_event.wait(0.1)

        with self.__lock, suppress(Exception):
            for process, _ in self.__active.values():
                process.stop(force=True)

    def __stop_queue(self) -> None:
        if self.__queue.is_shutdown:
            return

        with suppress(Exception):
            self.__queue.put((None, None))

    @staticmethod
    def __normalize_callbacks(
        *on_finish_callbacks: Callable[[ManagedProcessProtocol], None],
    ) -> list[Callable[[ManagedProcessProtocol], None]]:
        return [i for i in on_finish_callbacks if callable(i)]

    def __invoke_callbacks(
        self,
        callbacks: list[Callable[[ManagedProcessProtocol], None]],
        process: ManagedProcessProtocol,
    ) -> None:
        for cb in callbacks:
            cb_name = getattr(cb, "__qualname__", None) or getattr(cb, "__name__", str(cb))

            logger.debug("[{}] Invoke callback: {}", self, cb_name)

            try:
                cb(process)
            except Exception as e:
                logger.exception("[{}] Callback error: {}", self, str(e), exc_info=e)


class ProcessManagerThread(Thread, ReprMixin):
    def __init__(
        self,
        max_workers: int = DEFAULT_MAX_PROCESS_WORKERS,
        queue_size: int = 10_000,
    ) -> None:
        super().__init__(daemon=True)

        self.__executor = ThreadPoolExecutor(max_workers=max_workers)
        self.__queue = Queue[tuple[Callable | None, tuple, dict]](queue_size)
        self.__started = False

    def put(self, fn: Callable, *args, **kwargs) -> None:
        self.__queue.put((fn, args, kwargs))

    def run(self) -> None:
        logger.debug("[{}] Starting", self)

        self.__started = True

        while self.__started:
            try:
                c, args, kwargs = self.__queue.get()
            except ShutDown:
                break

            if c is None:
                logger.debug("[{}] Received stop flag, stopping", self)
                self.__queue.task_done()
                break

            self.__submit(c, *args, **kwargs)

            self.__queue.task_done()

        self.__started = False

        logger.debug("[{}] Finished", self)

    def __submit(self, c: Callable, *args, **kwargs) -> None:
        name = getattr(c, "__qualname__", None) or getattr(c, "__name__", str(c))
        logger.debug("[{}] Submitting: {}", self, name)
        self.__executor.submit(c, *args, **kwargs)

    def stop(self) -> None:
        if not self.__started:
            return

        self.__started = False

        logger.debug("[{}] Stopping", self)

        self.__queue.put((None, (), {}))
        self.__executor.shutdown(wait=True)

        logger.debug("[{}] Stopped", self)
