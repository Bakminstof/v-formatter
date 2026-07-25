from __future__ import annotations


class ProcessError(Exception):
    """
    Базовое исключение библиотеки.
    """

    pass


class ProcessStartError(ProcessError):
    """
    Не удалось запустить процесс.
    """

    pass


class ProcessAlreadyRunningError(ProcessError):
    """
    Попытка повторно запустить уже работающий процесс.
    """

    pass


class ProcessNotRunningError(ProcessError):
    """
    Операция требует запущенного процесса.
    """

    pass


class ProcessTimeoutError(ProcessError):
    """
    Процесс превысил допустимое время выполнения.
    """

    pass


class ProcessKilledError(ProcessError):
    """
    Процесс был принудительно остановлен пользователем.
    """

    pass


class ProcessReadError(ProcessError):
    """
    Ошибка чтения stdout/stderr.
    """

    pass
