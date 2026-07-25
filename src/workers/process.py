from __future__ import annotations

from time import sleep

from loguru import logger

from processes import ManagedProcess, ProcessState


class FFProcess(ManagedProcess):
    def stop(
        self,
        force: bool = False,
        timeout: int | float = 2,
    ) -> None:
        logger.debug("[{}] Stopping FF process", self)

        self.cancel()

        if self.result.state is ProcessState.RUNNING:
            self.write_stdin("q\n", flush=True)

            sleep(0.8)

        if self.result.state is ProcessState.RUNNING:
            super().stop(force, timeout)

        logger.debug("[{}] Stopped", self)
