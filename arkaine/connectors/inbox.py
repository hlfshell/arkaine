from __future__ import annotations

import email
import hashlib
import imaplib
import json
import os
import re
import traceback
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Lock, Thread
from time import sleep
from typing import Callable, Dict, List, Optional, Union

from arkaine.tools.tool import Tool
from arkaine.utils.interval import Interval


class EmailMessage:
    def __init__(
        self,
        subject: str,
        sender: str,
        body: str,
        received_at: datetime,
        message_id: str,
        tags: List[str] = [],
    ):
        self.subject = subject
        self.sender = sender
        self.body = body
        self.received_at = received_at
        self.message_id = message_id
        self.tags = tags

        if not self.message_id:
            self.__generate_id()

    def __str__(self):
        """Convert EmailMessage to string representation"""
        # Remove microseconds from datetime representation
        formatted_date = self.received_at.replace(microsecond=0).isoformat()
        return (
            f"ID: {self.message_id}\n"
            f"From: {self.sender} @ {formatted_date}\n"
            f"Subject: {self.subject}\n"
            f"Date: {formatted_date}\n"
            f"Tags: {', '.join(self.tags)}\n"
            f"Body: {self.body}"
        )

    def __generate_id(self):
        """
        If the e-mail is lacking an ID, generate one
        from the combination of sender, subject, and body
        """
        if not self.message_id:
            self.message_id = hashlib.sha256(
                f"{self.sender}{self.subject}{self.body}".encode()
            ).hexdigest()

    @staticmethod
    def to_json(message: EmailMessage) -> str:
        """Convert EmailMessage to JSON string"""
        data = {
            "subject": message.subject,
            "sender": message.sender,
            "body": message.body,
            "received_at": message.received_at.isoformat(),
            "message_id": message.message_id,
            "tags": message.tags,
        }
        return json.dumps(data)

    @staticmethod
    def from_json(json_str: str) -> EmailMessage:
        """Create EmailMessage from JSON string"""
        data = json.loads(json_str)
        # Convert ISO format string back to datetime
        data["received_at"] = datetime.fromisoformat(data["received_at"])
        return EmailMessage(**data)

    @staticmethod
    def from_str(email_str: str) -> EmailMessage:
        """Create EmailMessage from string representation"""
        # Extract fields from string format
        lines = email_str.strip().split("\n")
        message_id = lines[0].replace("ID: ", "")
        sender = lines[1].split(" @ ")[0].replace("From: ", "")
        # Parse datetime without microseconds
        received_at = datetime.fromisoformat(lines[1].split(" @ ")[1])
        subject = lines[2].replace("Subject: ", "")
        tags_str = lines[4].replace("Tags: ", "")
        tags = tags_str.split(", ") if tags_str else []
        body = lines[5].replace("Body: ", "")

        return EmailMessage(
            subject=subject,
            sender=sender,
            body=body,
            received_at=received_at,
            message_id=message_id,
            tags=tags,
        )

    @staticmethod
    def from_message(msg: email.message.Message) -> EmailMessage:
        """Create EmailMessage from email.message.Message object."""
        subject = msg.get("subject", "")
        sender = msg.get("from", "")
        received_at = email.utils.parsedate_to_datetime(msg.get("date"))
        message_id = msg.get("message-id", "")

        # Decode the subject properly
        subject = email.header.decode_header(subject)
        subject = "".join(
            (
                str(t[0], t[1] if t[1] else "utf-8")
                if isinstance(t[0], bytes)
                else t[0]
            )
            for t in subject
        )

        body = ""
        if msg.is_multipart():
            parts = msg.walk()
        else:
            parts = [msg]

        for part in parts:
            if part.get_content_type() in ["text/plain", "text/html"]:
                try:
                    body = part.get_payload(decode=True).decode()
                except UnicodeDecodeError:
                    body = part.get_payload(decode=True).decode("ISO-8859-1")
                break

        return EmailMessage(
            subject=subject,
            sender=sender,
            body=body,
            received_at=received_at,
            message_id=message_id,
        )


