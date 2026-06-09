from typing import Callable

from workers.periodic_worker import TaskWorker


class TaskManager:
    def __init__(self) -> None:
        self._tasks: list[TaskWorker] = []

    def add_task(
        self,
        interval_s: int = 0,
        *,
        callback: Callable,
        callback_args: tuple | None = None,
        callback_kwargs: dict | None = None,
    ) -> TaskWorker:
        worker = TaskWorker(
            interval_s,
            callback=callback,
            callback_args=callback_args,
            callback_kwargs=callback_kwargs,
        )

        self._tasks.append(worker)
        worker.start()

        return worker

    def stop_all(self) -> None:
        for worker in self._tasks:
            worker.stop()
