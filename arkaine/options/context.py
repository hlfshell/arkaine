"""Module for managing global context options in a thread-safe manner."""

from pathlib import Path
from threading import Lock
from typing import Optional


class ContextOptions:
    """
    Thread-safe singleton class for managing global context options.
    Provides centralized control over context behavior across the application.
    """

    __instance: Optional["ContextOptions"] = None
    __lock = Lock()

    # Debug enables/disables the debug store on contexts, and whether
    # or not their messages are broadcasted to any possible subscribers
    __debug = False

    __save_on_success = False
    __save_on_exception = False

    # Saving a context will write to the target folder (default, current
    # working directory + "{date}/", the contexts for the current date are
    # saved in the "success" folder. The {date} template will always be
    # replaced with the current day according to the system's timezone. The
    # contexts are then placed in a subfolder which lands it in, by default,
    # the "success" (success_folder) or "exception" (exception_folder) folder.
    # If a context had neither completed or failed, it is saved in the
    # "running" (running_folder) folder.
    __save_folder = Path.cwd() / "{date}"
    __success_folder = "success"
    __running_folder = "running"
    __exception_folder = "exception"

    def __new__(cls):
        raise ValueError("ContextOptions cannot be instantiated")

    @classmethod
    def debug(cls, value: Optional[bool] = None) -> bool:
        with cls.__lock:
            if value is not None:
                cls.__debug = value
            return cls.__debug

    @classmethod
    def save_on_success(cls, value: Optional[bool] = None) -> bool:
        with cls.__lock:
            if value is not None:
                cls.__save_on_success = value
            return cls.__save_on_success

    @classmethod
    def save_on_exception(cls, value: Optional[bool] = None) -> bool:
        with cls.__lock:
            if value is not None:
                cls.__save_on_exception = value
            return cls.__save_on_exception

    @classmethod
    def save_folder(cls, value: Optional[Path] = None) -> Path:
        with cls.__lock:
            if value is not None:
                cls.__save_folder = value
                cls.__ensure_exists(cls.__save_folder)
                cls.__ensure_exists(cls.__success_folder)
                cls.__ensure_exists(cls.__running_folder)
                cls.__ensure_exists(cls.__exception_folder)
            return cls.__save_folder

    @classmethod
    def success_folder(cls, value: Optional[Path] = None) -> Path:
        with cls.__lock:
            if value is not None:
                cls.__success_folder = value
            cls.__ensure_exists(cls.__success_folder)
            return cls.__success_folder

    @classmethod
    def exception_folder(cls, value: Optional[Path] = None) -> Path:
        with cls.__lock:
            if value is not None:
                cls.__exception_folder = value
            cls.__ensure_exists(cls.__exception_folder)
            return cls.__exception_folder

    @classmethod
    def running_folder(cls, value: Optional[Path] = None) -> Path:
        with cls.__lock:
            if value is not None:
                cls.__running_folder = value
            cls.__ensure_exists(cls.__running_folder)
            return cls.__running_folder

    @classmethod
    def __ensure_exists(cls, folder: Path):
        if not folder.exists():
            folder.mkdir(parents=True, exist_ok=True)
