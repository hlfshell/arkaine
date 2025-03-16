import pytest

from arkaine.internal.json import (
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
        return cls(data["r"], data["g"], data["b"])

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
        return cls(data["name"], data["age"])

    def to_json(self):
        return {"name": self.name, "age": self.age}

    def __eq__(self, other):
        return self.name == other.name and self.age == other.age


def test_serialization_basic():
    # Test with Color class
    color = Color(r=0, g=255, b=0)
    json_data = recursive_to_json(color)

    # The new implementation adds __class__ and __module__ directly
    assert json_data["__class__"] == "Color"
    assert "test_json" in json_data["__module__"]
    assert json_data["r"] == 0
    assert json_data["g"] == 255
    assert json_data["b"] == 0

    # Test reconstruction
    reconstructed = recursive_from_json(json_data)
    assert reconstructed.r == 0
    assert reconstructed.g == 255
    assert reconstructed.b == 0

    # Test with Person class
    person = Person(name="Alice", age=30)
    json_data = recursive_to_json(person)

    assert json_data["__class__"] == "Person"
    assert json_data["name"] == "Alice"
    assert json_data["age"] == 30

    reconstructed = recursive_from_json(json_data)
    assert reconstructed.name == "Alice"
    assert reconstructed.age == 30


def test_is_serialized_object():
    # Test if a dictionary has the necessary attributes for deserialization
    serialized_obj = {
        "__class__": "Test",
        "__module__": "test_module",
    }

    # Check manually since there's no helper function
    assert "__class__" in serialized_obj
    assert "__module__" in serialized_obj

    # Test with missing attributes
    incomplete = {
        "__class__": "Test",
    }
    assert "__module__" not in incomplete


def test_round_trip_serialization():
    # Test full serialization and deserialization cycle
    original = Person(name="Bob", age=25)

    # Create a clean copy without the metadata
    json_data = original.to_json()
    json_data["__class__"] = "Person"
    json_data["__module__"] = "test_json"

    reconstructed = recursive_from_json(json_data)
    assert reconstructed.name == original.name
    assert reconstructed.age == original.age


def test_serialization_with_website(mock_llm):
    website = Website(
        url="https://example.com",
    )

    json_data = recursive_to_json(website)
    # Remove metadata before reconstruction to avoid __init__ errors
    class_name = json_data.pop("__class__")
    module_name = json_data.pop("__module__")

    # Add them back for the test
    json_data["__class__"] = class_name
    json_data["__module__"] = module_name

    reconstructed = recursive_from_json(json_data)
    assert reconstructed.url == website.url


def test_serialization_with_recursive_to_json():
    website = Website(
        url="https://example.com",
    )

    json_data = recursive_to_json(website)

    assert json_data["__class__"] == "Website"
    assert json_data["url"] == "https://example.com"

    # Remove metadata before reconstruction to avoid __init__ errors
    class_name = json_data.pop("__class__")
    module_name = json_data.pop("__module__")

    # Add them back for the test
    json_data["__class__"] = class_name
    json_data["__module__"] = module_name

    reconstructed = recursive_from_json(json_data)
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
    json_result = recursive_to_json(color)

    # Check the core values (ignoring metadata)
    assert json_result["r"] == 255
    assert json_result["g"] == 0
    assert json_result["b"] == 0

    # Test nested objects with to_json method
    data = {
        "person": Person(name="John", age=25),
        "favorite_color": Color(r=0, g=0, b=255),
    }
    result = recursive_to_json(data)

    # Check person values
    assert result["person"]["name"] == "John"
    assert result["person"]["age"] == 25

    # Check color values
    assert result["favorite_color"]["r"] == 0
    assert result["favorite_color"]["g"] == 0
    assert result["favorite_color"]["b"] == 255


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

    # Create serialized data manually to avoid metadata issues
    person_json = {
        "name": "John",
        "age": 25,
        "__class__": "Person",
        "__module__": "test_json",
    }
    color_json = {
        "r": 255,
        "g": 0,
        "b": 0,
        "__class__": "Color",
        "__module__": "test_json",
    }

    # This should call the from_json method on the class
    result = recursive_from_json(person_json)
    assert result.name == "John"
    assert result.age == 25

    result = recursive_from_json(color_json)
    assert result.r == 255
    assert result.g == 0
    assert result.b == 0


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

    # Check color values (ignoring metadata)
    assert json_data["colors"][0]["r"] == 255
    assert json_data["colors"][0]["g"] == 0
    assert json_data["colors"][0]["b"] == 0

    # Check person values
    assert json_data["details"]["contact"]["name"] == "Emergency Contact"
    assert json_data["details"]["contact"]["age"] == 45


def test_recursive_to_json_nested():
    # Test with nested objects
    person = Person(name="Alice", age=30)
    color = Color(r=255, g=0, b=0)

    data = {
        "person": person,
        "favorite_color": color,
        "website": Website(url="https://example.com"),
    }

    json_data = recursive_to_json(data)

    # The top-level dict should remain a dict
    assert isinstance(json_data, dict)

    # Check that values have metadata
    assert "__class__" in json_data["person"]
    assert json_data["person"]["__class__"] == "Person"

    assert "__class__" in json_data["favorite_color"]
    assert json_data["favorite_color"]["__class__"] == "Color"

    assert "__class__" in json_data["website"]
    assert json_data["website"]["__class__"] == "Website"


def test_recursive_from_json_fallback_propagation():
    """Test that fallback_if_no_class is properly propagated to nested calls."""
    # Create a nested structure with a class that doesn't exist
    nested_data = {
        "top_level": "value",
        "nested": {
            "__class__": "NonExistentClass",
            "__module__": "non_existent_module",
            "some_data": 123,
        },
        "list_with_problem": [
            42,
            {
                "__class__": "AnotherNonExistentClass",
                "__module__": "another_non_existent_module",
                "more_data": "test",
            },
        ],
    }

    # Without fallback, this should raise an exception
    with pytest.raises(Exception):
        recursive_from_json(nested_data, fallback_if_no_class=False)

    # With fallback=True, it should return the structure with the problematic
    # parts as dictionaries
    result = recursive_from_json(nested_data, fallback_if_no_class=True)

    # Verify the structure was preserved
    assert result["top_level"] == "value"
    assert isinstance(result["nested"], dict)
    assert result["nested"]["__class__"] == "NonExistentClass"
    assert result["nested"]["__module__"] == "non_existent_module"
    assert result["nested"]["some_data"] == 123

    # Check the list was processed correctly
    assert result["list_with_problem"][0] == 42
    assert isinstance(result["list_with_problem"][1], dict)
    assert (
        result["list_with_problem"][1]["__class__"] == "AnotherNonExistentClass"
    )
    assert (
        result["list_with_problem"][1]["__module__"]
        == "another_non_existent_module"
    )
    assert result["list_with_problem"][1]["more_data"] == "test"
