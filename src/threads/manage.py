import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import Callable

import humanize
from loguru import logger
from PySide6.QtCore import QRunnable, Slot

from threads.workers.task_worker import TaskWorker

DEFAULT_MAX_WORKERS = 16

type CallbackSingle = Callable
type CallbackWithArgsAndKwargs = tuple[Callable, tuple, dict] | tuple[Callable, dict, tuple]
type CallbackWithArgs = tuple[Callable, tuple]
type CallbackWithKwargs = tuple[Callable, dict]

type ExecutableType = CallbackSingle | CallbackWithArgsAndKwargs | CallbackWithArgs | CallbackWithKwargs


def run_in_thread_pool(
    items: list[ExecutableType] | tuple[ExecutableType, ...],
    *,
    max_workers: int = DEFAULT_MAX_WORKERS,
    executor: ThreadPoolExecutor | None = None,
) -> bool:
    title = f"ThreadPool(workers={max_workers})"
    logger.debug("[{}] Start executing {} items ", title, len(items))

    start = time.monotonic()

    if executor is None:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            is_success = __run_in_thread_pool(title, items, executor)
    else:
        is_success = __run_in_thread_pool(title, items, executor)

    elapsed = time.monotonic() - start

    logger.debug(
        "[{}] Finish at {}",
        title,
        humanize.precisedelta(elapsed),
    )

    return is_success


def __run_in_thread_pool(
    title: str,
    items: list[ExecutableType] | tuple[ExecutableType, ...],
    executor: ThreadPoolExecutor,
) -> bool:
    is_success = True

    futures: list[Future[None]] = []

    for item in items:
        if isinstance(item, tuple):
            item: tuple

            if len(item) not in {2, 3}:
                msg = "[{}] Invalid item format: {}", title, item
                logger.error(*msg)
                raise ValueError(msg[0].format(*msg[1:]))

            if len(item) == 2 and isinstance(item[1], tuple):
                futures.append(executor.submit(item[0], *item[1]))
            elif len(item) == 2 and isinstance(item[1], dict):
                futures.append(executor.submit(item[0], **item[1]))
            elif len(item) == 3 and isinstance(item[1], dict) and isinstance(item[2], tuple):
                futures.append(executor.submit(item[0], *item[2], **item[1]))
            elif len(item) == 3 and isinstance(item[1], tuple) and isinstance(item[2], dict):
                futures.append(executor.submit(item[0], *item[1], **item[2]))
        else:
            item: Callable

            futures.append(executor.submit(item))

    for future in as_completed(futures):
        try:
            future.result()
        except Exception as e:
            logger.error("[{}]: {}", title, str(e))
            is_success = False

    return is_success


class TaskManager:
    def __init__(self) -> None:
        self._tasks: list[TaskWorker] = []

    def add_task(
        self,
        callback: Callable[..., None],
        interval_s: int = 0,
        *callback_args,
        **callback_kwargs,
    ) -> TaskWorker:
        worker = TaskWorker(
            callback,
            interval_s,
            *callback_args,
            **callback_kwargs,
        )

        self._tasks.append(worker)
        worker.start()

        return worker

    def stop_all(self) -> None:
        for worker in self._tasks:
            worker.stop()


class Runnable(QRunnable):
    def __init__(self, func: Callable, *args, **kwargs) -> None:
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    @Slot()
    def run(self):
        self.func(*self.args, **self.kwargs)
