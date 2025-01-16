import socket
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Lock, Thread
from time import sleep
from typing import Dict, List, Optional, Union

import pytest

from arkaine.connectors.inbox import (
    EmailFilter,
    EmailMessage,
    FileSeenMessageStore,
    Inbox,
)
from arkaine.tools.argument import Argument
from arkaine.tools.tool import Tool


class FakeIMAPServer:

    def __init__(self, port: Optional[int] = None, users: Dict[str, str] = {}):
        if port:
            self.port = port
        else:
            with socket.socket() as s:
                s.bind(("", 0))
                self.port = s.getsockname()[1]

        self.users = users

        self.__lock = Lock()

        self.inboxes: Dict[str, List[EmailMessage]] = {}

        for user in self.users:
            self.inboxes[user] = []

        self.__running = False
        self.__listen_thread: Optional[Thread] = None
        self.__client_threadpool = ThreadPoolExecutor()

    def add_user(self, username: str, password: str):
        with self.__lock:
            self.users[username] = password
            self.inboxes[username] = []

    def add_messages(
        self, username, messages: Union[EmailMessage, List[EmailMessage]]
    ):
        with self.__lock:
            if isinstance(messages, EmailMessage):
                messages = [messages]
            [self.inboxes[username].append(msg) for msg in messages]

    def start(self):
        with self.__lock:
            if self.__running:
                return
            self.__running = True
            self.__listen_thread = Thread(target=self.__listen)
            self.__listen_thread.start()

    def stop(self):
        with self.__lock:
            if not self.__running:
                return
            self.__running = False
        self.__listen_thread.join()
        self.__listen_thread = None
        self.__client_threadpool.shutdown()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self):
        self.stop()

    def __del__(self):
        self.stop()

    def __listen(self):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind(("localhost", self.port))
        server_socket.listen(5)

        while True:
            try:
                server_socket.settimeout(
                    1.0
                )  # Allow checking __running periodically
                client, address = server_socket.accept()

                # Handle client connection in a new thread
                Thread(target=self.__handle_client, args=(client,)).start()

            except socket.timeout:
                continue
            except Exception as e:
                if (
                    self.__running
                ):  # Only log if we're still meant to be running
                    print(f"Error in IMAP server: {e}")
            finally:
                with self.__lock:
                    if not self.__running:
                        break
                sleep(0.1)

        server_socket.close()

    def __handle_client(self, client_socket):
        """Handle individual IMAP client connections"""
        try:
            # Send initial greeting
            client_socket.send(
                b"* OK [CAPABILITY IMAP4rev1] Mock Server Ready\r\n"
            )

            authenticated_user = None
            selected_mailbox = None

            while self.__running:
                try:
                    data = client_socket.recv(1024).decode("utf-8")
                    if not data:
                        break

                    # Parse command
                    parts = data.strip().split(" ")
                    tag = parts[0]
                    command = parts[1].upper() if len(parts) > 1 else ""

                    # Handle CAPABILITY command
                    if command == "CAPABILITY":
                        client_socket.send(
                            f"* CAPABILITY IMAP4rev1 AUTH=PLAIN\r\n{tag} OK CAPABILITY completed\r\n".encode()
                        )

                    # Handle LOGIN command
                    elif command == "LOGIN":
                        username = parts[2].strip('"')
                        password = parts[3].strip('"')

                        if (
                            username in self.users
                            and self.users[username] == password
                        ):
                            authenticated_user = username
                            client_socket.send(
                                f"{tag} OK [CAPABILITY IMAP4rev1] LOGIN completed\r\n".encode()
                            )
                        else:
                            client_socket.send(
                                f"{tag} NO LOGIN failed\r\n".encode()
                            )

                    # Handle SELECT command
                    elif command == "SELECT":
                        if not authenticated_user:
                            client_socket.send(
                                f"{tag} NO Not authenticated\r\n".encode()
                            )
                            continue

                        mailbox = parts[2].strip('"')
                        if mailbox.upper() == "INBOX":
                            selected_mailbox = "INBOX"
                            messages = self.inboxes[authenticated_user]
                            client_socket.send(
                                f"* {len(messages)} EXISTS\r\n".encode()
                            )
                            client_socket.send(f"* 0 RECENT\r\n".encode())
                            client_socket.send(
                                f"* OK [UIDVALIDITY 1] UIDs valid\r\n".encode()
                            )
                            client_socket.send(
                                f"{tag} OK [READ-WRITE] SELECT completed\r\n".encode()
                            )
                        else:
                            client_socket.send(
                                f"{tag} NO Mailbox does not exist\r\n".encode()
                            )

                    # Handle SEARCH command
                    elif command == "SEARCH":
                        if not authenticated_user or not selected_mailbox:
                            client_socket.send(
                                f"{tag} NO Select a mailbox first\r\n".encode()
                            )
                            continue

                        # Return all message sequence numbers for now
                        messages = self.inboxes[authenticated_user]
                        sequence_numbers = " ".join(
                            str(i + 1) for i in range(len(messages))
                        )
                        client_socket.send(
                            f"* SEARCH {sequence_numbers}\r\n".encode()
                        )
                        client_socket.send(
                            f"{tag} OK SEARCH completed\r\n".encode()
                        )

                    # Handle FETCH command
                    elif command == "FETCH":
                        if not authenticated_user or not selected_mailbox:
                            client_socket.send(
                                f"{tag} NO Select a mailbox first\r\n".encode()
                            )
                            continue

                        # Parse the message number from the FETCH command
                        msg_num = int(parts[2]) - 1  # Convert to 0-based index
                        messages = self.inboxes[authenticated_user]

                        if msg_num >= len(messages):
                            client_socket.send(
                                f"{tag} NO Message not found\r\n".encode()
                            )
                            continue

                        message = messages[msg_num]

                        # Format the date according to RFC 2822
                        formatted_date = message.received_at.strftime(
                            "%a, %d %b %Y %H:%M:%S %z"
                        )
                        if not formatted_date.endswith("+0000"):
                            formatted_date += " +0000"

                        # Create RFC822 formatted message
                        email_content = (
                            f"From: {message.sender}\r\n"
                            f"Subject: {message.subject}\r\n"
                            f"Date: {formatted_date}\r\n"
                            f"Message-ID: {message.message_id}\r\n"
                            f"\r\n"
                            f"{message.body}\r\n"
                        ).encode()

                        # Send the message data in IMAP format
                        # First send the message size
                        size = len(email_content)
                        client_socket.send(
                            f"* {msg_num + 1} FETCH (RFC822 {{{size}}}\r\n".encode()
                        )
                        # Then send the actual message
                        client_socket.send(email_content)
                        # End with closing parenthesis and OK response
                        client_socket.send(b")\r\n")
                        client_socket.send(
                            f"{tag} OK FETCH completed\r\n".encode()
                        )

                    # Handle LOGOUT command
                    elif command == "LOGOUT":
                        client_socket.send(
                            f"* BYE IMAP4rev1 Server logging out\r\n{tag} OK LOGOUT completed\r\n".encode()
                        )
                        break

                    else:
                        client_socket.send(
                            f"{tag} BAD Command not recognized\r\n".encode()
                        )

                except socket.timeout:
                    continue

        except Exception as e:
            print(f"Error handling client: {e}")
        finally:
            client_socket.close()


