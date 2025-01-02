from __future__ import annotations

import atexit
import json
import shutil
import tempfile
from abc import ABC, abstractmethod
from concurrent.futures import Future, ThreadPoolExecutor, wait
from datetime import datetime
from hashlib import md5
from os.path import join
from pathlib import Path
from threading import Lock, Thread
from time import sleep
from typing import Any, Dict, List, Optional, Union

import feedparser
from feedparser.util import FeedParserDict

from arkaine.tools import Tool
from arkaine.utils.interval import Interval
from arkaine.utils.website import Website


class Item:
    def __init__(
        self,
        title: str,
        description: str,
        link: str,
        published: str,
        content: str,
    ):
        self.title = title
        self.description = description
        self.link = link
        self.published = published
        self.content = content

    @staticmethod
    def format(entry: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "title": entry.get("title", ""),
            "description": entry.get("description", ""),
            "link": entry.get("link", ""),
            "published": entry.get("published", ""),
            "content": entry.get("content", entry.get("summary", "")),
        }

    @staticmethod
    def from_feedparser(entry: FeedParserDict) -> Item:
        return Item(
            title=entry.get("title", ""),
            description=entry.get("description", ""),
            link=entry.get("link", ""),
            published=entry.get("published", ""),
            content=entry.get("content", entry.get("summary", "")),
        )

    def __str__(self):
        return (
            f"{self.title}\n - {self.published}\n"
            f"\t{self.description}\n"
            f"\t{self.link}\n"
        )

    def get_website(self) -> Website:
        return Website(self.link)

    @property
    def md5(self) -> str:
        id = f"{self.title}-{self.link}-{self.published}"
        return md5(id.encode()).hexdigest()

    def to_json(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "description": self.description,
            "link": self.link,
            "published": self.published,
            "content": self.content,
        }

    @staticmethod
    def from_json(json: Dict[str, Any]) -> Item:
        return Item(
            title=json.get("title", ""),
            description=json.get("description", ""),
            link=json.get("link", ""),
            published=json.get("published", ""),
            content=json.get("content", ""),
        )


class Feed:

    def __init__(
        self,
        url: str,
        check_every: Union[str, Interval],
    ):
        self.__url = url
        if isinstance(check_every, str):
            if not self.__validate_recurrence(check_every):
                raise ValueError(
                    f"Invalid recurrence value: {check_every} - must be one of "
                    f"N{Interval.SECONDS}, N{Interval.MINUTES}, N{Interval.HOURS}"
                )
            self.__interval = Interval(datetime.now(), recur_every=check_every)
        elif isinstance(check_every, Interval):
            self.__interval = check_every
        else:
            raise ValueError(
                f"Invalid recurrence value: {check_every} - must be one of "
                f"N{Interval.SECONDS}, N{Interval.MINUTES}, N{Interval.HOURS}"
            )
        self.__last_check: Optional[datetime] = None

    def __validate_recurrence(self, value: str) -> bool:
        return value.endswith(
            (Interval.SECONDS, Interval.MINUTES, Interval.HOURS)
        )

    @property
    def url(self):
        return self.__url

    @property
    def trigger_at(self):
        return self.__interval.trigger_at

    @property
    def last_check(self):
        return self.__last_check

    def __str__(self):
        return (
            f"Feed(url={self.__url}, interval={self.__interval}, "
            f"last_check={self.__last_check})"
        )

    def get(self) -> List[Item]:
        self.__last_check = datetime.now()

        try:
            feed = feedparser.parse(self.__url)
            return [Item.from_feedparser(entry) for entry in feed.entries]
        except Exception as e:
            print(f"Error parsing RSS feed {self.__url}: {e}")
            return []
        finally:
            self.__interval.trigger()

    def to_json(self) -> Dict[str, Any]:
        return {
            "url": self.__url,
            "interval": self.__interval.to_json(),
            "last_check": self.__last_check,
        }

    @staticmethod
    def from_json(json: Dict[str, Any]) -> Feed:
        feed = Feed(
            url=json.get("url", ""),
            check_every=json.get("interval", ""),
        )
        feed.__last_check = json.get("last_check", datetime.now())
        return feed


class Store(ABC):
    """Abstract base class for RSS feed stores."""

    @abstractmethod
    def save_feed(
        self,
        feed: Feed,
    ) -> None:
        """Add a new RSS feed route with associated tool and format handler."""
        pass

    @abstractmethod
    def load_feed(self, feed: Feed) -> Optional[Feed]:
        """Load an RSS feed route."""
        pass

    @abstractmethod
    def save_item(
        self,
        item: Item,
    ) -> None:
        """Add a new RSS feed route with associated tool and format handler."""
        pass

    @abstractmethod
    def load_item(self, item: Item) -> Optional[Item]:
        """Load an RSS feed route."""
        pass