class SeenMessageStore(ABC):
    def __init__(self):
        super().__init__()

    @abstractmethod
    def add(self, message: EmailMessage):
        pass

    @abstractmethod
    def contains(self, message: Union[EmailMessage, str]) -> bool:
        pass


class FileSeenMessageStore(SeenMessageStore):
    def __init__(self, filename: str):
        super().__init__()
        self.filename = filename
        self.__messages = set()
        self.__lock = Lock()

        if not os.path.exists(self.filename):
            self.save()
        else:
            self.load()

    def add(self, message: EmailMessage):
        with self.__lock:
            self.__messages.add(message.message_id)
            self.save()

    def contains(self, message: Union[EmailMessage, str]) -> bool:
        with self.__lock:
            if isinstance(message, EmailMessage):
                return message.message_id in self.__messages
            else:
                return message in self.__messages

    def save(self):
        with open(self.filename, "w") as f:
            f.write("\n".join(self.__messages))

    def load(self):
        with open(self.filename, "r") as f:
            self.__messages = set(f.readlines())


class EmailFilter:
    """
    A filter for EmailMessage objects that allows filtering based on various
    fields.

    Args:
        subject_pattern - (Optional[str]): A string or regex pattern to match
            the subject of the email.

        sender_pattern - (Optional[str]): A string or regex pattern to match
            the sender of the email.

        body_pattern -  (Optional[str]): A string or regex pattern to match the
            body of the email.

        tags -  (Optional[List[str]]): A list of tags to match against the
            email's tags.

        func -  (Optional[Callable[[EmailMessage], bool]]): A custom function
            to apply additional filtering logic.

        match_all -  (bool): If True, all conditions must be met; if False, ANY
            condition can be met and the filter will return True. Defaults to
            True.


    Note that filters can be combined by adding them, resulting in a set of
    filters that check in the order they are created. Thus if you have filters
    A and B, and you add them together in the order of A + B, then the
    resulting new filter will check A first, then B, and if both of the filters
    return True, then the new filter will return True.
    """

    def __init__(
        self,
        subject_pattern: Optional[str] = None,
        sender_pattern: Optional[str] = None,
        body_pattern: Optional[str] = None,
        tags: Optional[List[str]] = None,
        func: Optional[Callable[[EmailMessage], bool]] = None,
        match_all: bool = True,
    ):
        # Validate and compile regex patterns immediately
        self.subject_pattern = None
        self.sender_pattern = None
        self.body_pattern = None

        if subject_pattern:
            try:
                self.subject_pattern = re.compile(subject_pattern)
            except re.error as e:
                raise re.error(f"Invalid subject pattern: {e}")

        if sender_pattern:
            try:
                self.sender_pattern = re.compile(sender_pattern)
            except re.error as e:
                raise re.error(f"Invalid sender pattern: {e}")

        if body_pattern:
            try:
                self.body_pattern = re.compile(body_pattern)
            except re.error as e:
                raise re.error(f"Invalid body pattern: {e}")

        self.tags = [t.lower() for t in tags or []]
        self.func = func
        self.match_all = match_all

    def __call__(self, message: EmailMessage) -> bool:
        checks = []

        # Check subject pattern
        if self.subject_pattern is not None:
            if message.subject is None:
                checks.append(False)
            else:
                checks.append(
                    bool(self.subject_pattern.search(message.subject))
                )

        # Check sender pattern
        if self.sender_pattern is not None:
            if message.sender is None:
                checks.append(False)
            else:
                checks.append(bool(self.sender_pattern.search(message.sender)))

        # Check body pattern
        if self.body_pattern is not None:
            if message.body is None:
                checks.append(False)
            else:
                checks.append(bool(self.body_pattern.search(message.body)))

        # Check tags
        if self.tags:
            checks.append(any(tag.lower() in message.tags for tag in self.tags))

        # Check custom function
        if self.func is not None:
            try:
                checks.append(bool(self.func(message)))
            except Exception:
                checks.append(False)

        if not checks:
            return True

        return all(checks) if self.match_all else any(checks)

    def __add__(self, other):
        if not isinstance(other, (EmailFilter, Callable)):
            raise TypeError(f"Cannot combine EmailFilter with {type(other)}")
        return CombinedEmailFilter([self, other])


