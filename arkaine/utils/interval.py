from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional


class Interval:

    HOURLY = "hourly"
    DAILY = "daily"
    TWICEADAY = "twice a day"
    WEEKENDS = "weekends"
    WEEKDAYS = "weekdays"
    WEEKLY = "weekly"
    FORTNIGHTLY = "fortnightly"
    MONTHLY = "monthly"
    YEARLY = "yearly"

    SECONDS = ":seconds"
    MINUTES = ":minutes"
    HOURS = ":hours"

    def __init__(self, trigger_at: datetime, recur_every: Optional[str] = None):
        # Convert all time units to seconds and store as total_seconds
        self.__trigger_at: Optional[None] = trigger_at

        # Calendar-based attributes remain unchanged
        self.__last_triggered: datetime = None
        if not self.__validate_recurrence(recur_every):
            raise ValueError(f"Invalid recurrence value: {recur_every}")
        self.__recur_every = recur_every

    def __validate_recurrence(self, value: Optional[str]) -> bool:
        if value is None:
            return True
        return value in [
            self.HOURLY,
            self.DAILY,
            self.TWICEADAY,
            self.WEEKENDS,
            self.WEEKDAYS,
            self.WEEKLY,
            self.FORTNIGHTLY,
            self.MONTHLY,
            self.YEARLY,
        ] or value.endswith((self.SECONDS, self.MINUTES, self.HOURS))

    @property
    def trigger_at(self) -> Optional[datetime]:
        return self.__trigger_at

    def trigger(self) -> Optional[datetime]:
        self.__last_triggered = self.__trigger_at

        self.__set_next_trigger_at()

    @property
    def last_triggered(self) -> Optional[datetime]:
        return self.__last_triggered

    @property
    def recur_every(self) -> str:
        return self.__recur_every

    @recur_every.setter
    def recur_every(self, value: Optional[str] = None):
        if not self.__validate_recurrence(value):
            raise ValueError(f"Invalid recurrence value: {value}")
        self.__recur_every = value
        self.__set_next_trigger_at()

    def __set_next_trigger_at(self):
        if not self.__recur_every:
            self.__trigger_at = None
            return None

        # Handle time-based intervals
        for unit in [self.SECONDS, self.MINUTES, self.HOURS]:
            if self.recur_every.endswith(unit):
                try:
                    value = float(self.recur_every.split(":")[0])
                    if unit == self.SECONDS:
                        self.__trigger_at = self.__trigger_at + timedelta(
                            seconds=value
                        )
                    elif unit == self.MINUTES:
                        self.__trigger_at = self.__trigger_at + timedelta(
                            minutes=value
                        )
                    else:
                        self.__trigger_at = self.__trigger_at + timedelta(
                            hours=value
                        )
                    return
                except ValueError:
                    raise ValueError(f"Invalid value in: {self.recur_every}")
        if self.recur_every == self.HOURLY:
            self.__trigger_at = self.__trigger_at + timedelta(hours=1)
        elif self.recur_every == self.DAILY:
            self.__trigger_at = self.__trigger_at + timedelta(days=1)
        elif self.recur_every == self.TWICEADAY:
            self.__trigger_at = self.__trigger_at + timedelta(days=0.5)
        elif self.recur_every == self.WEEKENDS:
            self.__trigger_at = __next_weekend(self.__trigger_at)
        elif self.recur_every == self.WEEKDAYS:
            self.__trigger_at = __next_weekday(self.__trigger_at)
        elif self.recur_every == self.WEEKLY:
            self.__trigger_at = self.__trigger_at + timedelta(days=7)
        elif self.recur_every == self.FORTNIGHTLY:
            self.__trigger_at = self.__trigger_at + timedelta(days=14)
        elif self.recur_every == self.MONTHLY:
            self.__trigger_at = self.__trigger_at + timedelta(weeks=4)
        elif self.recur_every == self.YEARLY:
            self.__trigger_at = __add_one_year(self.__trigger_at)

    def __str__(self):
        out = f"Interval - triggers @ {self.__trigger_at}"
        if self.recur_every:
            out += f" - Recurring {self.recur_every}"
        return out

    def __repr__(self):
        return self.__str__()

    def to_json(self):
        return {
            "trigger_at": (
                self.__trigger_at.isoformat() if self.__trigger_at else None
            ),
            "recur_every": self.__recur_every,
            "last_triggered": (
                self.__last_triggered.isoformat()
                if self.__last_triggered
                else None
            ),
        }

    @classmethod
    def from_json(cls, json_data: dict) -> Interval:
        trigger_at = datetime.fromisoformat(json_data["trigger_at"])
        last_triggered = (
            datetime.fromisoformat(json_data["last_triggered"])
            if json_data["last_triggered"]
            else None
        )
        interval = cls(trigger_at, json_data["recur_every"])
        interval.__last_triggered = last_triggered
        return interval


def __add_one_month(original_date: datetime) -> datetime:
    new_month = original_date.month + 1
    new_year = original_date.year
    if new_month > 12:
        new_month = 1
        new_year += 1

    if new_month == 2:  # February the problem child
        is_leap_year = new_year % 4 == 0 and (
            new_year % 100 != 0 or new_year % 400 == 0
        )
        last_day = 29 if is_leap_year else 28
    else:
        last_day = 30 if new_month in {4, 6, 9, 11} else 31
    return original_date.replace(year=new_year, month=new_month, day=last_day)


def __add_one_year(original_date: datetime) -> datetime:
    if original_date.month == 2 and original_date.day == 29:
        return original_date.replace(
            year=original_date.year + 1, month=2, day=28
        )
    else:
        return original_date.replace(year=original_date.year + 1)


def __next_weekend(original_date: datetime) -> datetime:
    weekday = original_date.weekday()
    if weekday < 5:
        return original_date + timedelta(days=5 - weekday)
    elif weekday == 5:
        return original_date + timedelta(days=1)
    else:
        return original_date + timedelta(days=6)


def __next_weekday(original_date: datetime) -> datetime:
    weekday = original_date.weekday()
    if weekday < 4:
        return original_date + timedelta(days=1)
    else:
        return original_date + timedelta(days=7 - weekday + 1)