class FileStore(Store):
    def __init__(self, dir: str):
        self.__dir = Path(dir)
        self.__dir.mkdir(parents=True, exist_ok=True)
        # Make feed dir
        self.__feed_dir = self.__dir / "feeds"
        self.__feed_dir.mkdir(parents=True, exist_ok=True)
        # Make items dir
        self.__items_dir = self.__dir / "items"
        self.__items_dir.mkdir(parents=True, exist_ok=True)

    def __feed_path(self, feed: Feed) -> Path:
        id = md5(feed.url.encode()).hexdigest()
        return join(self.__feed_dir, id)

    def __item_path(self, item: Item) -> Path:
        return join(self.__items_dir, item.md5)

    def save_feed(self, feed: Feed) -> None:
        with open(self.__feed_path(feed), "w") as f:
            json.dump(feed.to_json(), f)

    def load_feed(self, feed: Feed) -> Optional[Feed]:
        try:
            with open(self.__feed_path(feed), "r") as f:
                return Feed.from_json(json.load(f))
        except FileNotFoundError:
            return None

    def save_item(self, item: Item) -> None:
        with open(self.__item_path(item), "w") as f:
            json.dump(item.to_json(), f)

    def load_item(self, item: Item) -> Optional[Item]:
        try:
            with open(self.__item_path(item), "r") as f:
                return Item.from_json(json.load(f))
        except FileNotFoundError:
            return None


class TempFileStore(FileStore):
    """
    This is a file store that utilizes a temp directory, which cleans up
    on exit (assuming clean exit).
    """

    def __init__(self):
        self.__dir = tempfile.mkdtemp()
        atexit.register(shutil.rmtree, self.__dir)
        super().__init__(self.__dir)


class RSS:
    """
    RSS is a trigger class that monitors multiple RSS feeds and executes tools
    when new items are detected. When this occurs, a list of Items
    (arkaine.triggers.rss.Item) are passed to the associated tools.

    Basic usage:
    ```python
    # Create feeds with check intervals
    feeds = [
        # Check every 30 minutes
        Feed("http://example.com/rss", "30:minutes"),
        # Check every hour
        Feed("http://another.com/feed", "1:hours"),
        # Check every day
        Feed(
            "http://example.com/rss",
            Interval(datetime.now(), recur_every="daily"),
        ),
    ]

    # Create RSS trigger with feeds and tools
    rss = RSS(feeds=feeds, tools=[my_tool])

    # Start monitoring
    rss.start()

    # Add new feed while running
    rss.add_feed(Feed("http://new.com/rss", "15:minutes"))

    # Stop monitoring
    rss.stop()
    ```
    """

    def __init__(
        self,
        feeds: List[Feed],
        store: Optional[Store] = None,
        tools: Optional[Union[List[Tool], Tool]] = None,
        max_workers: int = 10,
        feed_timeout: int = 30,
    ):
        self.__feeds = feeds

        if store:
            self.__store = store
            for i, feed in enumerate(self.__feeds):
                self.__feeds[i] = self.__store.load_feed(feed)
        else:
            self.__store = TempFileStore()

        if not tools:
            tools = []
        elif isinstance(tools, Tool):
            tools = [tools]
        self.__tools = tools

        self.__running = False
        self.__die = False
        self.__lock = Lock()

        self.__thread = Thread(target=self.__run)
        self.__thread.start()

        self.__feed_threadpool = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="rss_feed_pool"
        )
        self.__feed_timeout = feed_timeout

    def __del__(self):
        """Ensure proper cleanup of threads and executor"""
        self.__die = True
        if hasattr(self, "_RSS__thread") and self.__thread.is_alive():
            self.__thread.join(timeout=1.0)  # Wait up to 1 second
        if hasattr(self, "_RSS__feed_threadpool"):
            self.__feed_threadpool.shutdown(wait=False, cancel_futures=True)

    @property
    def feeds(self):
        with self.__lock:
            return self.__feeds

    def add_feed(self, feed: Feed):
        with self.__lock:
            self.__feeds.append(feed)
            if self.__store:
                self.__store.save_feed(feed)

    @property
    def tools(self):
        with self.__lock:
            return self.__tools

    def add_tool(self, tool: Tool):
        if any(t.id == tool.id for t in self.__tools):
            return
        with self.__lock:
            self.__tools.append(tool)

    def start(self):
        with self.__lock:
            self.__running = True

    def stop(self):
        """Stop RSS monitoring and cleanup resources"""
        with self.__lock:
            self.__running = False
            # Cancel any pending futures
            self.__feed_threadpool.shutdown(wait=False, cancel_futures=True)
            # Create new threadpool for potential restart
            self.__feed_threadpool = ThreadPoolExecutor(
                max_workers=self.__feed_threadpool._max_workers,
                thread_name_prefix="rss_feed_pool",
            )

    def __handle_feed(self, feed: Feed):
        if feed.trigger_at > datetime.now():
            return

        items = feed.get()

        # Here we filter out the items that we have already
        # saved and thus processed. Note that we don't track
        # success here yet - that's a TODO
        filtered_items = []
        for index, item in enumerate(items):
            if not self.__store.load_item(item):
                self.__store.save_item(item)
                filtered_items.append(item)

        if len(filtered_items) == 0:
            return

        with self.__lock:
            # Finally trigger all tools attached to the RSS trigger class
            # with the detected items
            for tool in self.__tools:
                tool.async_call(filtered_items)

    def __run(self):
        while True:
            futures: List[Future] = []

            with self.__lock:
                if self.__die:
                    break
                elif not self.__running:
                    continue

                for feed in self.__feeds:
                    future = self.__feed_threadpool.submit(
                        self.__handle_feed, feed
                    )
                    futures.append(future)

            wait(futures, timeout=self.__feed_timeout)

            sleep(1.0)
