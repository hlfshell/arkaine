from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from datetime import datetime
from os.path import join
from queue import PriorityQueue
from threading import Lock, Thread
from time import sleep
from typing import List, Optional, Union
from uuid import uuid4

from arkaine.internal.registrar import Registrar
from arkaine.tools.context import Context
from arkaine.tools.tool import Tool
from arkaine.utils.interval import Interval
from arkaine.utils.timer import Timer


class Task:

    def __init__(
        self,
        tool: Tool,
        args: dict,
        trigger_at: Union[Interval, datetime],
        paused: bool = False,
        id: Optional[str] = None,
        history: List[float] = None,
        history_length: int = 100,
    ):
        self.__id = id or str(uuid4())
        self.__tool = tool
        self.__args = args
        self.__paused = paused
        self.__history: List[float] = history or []
        self.__history_length = history_length
        self.__lock = Lock()

        # Convert datetime to Interval if needed
        if isinstance(trigger_at, datetime):
            self.__interval = Interval(trigger_at)
        else:
            self.__interval = trigger_at

    @property
    def id(self) -> str:
        return self.__id

    @property
    def tool(self) -> Tool:
        return self.__tool

    @property
    def args(self) -> dict:
        return self.__args

    @property
    def interval(self) -> Interval:
        with self.__lock:
            return self.__interval

    @property
    def trigger_at(self) -> datetime:
        with self.__lock:
            return self.__interval.trigger_at

    @property
    def paused(self) -> bool:
        with self.__lock:
            return self.__paused

    @paused.setter
    def paused(self, value: bool):
        with self.__lock:
            self.__paused = value

    @property
    def last_triggered(self):
        with self.__lock:
            return self.__interval.last_triggered

    @property
    def next(self) -> datetime:
        """Get the next trigger time."""
        return self.__interval.trigger_at

    def trigger(self) -> datetime:
        with self.__lock:
            return self.__interval.trigger()

    def __call__(self, context: Optional[Context] = None):
        if self.paused:
            raise ValueError("Task is paused")

        with self.__lock:
            self.__interval.trigger()

            with Timer() as timer:
                result = self.tool(context=context, **self.args)

            self.__history.append(timer.elapsed)
            if len(self.__history) > self.__history_length:
                self.__history.pop(0)

        return result

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "tool": self.tool.name,
            "args": self.args,
            "trigger_at": self.__interval.to_json(),
            "paused": self.paused,
            "history": self.__history,
            "history_length": self.__history_length,
        }

    @classmethod
    def from_json(cls, json_dict: dict) -> Task:
        interval = Interval.from_json(json_dict["trigger_at"])
        return cls(
            tool=Registrar.get_tool(json_dict["tool"]),
            args=json_dict["args"],
            trigger_at=interval,
            paused=json_dict["paused"],
            history=json_dict["history"],
            history_length=json_dict["history_length"],
        )


class TaskStore(ABC):

    @abstractmethod
    def save(self, tasks: Union[Task, List[Task]], overwrite: bool = False):
        pass

    @abstractmethod
    def load(self, task: Union[Task, str]) -> Task:
        pass

    @abstractmethod
    def load_all(self) -> List[Task]:
        pass


class FileScheduleStore(TaskStore):
    def __init__(self, dir_path: str):
        self.dirpath = dir_path
        os.makedirs(os.path.dirname(dir_path), exist_ok=True)

    def save(self, tasks: Union[Task, List[Task]], overwrite: bool = True):
        if isinstance(tasks, Task):
            tasks = [tasks]

        for task in tasks:
            filepath = join(self.dirpath, task.id)

            # if the file already exists, do not overwrite
            if os.path.exists(filepath) and not overwrite:
                continue

            with open(filepath, "w") as f:
                json.dump(task.to_json(), f)

    def load(self, task: Union[Task, str]) -> Task:
        if isinstance(task, Task):
            task = task.id

        with open(join(self.dirpath, task)) as f:
            return Task.from_json(json.load(f))

    def load_all(self) -> List[Task]:
        tasks = []
        for file in os.listdir(self.dirpath):
            tasks.append(self.load(file))
        return tasks


class Schedule:

    def __init__(
        self,
        tasks: Union[Task, List[Task], TaskStore] = [],
    ):
        self.__lock = Lock()
        self.tasks = []
        self.running = False

        self._schedule = PriorityQueue()
        self._last_check_time = 0

        self.schedule_store = None
        if isinstance(tasks, Task):
            self.add_task(tasks)
        elif isinstance(tasks, list):
            for task in tasks:
                self.add_task(task)
        elif isinstance(tasks, TaskStore):
            self.schedule_store = tasks

            for task in self.schedule_store.load_all():
                if task not in self.tasks:
                    self.tasks.append(task)
                    self._schedule.put((task.next(), task))

    def add_task(self, task: Task):
        next_time = task.next
        if self.schedule_store:
            self.schedule_store.save(task, overwrite=False)

        with self.__lock:
            if task in self.tasks:
                return

            self.tasks.append(task)
            self._schedule.put((next_time, task))

    def remove_task(self, task: Task):
        with self.__lock:
            self.tasks.remove(task)

    def run(self):
        with self.__lock:
            if self.running:
                return
            self.running = True

        Thread(target=self._check_tasks).start()

    def stop(self):
        with self.__lock:
            self.running = False

    def __run_task(self, task: Task):
        try:
            task()
        except Exception as e:
            print(f"Error running task: {e}")
        finally:
            if self.schedule_store:
                self.schedule_store.save(task)

    def _check_tasks(self):
        while True:
            with self.__lock:
                if not self.running:
                    break

            if self._schedule.empty():
                sleep(0.5)
                continue

            next_time, task = self._schedule.queue[0]
            now = datetime.now()
            if next_time > now:
                with self.__lock:
                    self._last_check_time = now
                sleep(0.5)
                continue
            else:
                next_time, task = self._schedule.get()
                task.trigger()
                if task.interval.recur_every:
                    self._schedule.put((task.trigger_at, task))
                    if self.schedule_store:
                        self.schedule_store.save(task)
                Thread(target=self.__run_task, args=(task,)).start()

    def save(self):
        if self.schedule_store:
            self.schedule_store.save(self)
        else:
            raise ValueError("No schedule store provided")
