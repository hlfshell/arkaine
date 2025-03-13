import pytest

from arkaine.internal.json import (
    SerialWrapper,
    recursive_from_json,
    recursive_to_json,
)
from arkaine.llms.llm import LLM
from arkaine.utils.website import Website


@pytest.fixture
def mock_llm():
    class MockLLM(LLM):
        def __init__(self):
            super().__init__(
                name="mock_llm",
                id="mock-llm-id",
            )

        def context_length(self) -> int:
            return 4096

        def completion(self, prompt: str) -> str:
            return "Mocked response"

    return MockLLM()


# Test fixtures and helper classes
class Color:
    def __init__(self, r: int, g: int, b: int):
        self.r = r
        self.g = g
        self.b = b

    @classmethod
    def from_json(cls, data):
        return cls(**data)

    def to_json(self):
        return {"r": self.r, "g": self.g, "b": self.b}

    def __eq__(self, other):
        return self.r == other.r and self.g == other.g and self.b == other.b


class Person:
    def __init__(self, name: str, age: int):
        self.name = name
        self.age = age

    @classmethod
    def from_json(cls, data):
        return cls(**data)

    def to_json(self):
        return {"name": self.name, "age": self.age}

    def __eq__(self, other):
        return self.name == other.name and self.age == other.age


def test_serial_wrapper_basic():
    # Test with Enum
    color = Color(r=0, g=255, b=0)
    wrapper = SerialWrapper(color)
    json_data = wrapper.to_json()

    assert json_data["type"] == "Color"
    assert "test_json" in json_data["module"]
    assert json_data["value"] == {"r": 0, "g": 255, "b": 0}

    # Test reconstruction
    reconstructed = SerialWrapper.from_json(json_data)
    assert reconstructed.r == 0
    assert reconstructed.g == 255
    assert reconstructed.b == 0

    person = Person(name="Alice", age=30)
    wrapper = SerialWrapper(person)
    json_data = wrapper.to_json()

    assert json_data["type"] == "Person"
    assert json_data["value"] == {"name": "Alice", "age": 30}

    reconstructed = SerialWrapper.from_json(json_data)
    assert reconstructed.name == "Alice"
    assert reconstructed.age == 30


def test_is_serial_wrapper():
    # Test the is_serial_wrapper method
    mock_wrapper = {
        "type": "Test",
        "module": "test_module",
        "value": 42,
    }

    assert SerialWrapper.is_serial_wrapper(mock_wrapper) is True

    # Test with missing attributes
    incomplete = {
        "type": "Test",
        "module": "test_module",
    }
    assert SerialWrapper.is_serial_wrapper(incomplete) is False


def test_round_trip_serialization():
    # Test full serialization and deserialization cycle
    original = Person(name="Bob", age=25)
    wrapper = SerialWrapper(original)
    json_data = wrapper.to_json()
    reconstructed = SerialWrapper.from_json(json_data)

    assert reconstructed.name == original.name
    assert reconstructed.age == original.age


def test_serial_wrapper_with_website(mock_llm):
    website = Website(
        url="https://example.com",
    )

    wrapper = SerialWrapper(website)
    json_data = wrapper.to_json()
    reconstructed = SerialWrapper.from_json(json_data)

    assert reconstructed.url == website.url


def test_serial_wrapper_with_recursive_to_json():
    website = Website(
        url="https://example.com",
    )

    wrapper = SerialWrapper(website)
    json_data = wrapper.to_json()

    assert json_data["type"] == "Website"
    assert json_data["value"]["url"] == "https://example.com"

    reconstructed = SerialWrapper.from_json(json_data)
    assert reconstructed.url == website.url


def test_recursive_to_json_primitives():
    # Test primitive types
    assert recursive_to_json(42) == 42
    assert recursive_to_json("hello") == "hello"
    assert recursive_to_json(3.14) == 3.14
    assert recursive_to_json(True) is True
    assert recursive_to_json(None) is None


def test_recursive_to_json_collections():
    # Test lists
    assert recursive_to_json([1, 2, 3]) == [1, 2, 3]

    # Test nested lists
    assert recursive_to_json([1, [2, 3], 4]) == [1, [2, 3], 4]

    # Test dictionaries
    assert recursive_to_json({"a": 1, "b": 2}) == {"a": 1, "b": 2}

    # Test nested dictionaries
    assert recursive_to_json({"a": 1, "b": {"c": 3}}) == {"a": 1, "b": {"c": 3}}

    # Test mixed collections
    assert recursive_to_json({"a": [1, 2], "b": {"c": 3}}) == {
        "a": [1, 2],
        "b": {"c": 3},
    }


