import threading
import time

import pytest

from arkaine.tools.datastore import ThreadSafeDataStore


def test_initialization():
    store = ThreadSafeDataStore()
    assert len(store) == 0


def test_set_get_item():
    store = ThreadSafeDataStore()
    store["key1"] = "value1"
    assert store["key1"] == "value1"


def test_contains():
    store = ThreadSafeDataStore()
    store["key1"] = "value1"
    assert "key1" in store
    assert "key2" not in store


def test_delete_item():
    store = ThreadSafeDataStore()
    store["key1"] = "value1"
    del store["key1"]
    assert "key1" not in store


def test_operate():
    store = ThreadSafeDataStore()
    store["key1"] = 1
    store.operate("key1", lambda x: x + 1)
    assert store["key1"] == 2


def test_update():
    store = ThreadSafeDataStore()
    store["key1"] = 1
    new_value = store.update("key1", lambda x: x * 2)
    assert new_value == 2
    assert store["key1"] == 2


def test_increment():
    store = ThreadSafeDataStore()
    store["key1"] = 1
    store.increment("key1", 5)
    assert store["key1"] == 6


def test_decrement():
    store = ThreadSafeDataStore()
    store["key1"] = 5
    store.decrement("key1", 2)
    assert store["key1"] == 3


def test_append():
    store = ThreadSafeDataStore()
    store["key1"] = []
    store.append("key1", "value1")
    assert store["key1"] == ["value1"]


def test_thread_safety_increment():
    store = ThreadSafeDataStore()
    store["key1"] = 0

    def increment():
        for _ in range(1000):
            store.increment("key1", 1)

    threads = [threading.Thread(target=increment) for _ in range(10)]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    assert store["key1"] == 10000  # 10 threads * 1000 increments


def test_thread_safety_decrement():
    store = ThreadSafeDataStore()
    store["key1"] = 10000

    def decrement():
        for _ in range(1000):
            store.decrement("key1", 1)

    threads = [threading.Thread(target=decrement) for _ in range(10)]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    assert store["key1"] == 0  # 10 threads * 1000 decrements


def test_thread_safety_set_get():
    store = ThreadSafeDataStore()

    def set_items():
        for i in range(1000):
            store[f"key{i}"] = i

    def get_items():
        for i in range(1000):
            assert store[f"key{i}"] == i

    set_thread = threading.Thread(target=set_items)
    get_thread = threading.Thread(target=get_items)

    set_thread.start()
    get_thread.start()

    set_thread.join()
    get_thread.join()


def test_nested_keys():
    store = ThreadSafeDataStore()
    store["key1"] = {"subkey1": 1, "subkey2": {"subsubkey1": 2}}

    def update_nested():
        store.operate(
            ["key1", "subkey2"], lambda x: {"subsubkey1": x["subsubkey1"] + 1}
        )

    def get_nested():
        # Wait until the value is updated to 3
        for _ in range(10):  # Retry for a few seconds
            if store["key1"]["subkey2"]["subsubkey1"] == 3:
                return
            time.sleep(0.1)  # Sleep briefly before retrying

    update_thread = threading.Thread(target=update_nested)
    get_thread = threading.Thread(target=get_nested)

    update_thread.start()
    get_thread.start()

    update_thread.join()
    get_thread.join()

    assert store["key1"]["subkey2"]["subsubkey1"] == 3
