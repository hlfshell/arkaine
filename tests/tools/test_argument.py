import pytest

from arkaine.tools.argument import Argument, InvalidArgumentException


def test_argument_initialization():
    arg = Argument(
        name="test_arg",
        description="A test argument",
        type="str",
        required=True,
    )
    assert arg.name == "test_arg"
    assert arg.description == "A test argument"
    assert arg.type == "str"
    assert arg.required is True
    assert arg.default is None


def test_argument_default_value_conversion():
    arg = Argument(
        name="test_arg", description="A test argument", type="int", default="10"
    )
    assert arg.default == 10


def test_argument_invalid_type_conversion():
    with pytest.raises(ValueError):
        Argument(
            name="test_arg",
            description="A test argument",
            type="float",
            default="not_a_float",
        )


def test_argument_to_json():
    arg = Argument(
        name="test_arg",
        description="A test argument",
        type="str",
        required=True,
        default="default_value",
    )
    expected_json = {
        "name": "test_arg",
        "description": "A test argument",
        "type": "str",
        "required": True,
        "default": "default_value",
    }
    assert arg.to_json() == expected_json


# Additional tests for InvalidArgumentException
def test_invalid_argument_exception():
    with pytest.raises(InvalidArgumentException) as exc_info:
        raise InvalidArgumentException("test_tool", ["arg1"], ["arg2"])
    assert "Function test_tool was improperly called" in str(exc_info.value)
    assert "Missing required arguments: arg1" in str(exc_info.value)
    assert "Extraneous arguments: arg2" in str(exc_info.value)