@pytest.fixture
def fake_imap_server():
    server = FakeIMAPServer()
    server.add_user("test@example.com", "password123")
    server.start()
    yield server
    server.stop()


@pytest.fixture
def test_inbox(fake_imap_server, tmp_path):
    # Create a temporary file for seen messages
    seen_messages_file = tmp_path / "seen_messages.json"
    store = FileSeenMessageStore(str(seen_messages_file))

    # Create a simple notification tool for testing
    class NotificationTool(Tool):
        def __init__(self):
            self.notifications = []

            super().__init__(
                name="notification_tool",
                description="",
                args=[
                    Argument(
                        name="message",
                        description="The message to notify about",
                        type=EmailMessage,
                    ),
                ],
                func=self.notify,
            )

        def notify(self, message: EmailMessage):
            self.notifications.append(message)

    notification_tool = NotificationTool()

    # Create inbox instance
    inbox = Inbox(
        call_when={EmailFilter(subject_pattern="Test:"): notification_tool},
        username="test@example.com",
        password="password123",
        imap_host=f"localhost:{fake_imap_server.port}",
        check_every="1:seconds",  # Fast checking for tests
        store=store,
        use_ssl=False,  # Disable SSL for testing
    )

    yield inbox, notification_tool
    inbox.stop()


def test_inbox_basic_functionality(fake_imap_server, test_inbox):
    inbox, notification_tool = test_inbox

    # Add a test message
    test_message = EmailMessage(
        subject="Test: Hello",
        sender="sender@example.com",
        body="Test message body",
        received_at=datetime.now(),
        message_id="test123",
    )

    try:
        fake_imap_server.add_messages("test@example.com", test_message)
    except Exception as e:
        raise e

    # Start the inbox
    inbox.start()

    # Wait for processing
    sleep(2)

    # Check if notification tool received the message
    assert len(notification_tool.notifications) == 1
    assert notification_tool.notifications[0].subject == "Test: Hello"