def test_recursive_to_json_custom_objects():
    # Test objects with to_json method
    color = Color(r=255, g=0, b=0)
    assert recursive_to_json(color) == {"r": 255, "g": 0, "b": 0}

    # Test nested objects with to_json method
    data = {
        "person": Person(name="John", age=25),
        "favorite_color": Color(r=0, g=0, b=255),
    }
    expected = {
        "person": {"name": "John", "age": 25},
        "favorite_color": {"r": 0, "g": 0, "b": 255},
    }
    assert recursive_to_json(data) == expected


def test_recursive_to_json_fallback():
    # Test objects without to_json method
    class NoJsonMethod:
        def __init__(self, value):
            self.value = value

    obj = NoJsonMethod(42)
    # Should convert to string representation
    assert isinstance(recursive_to_json(obj), str)


def test_recursive_from_json_primitives():
    # Test primitive types
    assert recursive_from_json(42) == 42
    assert recursive_from_json("hello") == "hello"
    assert recursive_from_json(3.14) == 3.14
    assert recursive_from_json(True) is True
    assert recursive_from_json(None) is None


def test_recursive_from_json_collections():
    # Test lists
    assert recursive_from_json([1, 2, 3]) == [1, 2, 3]

    # Test nested lists
    assert recursive_from_json([1, [2, 3], 4]) == [1, [2, 3], 4]

    # Test dictionaries
    assert recursive_from_json({"a": 1, "b": 2}) == {"a": 1, "b": 2}

    # Test nested dictionaries
    assert recursive_from_json({"a": 1, "b": {"c": 3}}) == {
        "a": 1,
        "b": {"c": 3},
    }

    # Test mixed collections
    assert recursive_from_json({"a": [1, 2], "b": {"c": 3}}) == {
        "a": [1, 2],
        "b": {"c": 3},
    }


def test_recursive_from_json_with_from_json_method():
    person = Person(name="John", age=25)
    color = Color(r=255, g=0, b=0)

    person_json = recursive_to_json(person, serial_wrap=True)
    color_json = recursive_to_json(color, serial_wrap=True)

    # This should call the from_json method on the mock object
    result = recursive_from_json(person_json)
    assert result == person

    result = recursive_from_json(color_json)
    assert result == color


def test_recursive_to_from_json_round_trip():
    # Test round trip conversion with nested structures
    original = {
        "name": "Test User",
        "age": 30,
        "colors": [Color(r=255, g=0, b=0), Color(r=0, g=255, b=0)],
        "details": {
            "address": "123 Test St",
            "contact": Person(name="Emergency Contact", age=45),
        },
    }

    # Convert to JSON-friendly format
    json_data = recursive_to_json(original)

    # Verify structure is as expected
    assert json_data["name"] == "Test User"
    assert json_data["age"] == 30
    assert len(json_data["colors"]) == 2
    assert json_data["colors"][0] == {"r": 255, "g": 0, "b": 0}
    assert json_data["details"]["contact"] == {
        "name": "Emergency Contact",
        "age": 45,
    }

    # Note: A complete round-trip test would require reconstructing the custom
    # objects, which would need more complex logic in recursive_from_json to
    # handle class instantiation. The SerialWrapper class handles this case.


def test_recursive_to_json_with_serial_wrap():
    # Test the serial_wrap parameter
    website = Website(
        url="https://example.com",
    )

    # Without serial_wrap (default behavior)
    json_data = recursive_to_json(website)
    assert isinstance(json_data, dict)
    assert "url" in json_data

    # With serial_wrap=True
    json_data = recursive_to_json(website, serial_wrap=True)
    assert isinstance(json_data, dict)
    assert "type" in json_data
    assert "module" in json_data
    assert "value" in json_data
    assert json_data["type"] == "Website"

    # Verify we can reconstruct from the wrapped data
    reconstructed = SerialWrapper.from_json(json_data)
    assert reconstructed.url == website.url


def test_recursive_to_json_nested_with_serial_wrap():
    # Test serial_wrap with nested objects
    person = Person(name="Alice", age=30)
    color = Color(r=255, g=0, b=0)

    data = {
        "person": person,
        "favorite_color": color,
        "website": Website(url="https://example.com"),
    }

    # With serial_wrap=True
    json_data = recursive_to_json(data, serial_wrap=True)

    # The top-level dict should remain a dict
    assert isinstance(json_data, dict)

    # But the values should be wrapped
    assert "type" in json_data["person"]
    assert json_data["person"]["type"] == "Person"

    assert "type" in json_data["favorite_color"]
    assert json_data["favorite_color"]["type"] == "Color"

    assert "type" in json_data["website"]
    assert json_data["website"]["type"] == "Website"

    # Test round-trip for a nested object
    reconstructed_website = SerialWrapper.from_json(json_data["website"])
    assert reconstructed_website.url == "https://example.com"