class CombinedEmailFilter:
    def __init__(
        self, filters: List[Union[EmailFilter, Callable[[EmailMessage], bool]]]
    ):
        self.__filters = []
        for f in filters:
            if isinstance(f, EmailFilter):
                self.__filters.append(f)
            elif isinstance(f, Callable):
                self.__filters.append(EmailFilter(func=f))
            else:
                raise TypeError(f"Invalid filter type: {type(f)}")

    def __call__(self, message: EmailMessage) -> bool:
        return all(f(message) for f in self.__filters)

    def __add__(self, other):
        if not isinstance(other, (EmailFilter, Callable, CombinedEmailFilter)):
            raise TypeError(f"Cannot combine with {type(other)}")

        new_filters = self.__filters.copy()
        if isinstance(other, CombinedEmailFilter):
            new_filters.extend(other.__filters)
        elif isinstance(other, EmailFilter):
            new_filters.append(other)
        elif isinstance(other, Callable):
            new_filters.append(EmailFilter(func=other))

        return CombinedEmailFilter(new_filters)


class Inbox:
    """
    Monitors incoming emails and triggers tools when matching emails are found.

    Basic usage:
    ```python
    # Create monitor checking every 5 minutes
    inbox = Inbox(
        username="user@example.com",
        password="pass",
        service="gmail",
        check_every="5:minutes"
    )

    # Add filter and associated tools
    inbox.add_filter(
        EmailFilter(subject_pattern="Important:.*"),
        tools=[notification_tool]
    )

    # Start monitoring
    inbox.start()

    # Add another filter while running
    inbox.add_filter(
        EmailFilter(sender_pattern="boss@company.com"),
        tools=[urgent_tool]
    )

    # Stop monitoring
    inbox.stop()
    ```
    """

    # Common IMAP servers
    COMMON_IMAP_SERVERS = {
        "gmail": "imap.gmail.com",
        "outlook": "outlook.office365.com",
        "yahoo": "imap.mail.yahoo.com",
        "aol": "imap.aol.com",
        "icloud": "imap.mail.me.com",
    }

    def __init__(
        self,
        call_when: Dict[
            Union[List, EmailFilter, Callable[[EmailMessage], bool]],
            Union[Tool, List[Tool]],
        ] = {},
        username: Optional[Union[str, dict]] = None,
        password: Optional[Union[str, dict]] = None,
        service: Optional[str] = None,
        imap_host: Optional[str] = None,
        check_every: Union[str, Interval] = "5:minutes",
        env_prefix: str = "EMAIL",
        folders: Optional[List[str]] = None,
        store: Optional[SeenMessageStore] = None,
        ignore_emails_older_than: Optional[datetime] = None,
        max_messages_to_process: Optional[int] = None,
        use_ssl: bool = True,
    ):
        self.username = self._load_credential(
            username, f"{env_prefix}_USERNAME"
        )
        self.password = self._load_credential(
            password, f"{env_prefix}_PASSWORD"
        )
        self.__use_ssl = use_ssl

        if store:
            self.__seen_msg_store = store
        else:
            file_location = f"{env_prefix}_SEEN_MESSAGES.json"
            print(
                f"No store provided, defaulting to file store {file_location}"
            )
            self.__seen_msg_store = FileSeenMessageStore(file_location)

        # Set up IMAP host
        if imap_host:
            self.imap_host = imap_host
        elif service:
            if service not in self.COMMON_IMAP_SERVERS:
                raise ValueError(f"Unknown email service: {service}")
            self.imap_host = self.COMMON_IMAP_SERVERS[service]
        else:
            self.imap_host = os.getenv(f"{env_prefix}_IMAP_HOST")
            if not self.imap_host:
                raise ValueError("IMAP host not provided")

        # Set up interval
        if isinstance(check_every, str):
            self.interval = Interval(datetime.now(), recur_every=check_every)
        else:
            self.interval = check_every

        self.__tools: Dict[str, Tool] = {}
        self.__call_when: Dict[EmailFilter, List[str]] = {}

        for filters, tools in call_when.items():
            # Convert everything to a singular EmailFilter
            if isinstance(filters, List):
                filter = None
                for filter in filters:
                    if isinstance(filter, EmailFilter):
                        if filter:
                            filter += filter
                        else:
                            filter = filter
                    elif callable(filter):
                        filter += EmailFilter(func=filter)
                    else:
                        raise ValueError(f"Unknown filter type: {type(filter)}")
            elif isinstance(filters, EmailFilter):
                filter = filters
            elif callable(filters):
                filter = EmailFilter(func=filters)
            else:
                raise ValueError(f"Unknown filter type: {type(filters)}")

            if isinstance(tools, Tool):
                tools = [tools]

            self.__call_when[filter] = [t.tname for t in tools]
            for tool in tools:
                self.__tools[tool.tname] = tool

        self.__folders: List[str] = []
        if folders:
            self.__folders = folders
        else:
            self.__folders = ["INBOX"]

        self.__listeners: Dict[str, List[Callable]] = {
            "send": [],
            "error": [],
        }
        self.__threadpool = ThreadPoolExecutor()

        self.__ignore_emails_older_than = ignore_emails_older_than
        if self.__ignore_emails_older_than is None:
            # We default to the last 48 hours if not specified
            # to prevent people accidentally pulling years of emails.
            self.__ignore_emails_older_than = datetime.now() - timedelta(
                hours=48
            )

        self.__max_messages_to_process = max_messages_to_process

        self.__running = False
        self.__lock = Lock()
        self.__thread = Thread(target=self.__run)
        self.__thread.daemon = True
        self.__thread.start()

    def _load_credential(
        self,
        value: Optional[Union[str, dict]],
        env_var: str,
        required: bool = True,
    ) -> Optional[str]:
        """Load a credential from various sources."""
        if isinstance(value, str):
            return value
        if isinstance(value, dict) and "env" in value:
            value = os.getenv(value["env"])
        else:
            value = os.getenv(env_var)

        if required and not value:
            raise ValueError(
                f"Required credential not provided: direct value, "
                f"dict with 'env', or environment variable {env_var}"
            )
        return value

    def add_listener(self, on: str, listener: Callable):
        """
        Add a listener to the inbox, either triggering
        when an email is sent or when an error occurs.

        on can either be "send" or "error".

        If on is "send", then the listener will follow the
        type of func(EmailMessage, Filter, Context).

        If the on is "error", then the listener will follow the type of
        func(Exception).
        """
        with self.__lock:
            if on not in self.__listeners:
                raise ValueError(f"Unknown listener type: {on}")
            self.__listeners[on].append(listener)

    def add_filter(
        self,
        filter: Union[EmailFilter, Callable[[EmailMessage], bool], List],
        tools: Union[Tool, List[Tool]],
    ):
        """
        Add a new filter and associated tools to the inbox.

        Args:
            filter: An EmailFilter, callable function, or list of filters
            tools: A single Tool or list of Tool objects to trigger when filter matches
        """
        if isinstance(tools, Tool):
            tools = [tools]

        # Convert to EmailFilter if needed
        if isinstance(filter, List):
            email_filter = None
            for f in filter:
                if isinstance(f, EmailFilter):
                    if email_filter:
                        email_filter += f
                    else:
                        email_filter = f
                elif callable(f):
                    if email_filter:
                        email_filter += EmailFilter(func=f)
                    else:
                        email_filter = EmailFilter(func=f)
                else:
                    raise ValueError(f"Unknown filter type: {type(f)}")
        elif isinstance(filter, EmailFilter):
            email_filter = filter
        elif callable(filter):
            email_filter = EmailFilter(func=filter)
        else:
            raise ValueError(f"Unknown filter type: {type(filter)}")

        with self.__lock:
            # Add tools to the filter
            tool_names = [t.tname for t in tools]
            if email_filter in self.__call_when:
                self.__call_when[email_filter].extend(tool_names)
            else:
                self.__call_when[email_filter] = tool_names

            # Add tools to the tools dictionary
            for tool in tools:
                self.__tools[tool.tname] = tool

    def start(self):
        """Start monitoring emails."""
        with self.__lock:
            self.__running = True

    def stop(self):
        """Stop monitoring emails."""
        with self.__lock:
            self.__running = False

    def __del__(self):
        if hasattr(self, "_Inbox__lock"):
            self.stop()
        if hasattr(self, "_Inbox__thread"):
            self.__thread.join()
        if hasattr(self, "_Inbox__threadpool"):
            self.__threadpool.shutdown(wait=True)

    def _check_emails(self):
        """Check for new emails and process them."""
        try:
            # Split host and port if provided in format "host:port"
            if ":" in self.imap_host:
                host, port = self.imap_host.split(":")
                port = int(port)
            else:
                host = self.imap_host
                port = 993 if self.__use_ssl else 143

            imap_class = imaplib.IMAP4_SSL if self.__use_ssl else imaplib.IMAP4
            with imap_class(host, port) as imap:
                imap.login(self.username, self.password)

                messages: List[EmailMessage] = []
                for folder in self.__folders:
                    try:
                        imap.select(folder)
                    except imaplib.IMAP4.error as e:
                        print(f"Error selecting folder {folder}: {e}")
                        continue

                    filter = ""
                    if self.__ignore_emails_older_than:
                        date_str = self.__ignore_emails_older_than.strftime(
                            "%d-%b-%Y"
                        )
                        filter += f'SINCE "{date_str}"'
                    if self.__max_messages_to_process:
                        filter += f"1:{self.__max_messages_to_process}"
                    if filter == "":
                        filter = "ALL"
                    _, message_numbers = imap.search(None, filter)

                    for num in message_numbers[0].split():
                        _, msg_data = imap.fetch(num, "(RFC822)")
                        email_body = msg_data[0][1]
                        msg = email.message_from_bytes(email_body)
                        message = EmailMessage.from_message(msg)

                        # Skip if we've seen this message before
                        if self.__seen_msg_store.contains(message):
                            continue
                        else:
                            messages.append(message)

                for msg in messages:
                    self.__seen_msg_store.add(msg)

                    # Check against filters and trigger tools
                    with self.__lock:
                        for email_filter, tools in self.__call_when.items():
                            if email_filter(msg):
                                for name in tools:
                                    tool = self.__tools[name]
                                    # ctx = tool.async_call(msg)
                                    ctx = None
                                    tool(msg)

                                # Trigger listeners
                                for listener in self.__listeners["send"]:
                                    self.__trigger_listener(
                                        listener, msg, email_filter, ctx
                                    )

        except Exception as e:
            trace = traceback.format_exc()
            print(f"Error checking emails: {str(e)}")
            print(trace)

            # Trigger error listeners
            with self.__lock:
                for listener in self.__listeners["error"]:
                    self.__trigger_listener(listener, e)

    def __trigger_listener(self, func: callable, **args):
        """
        Async fire off the listener
        """
        self.__threadpool.submit(func, **args)

    def __run(self):
        """Main monitoring loop."""
        while True:
            sleep(0.1)
            with self.__lock:
                if not self.__running:
                    continue

                check = self.interval.trigger_at <= datetime.now()

            if check:
                self._check_emails()
                self.interval.trigger()