def test_inbox_filter_no_match(fake_imap_server, test_inbox):
    inbox, notification_tool = test_inbox

    # Add a message that shouldn't match the filter
    test_message = EmailMessage(
        subject="No Match",
        sender="sender@example.com",
        body="Test message body",
        received_at=datetime.now(),
        message_id="test123",
    )

    fake_imap_server.add_messages("test@example.com", test_message)

    # Start the inbox
    inbox.start()

    # Wait for processing
    sleep(2)

    # Check that notification tool didn't receive the message
    assert len(notification_tool.notifications) == 0


def test_inbox_multiple_filters(fake_imap_server, tmp_path):
    # Create a temporary file for seen messages
    seen_messages_file = tmp_path / "seen_messages.json"
    store = FileSeenMessageStore(str(seen_messages_file))

    # Create two different tools for testing
    class TestTool(Tool):
        def __init__(self, name):
            super().__init__(
                name=name,
                description="",
                args=[
                    Argument(
                        name="message",
                        description="The message to append",
                        type=EmailMessage,
                    )
                ],
                func=self.append,
            )

            self.messages = []

        def append(self, message: EmailMessage):
            self.messages.append(message)

    subject_tool = TestTool("subject_tool")
    sender_tool = TestTool("sender_tool")

    # Create inbox with multiple filters
    inbox = Inbox(
        call_when={
            EmailFilter(subject_pattern="Test:"): subject_tool,
            EmailFilter(sender_pattern="important@example.com"): sender_tool,
        },
        username="test@example.com",
        password="password123",
        imap_host=f"localhost:{fake_imap_server.port}",
        check_every="1:seconds",
        store=store,
        use_ssl=False,
    )

    # Add test messages
    messages = [
        EmailMessage(
            subject="Test: Hello",
            sender="random@example.com",
            body="Test message 1",
            received_at=datetime.now(),
            message_id="test1",
        ),
        EmailMessage(
            subject="Regular Subject",
            sender="important@example.com",
            body="Test message 2",
            received_at=datetime.now(),
            message_id="test2",
        ),
    ]

    fake_imap_server.add_messages("test@example.com", messages)

    # Start the inbox
    inbox.start()

    # Wait for processing
    sleep(2)

    # Check that each tool received the correct message
    assert len(subject_tool.messages) == 1
    assert subject_tool.messages[0].subject == "Test: Hello"

    assert len(sender_tool.messages) == 1
    assert sender_tool.messages[0].sender == "important@example.com"

    inbox.stop()


def test_inbox_seen_messages(fake_imap_server, test_inbox):
    inbox, notification_tool = test_inbox

    # Add a test message
    test_message = EmailMessage(
        subject="Test: Hello",
        sender="sender@example.com",
        body="Test message body",
        received_at=datetime.now(),
        message_id="test123",
    )

    fake_imap_server.add_messages("test@example.com", test_message)

    # Start the inbox
    inbox.start()

    # Wait for first processing
    sleep(2)

    # Add the same message again
    fake_imap_server.add_messages("test@example.com", test_message)

    # Wait for second processing
    sleep(2)

    # Check that notification tool only received the message once
    assert len(notification_tool.notifications) == 1


