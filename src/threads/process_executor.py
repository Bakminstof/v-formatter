from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import suppress
from multiprocessing import cpu_count
from queue import Empty, Queue, ShutDown
from threading import Event, Lock, Thread
from typing import Callable

from loguru import logger
from PySide6.QtCore import QCoreApplication, QEvent, QObject

from core.mixins import ReprMixin
from processes import ManagedProcess, ProcessResult, ProcessState

MANAGED_PROCESS_FINISHED_EVENT_TYPE = QEvent.Type(QEvent.Type.User + 1)
DEFAULT_MAX_PROCESS_WORKERS = min(cpu_count(), 16)


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
        queue: Queue[tuple[ManagedProcess | None, Callable | None]],
    ) -> None:
        super().__init__(daemon=True)

        self.__queue = queue

        self.__gui_receiver = gui_receiver

        self.__process: ManagedProcess | None = None
        self.__process_stop_fn: Callable | None = None

        self.__lock = Lock()

        self.__manager = ProcessManagerThread()

        self.__started = False

    @property
    def process(self) -> ManagedProcess | None:
        return self.__process or None

    def put(self, p: ManagedProcess, stop_fn: Callable | None = None) -> None:
        self.__queue.put((p, stop_fn))

    def run(self) -> None:
        logger.debug("[{}] Start", self)

        self.__started = True

        self.__manager.start()

        while self.__started:
            try:
                p, stop = self.__queue.get(timeout=1)
            except Empty:
                continue
            except ShutDown:
                break

            if p is None:
                logger.debug("[{}] Received stop flag, stopping", self)
                self.__queue.task_done()
                break

            self.__process = p
            self.__process_stop_fn = stop

            title = self.process.title if self.process else None

            try:
                res = self.__process.run()
            except Exception as e:
                logger.error("[{}]: {}", title, str(e))
                res = e
            finally:
                self.__queue.task_done()

            event = ProcessFinishedEvent(
                title,
                res,
                p.metadata,
            )
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

    def __stop_process(self) -> None:
        if not self.process:
            return

        with self.__lock:
            if not self.process.result.state is ProcessState.RUNNING:
                return

            title = self.process.title if self.process else None

            logger.debug(
                "[{}] Stopping process: {!r}",
                self,
                title,
            )

            if self.__process_stop_fn is not None:
                self.__process_stop_fn()
            else:
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


class ProcessPoolExecutorThread(Thread, ReprMixin):
    def __init__(
        self,
        gui_receiver: QObject,
        queue: Queue[tuple[ManagedProcess | None, Callable | None]],
        max_workers: int = DEFAULT_MAX_PROCESS_WORKERS,
    ) -> None:
        super().__init__(daemon=True)

        self.__queue = queue
        self.__gui_receiver = gui_receiver
        self.__max_workers = max_workers

        self.__active: dict[Future, tuple[ManagedProcess, Callable | None]] = {}
        self.__lock = Lock()
        self.__started = False
        self.__stop_event = Event()

        self.__manager = ProcessManagerThread()

    @property
    def processes(self) -> dict[Future, tuple[ManagedProcess, Callable | None]]:
        return self.__active

    def put(self, p: ManagedProcess, stop_fn: Callable | None = None) -> None:
        self.__queue.put((p, stop_fn))

    def run(self) -> None:
        logger.debug("[{}] Start", self)

        self.__started = True

        self.__manager.start()

        with ThreadPoolExecutor(max_workers=self.__max_workers) as executor:
            while not self.__stop_event.is_set():
                try:
                    p, stop_fn = self.__queue.get(timeout=1)
                except Empty:
                    continue
                except ShutDown:
                    break

                if p is None:
                    logger.debug("[{}] Received stop flag", self)
                    self.__queue.task_done()
                    break

                future = executor.submit(self.__execute_process, p, stop_fn)

                with self.__lock:
                    self.__active[future] = (p, stop_fn)

                self.__queue.task_done()

            self._wait_active()

        logger.debug("[{}] Finished", self)

    def __execute_process(
        self,
        process: ManagedProcess,
        stop_fn: Callable | None,
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

        event = ProcessFinishedEvent(title, res, process.metadata)
        QCoreApplication.postEvent(self.__gui_receiver, event)

    def __stop_manager(self) -> None:
        with self.__lock:
            if self.__manager.is_alive():
                self.__manager.stop()

    def stop_all_processes(self, block: bool = False) -> None:
        if block:
            self.__stop_all()
        else:
            self.__manager.put(self.__stop_all)

    def stop(self) -> None:
        logger.debug("[{}] Stopping", self)

        self.stop_all_processes(block=True)
        self.__stop_manager()
        self.__stop_queue()

        logger.debug("[{}] Stopped", self)

    def __stop_all(self) -> None:
        logger.debug("[{}] Stopping all processes", self)

        with self.__lock:
            for process, stop_fn in self.__active.values():
                try:
                    if stop_fn is not None:
                        stop_fn()
                    else:
                        process.stop()
                except Exception as e:
                    logger.error("[{}] Error stopping process: {}", self, e)

        self.__stop_event.set()
        self.__stop_queue()

        if self.is_alive():
            self.join(timeout=10)

        logger.debug("[{}] Stopped", self)

    def stop_process(self, process: ManagedProcess) -> None:
        with self.__lock:
            for future, (proc, stop_fn) in self.__active.items():
                if proc is process:
                    try:
                        if stop_fn is not None:
                            stop_fn()
                        else:
                            process.stop()
                    except Exception as e:
                        logger.error("[{}] Error stopping process: {}", self, e)
                    break

    def _wait_active(self) -> None:
        while not self.__stop_event.is_set():
            with self.__lock:
                if not self.__active:
                    break

            self.__stop_event.wait(0.5)

        if self.__stop_event.is_set():
            with self.__lock:
                for process, stop_fn in self.__active.values():
                    with suppress(Exception):
                        process.stop(force=True)

    def __stop_queue(self) -> None:
        if self.__queue.is_shutdown:
            return

        with suppress(Exception):
            self.__queue.put((None, None))


class ProcessManagerThread(Thread, ReprMixin):
    def __init__(self, max_workers: int = 10, queue_size: int = 100) -> None:
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
                c, args, kwargs = self.__queue.get(timeout=1)
            except Empty:
                continue
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
