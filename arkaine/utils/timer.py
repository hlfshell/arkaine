from datetime import datetime


class Timer:
    def __init__(self):
        self.__elapsed: float = 0
        self._start_time = None

    def __enter__(self):
        self._start_time = datetime.now()
        return self

    def __exit__(self, *args):
        end_time = datetime.now()
        self.__elapsed = (end_time - self._start_time).total_seconds()

    @property
    def elapsed(self) -> float:
        return self.__elapsed