def test_inbox_body_filter(fake_imap_server, tmp_path):
    """Test filtering emails based on body content"""
    seen_messages_file = tmp_path / "seen_messages.json"
    store = FileSeenMessageStore(str(seen_messages_file))

    class BodyTool(Tool):
        def __init__(self):
            self.messages = []
            super().__init__(
                name="body_tool",
                description="",
                args=[
                    Argument(name="message", description="", type=EmailMessage)
                ],
                func=self.append,
            )

        def append(self, message: EmailMessage):
            self.messages.append(message)

    body_tool = BodyTool()

    inbox = Inbox(
        call_when={EmailFilter(body_pattern="URGENT"): body_tool},
        username="test@example.com",
        password="password123",
        imap_host=f"localhost:{fake_imap_server.port}",
        check_every="1:seconds",
        store=store,
        use_ssl=False,
    )

    # Add test messages
    messages = [
        EmailMessage(
            subject="Regular Subject",
            sender="sender@example.com",
            body="This is URGENT and important",
            received_at=datetime.now(),
            message_id="test1",
        ),
        EmailMessage(
            subject="Another Subject",
            sender="sender@example.com",
            body="Not urgent message",
            received_at=datetime.now(),
            message_id="test2",
        ),
    ]

    fake_imap_server.add_messages("test@example.com", messages)
    inbox.start()
    sleep(2)

    assert len(body_tool.messages) == 1
    assert "URGENT" in body_tool.messages[0].body
    inbox.stop()


def test_inbox_combined_filters(fake_imap_server, tmp_path):
    """Test combining multiple filters with + operator"""
    seen_messages_file = tmp_path / "seen_messages.json"
    store = FileSeenMessageStore(str(seen_messages_file))

    class CombinedTool(Tool):
        def __init__(self):
            self.messages = []
            super().__init__(
                name="combined_tool",
                description="",
                args=[
                    Argument(name="message", description="", type=EmailMessage)
                ],
                func=self.append,
            )

        def append(self, message: EmailMessage):
            self.messages.append(message)

    combined_tool = CombinedTool()

    # Combine filters using +
    filter1 = EmailFilter(subject_pattern="Test:")
    filter2 = EmailFilter(sender_pattern="important@example.com")
    combined_filter = filter1 + filter2

    inbox = Inbox(
        call_when={combined_filter: combined_tool},
        username="test@example.com",
        password="password123",
        imap_host=f"localhost:{fake_imap_server.port}",
        check_every="1:seconds",
        store=store,
        use_ssl=False,
    )

    messages = [
        EmailMessage(
            subject="Test: Important",
            sender="important@example.com",
            body="Should match both filters",
            received_at=datetime.now(),
            message_id="test1",
        ),
        EmailMessage(
            subject="Test: Regular",
            sender="regular@example.com",
            body="Should only match subject filter",
            received_at=datetime.now(),
            message_id="test2",
        ),
    ]

    fake_imap_server.add_messages("test@example.com", messages)
    inbox.start()
    sleep(2)

    # Only the message matching both filters should be processed
    assert len(combined_tool.messages) == 1
    assert combined_tool.messages[0].message_id == "test1"
    inbox.stop()


def test_inbox_custom_filter_function(fake_imap_server, tmp_path):
    """Test using a custom filter function"""
    seen_messages_file = tmp_path / "seen_messages.json"
    store = FileSeenMessageStore(str(seen_messages_file))

    class CustomTool(Tool):
        def __init__(self):
            self.messages = []
            super().__init__(
                name="custom_tool",
                description="",
                args=[
                    Argument(name="message", description="", type=EmailMessage)
                ],
                func=self.append,
            )

        def append(self, message: EmailMessage):
            self.messages.append(message)

    custom_tool = CustomTool()

    # Use the custom filter directly instead of wrapping in EmailFilter
    def custom_filter(message: EmailMessage) -> bool:
        # Custom logic: match emails with "urgent" in subject (case insensitive)
        return "urgent" in message.subject.lower()

    try:
        inbox = Inbox(
            call_when={custom_filter: custom_tool},  # Use filter directly
            username="test@example.com",
            password="password123",
            imap_host=f"localhost:{fake_imap_server.port}",
            check_every="1:seconds",
            store=store,
            use_ssl=False,
        )

        messages = [
            EmailMessage(
                subject="Urgent Meeting",
                sender="boss@example.com",
                body="Recent urgent message",
                received_at=datetime.now(),
                message_id="test1",
            ),
            EmailMessage(
                subject="Regular Update",
                sender="boss@example.com",
                body="Not urgent",
                received_at=datetime.now(),
                message_id="test2",
            ),
        ]

        fake_imap_server.add_messages("test@example.com", messages)
        inbox.start()
        sleep(2)

        assert len(custom_tool.messages) == 1
        assert custom_tool.messages[0].message_id == "test1"
    finally:
        inbox.stop()


def test_email_message_generate_id():
    """Test automatic message ID generation"""
    msg = EmailMessage(
        subject="Test",
        sender="test@example.com",
        body="Test body",
        received_at=datetime.now(),
        message_id="",
    )

    assert msg.message_id != ""
    assert isinstance(msg.message_id, str)
    assert len(msg.message_id) == 64  # SHA-256 hash length


def test_email_message_json_serialization():
    """Test JSON serialization/deserialization"""
    now = datetime.now()
    original = EmailMessage(
        subject="Test",
        sender="test@example.com",
        body="Test body",
        received_at=now,
        message_id="test123",
        tags=["important", "test"],
    )

    json_str = EmailMessage.to_json(original)
    restored = EmailMessage.from_json(json_str)

    assert restored.subject == original.subject
    assert restored.sender == original.sender
    assert restored.body == original.body
    assert restored.message_id == original.message_id
    assert restored.tags == original.tags
    assert restored.received_at.isoformat() == original.received_at.isoformat()


def test_email_message_string_conversion():
    """Test string conversion and parsing"""
    now = datetime(2024, 1, 1, 12, 0, 0)
    original = EmailMessage(
        subject="Test",
        sender="test@example.com",
        body="Test body",
        received_at=now,
        message_id="test123",
        tags=["important", "test"],
    )

    str_repr = str(original)
    restored = EmailMessage.from_str(str_repr)

    assert restored.subject == original.subject
    assert restored.sender == original.sender
    assert restored.body == original.body
    assert restored.message_id == original.message_id
    assert restored.tags == original.tags
    assert restored.received_at == original.received_at


def test_email_message_empty_tags():
    """Test handling of empty tags"""
    now = datetime(2024, 1, 1, 12, 0, 0)  # No microseconds
    original = EmailMessage(
        subject="Test",
        sender="test@example.com",
        body="Test body",
        received_at=now,
        message_id="test123",
        tags=[],
    )

    str_repr = str(original)
    restored = EmailMessage.from_str(str_repr)
    assert restored.tags == []
    assert restored.received_at == original.received_at


def test_email_filter_patterns():
    """Test various pattern matching in EmailFilter"""
    msg = EmailMessage(
        subject="Important: Test Message",
        sender="boss@example.com",
        body="This is urgent!",
        received_at=datetime.now(),
        message_id="test123",
    )

    # Test subject pattern
    subject_filter = EmailFilter(subject_pattern=r"Important:.*")
    assert subject_filter(msg) == True

    # Test sender pattern
    sender_filter = EmailFilter(sender_pattern=r".*@example\.com")
    assert sender_filter(msg) == True

    # Test body pattern
    body_filter = EmailFilter(body_pattern=r"urgent")
    assert body_filter(msg) == True

    # Test non-matching patterns
    non_match = EmailFilter(subject_pattern=r"Urgent:.*")
    assert non_match(msg) == False


def test_email_filter_combination():
    """Test combining filters with + operator"""
    msg = EmailMessage(
        subject="Important: Test",
        sender="boss@example.com",
        body="Test body",
        received_at=datetime.now(),
        message_id="test123",
    )

    filter1 = EmailFilter(subject_pattern=r"Important:.*")
    filter2 = EmailFilter(sender_pattern=r"boss@.*")

    combined = filter1 + filter2
    assert combined(msg) == True

    # Test with non-matching second filter
    filter3 = EmailFilter(body_pattern=r"urgent")
    combined_non_match = filter1 + filter3
    assert combined_non_match(msg) == False


def test_email_filter_match_all_flag():
    """Test the match_all flag in EmailFilter"""
    msg = EmailMessage(
        subject="Important: Test",
        sender="boss@example.com",
        body="Test body",
        received_at=datetime.now(),
        message_id="test123",
    )

    # Test with match_all=True (default)
    filter_all = EmailFilter(
        subject_pattern=r"Important:.*", body_pattern=r"urgent", match_all=True
    )
    assert filter_all(msg) == False

    # Test with match_all=False
    filter_any = EmailFilter(
        subject_pattern=r"Important:.*", body_pattern=r"urgent", match_all=False
    )
    assert filter_any(msg) == True


def test_file_seen_store_basic(tmp_path):
    """Test basic functionality of FileSeenMessageStore"""
    store_file = tmp_path / "seen_messages.txt"
    store = FileSeenMessageStore(str(store_file))

    msg = EmailMessage(
        subject="Test",
        sender="test@example.com",
        body="Test body",
        received_at=datetime(2024, 1, 1, 12, 0, 0),
        message_id="test123",
    )

    # Test adding and checking messages
    assert store.contains(msg) == False
    store.add(msg)
    assert store.contains(msg) == True
    assert store.contains("test123") == True  # Test with message_id string


def test_file_seen_store_persistence(tmp_path):
    """Test that messages persist between store instances"""
    store_file = tmp_path / "seen_messages.txt"

    # First store instance
    store1 = FileSeenMessageStore(str(store_file))
    msg = EmailMessage(
        subject="Test",
        sender="test@example.com",
        body="Test body",
        received_at=datetime(2024, 1, 1, 12, 0, 0),
        message_id="test123",
    )
    store1.add(msg)

    # Second store instance should see the same messages
    store2 = FileSeenMessageStore(str(store_file))
    assert store2.contains(msg) == True
    assert store2.contains("test123") == True


def test_file_seen_store_multiple_messages(tmp_path):
    """Test handling multiple messages"""
    store_file = tmp_path / "seen_messages.txt"
    store = FileSeenMessageStore(str(store_file))

    messages = [
        EmailMessage(
            subject=f"Test {i}",
            sender="test@example.com",
            body=f"Test body {i}",
            received_at=datetime(2024, 1, 1, 12, 0, 0),
            message_id=f"test{i}",
        )
        for i in range(3)
    ]

    # Add all messages
    for msg in messages:
        store.add(msg)

    # Verify all messages are contained
    for msg in messages:
        assert store.contains(msg) == True
        assert store.contains(msg.message_id) == True


def test_file_seen_store_empty_file(tmp_path):
    """Test behavior with empty file"""
    store_file = tmp_path / "seen_messages.txt"
    store_file.write_text("")  # Create empty file

    store = FileSeenMessageStore(str(store_file))
    msg = EmailMessage(
        subject="Test",
        sender="test@example.com",
        body="Test body",
        received_at=datetime(2024, 1, 1, 12, 0, 0),
        message_id="test123",
    )

    assert store.contains(msg) == False
    store.add(msg)
    assert store.contains(msg) == True


def test_file_seen_store_concurrent_access(tmp_path):
    """Test concurrent access to the store"""
    store_file = tmp_path / "seen_messages.txt"
    store = FileSeenMessageStore(str(store_file))

    messages = [
        EmailMessage(
            subject=f"Test {i}",
            sender="test@example.com",
            body=f"Test body {i}",
            received_at=datetime(2024, 1, 1, 12, 0, 0),
            message_id=f"test{i}",
        )
        for i in range(10)
    ]

    def add_and_check(msg):
        store.add(msg)
        assert store.contains(msg) == True

    # Create threads to add messages concurrently
    threads = [Thread(target=add_and_check, args=(msg,)) for msg in messages]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Verify all messages were added
    for msg in messages:
        assert store.contains(msg) == True
