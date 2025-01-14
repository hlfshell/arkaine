from typing import Any, List, Optional, Union

import pytest

from arkaine.tools.tool import Tool
from arkaine.tools.toolify import toolify


class TestBasicFormats:
    def test_rst_format(self):
        @toolify
        def func(a: int, b: int) -> int:
            """
            Adds two numbers together

            :param a: The first number to add
            :param b: The second number to add
            :return: The sum of the two numbers
            """
            return a + b

        assert func.name == "func"
        assert "Adds two numbers together" in func.description
        assert "The sum of the two numbers" in func.description
        assert len(func.args) == 2
        assert func.args[0].name == "a"
        assert func.args[0].description == "The first number to add"
        assert func.args[0].type == "int"
        assert func.args[0].required is True

    def test_google_format(self):
        @toolify
        def func(text: str, times: int = 1) -> str:
            """
            Repeats text a specified number of times.

            Args:
                text: The text to repeat
                times: Number of times to repeat the text

            Returns:
                The repeated text
            """
            return text * times

        assert len(func.args) == 2
        assert func.args[0].name == "text"
        assert func.args[0].required is True
        assert func.args[1].name == "times"
        assert func.args[1].required is False
        assert func.args[1].default == 1
        assert "The repeated text" in func.description

    def test_plain_format(self):
        @toolify
        def func(name: str, age: Optional[int] = None) -> str:
            """
            Formats a greeting for a person.

            name -- The person's name
            age -- The person's age (optional)
            returns -- A formatted greeting
            """
            return f"Hello {name}!"

        assert len(func.args) == 2
        assert func.args[0].name == "name"
        assert func.args[0].description == "The person's name"
        assert func.args[1].name == "age"
        assert func.args[1].type == "Optional[int]"
        assert "A formatted greeting" in func.description


class TestComplexCases:
    def test_multiline_parameters(self):
        @toolify
        def func(text: str, width: int = 80) -> str:
            """
            Centers text.

            Args:
                text: The text to center
                      Can be any string you want
                      Multiple lines are fine
                width: The total width
                       Must be greater than text length
                       Defaults to 80

            Returns:
                The centered text
                With proper width
            """
            return text.center(width)

        assert func.args[0].description == (
            "The text to center Can be any string you want Multiple lines are fine"
        )
        assert "The centered text With proper width" in func.description

    def test_mixed_formats(self):
        @toolify
        def func(a: List[int], b: Union[int, float]) -> float:
            """
            Mixed format test.

            :param a: A list of numbers
            Args:
                b: A number to multiply by

            returns -- First return
            :return: Second return
            Returns:
                Third return
            """
            return sum(a) * b

        assert len(func.args) == 2
        assert func.args[0].type == "List[int]"
        assert func.args[1].type == "Union[int, float]"
        # Should use the first return description encountered
        assert "First return" in func.description

    def test_unicode_handling(self):
        @toolify
        def func(text: str) -> str:
            """
            Unicode test.

            Parameters:
                text: Text with unicode — including em-dash
                      and other™ special® characters…

            Returns: ☺ → ♠ ♣ ♥ ♦ ∞ ≠ ≈
            """
            return text

        assert "em-dash" in func.args[0].description
        assert "☺ → ♠" in func.description


class TestEdgeCases:
    def test_empty_docstring(self):
        @toolify
        def func() -> None:
            """"""
            pass

        assert func.description == "Tool for func"
        assert len(func.args) == 0

    def test_no_docstring(self):
        @toolify
        def func():
            pass

        assert func.description == "Tool for func"
        assert len(func.args) == 0

    def test_malformed_rst(self):
        @toolify
        def func(x: int, y: int) -> int:
            """
            Bad RST.

            :param: missing name
            :param x: good parameter
            :param y missing colon
            :return missing colon
            """
            return x + y

        assert len(func.args) == 2
        assert func.args[0].name == "x"
        assert func.args[0].description == "good parameter"
        assert func.args[1].description == f"Parameter y"

    # def test_incomplete_google(self):
    #     @toolify
    #     def func(x: int, y: int) -> int:
    #         """
    #         Bad Google format.

    #         Args:
    #             x: This is fine
    #             y with no colon
    #             z: (This parameter doesn't exist)

    #         Returns
    #             No colon here
    #         """
    #         return x + y

    #     assert len(func.args) == 2
    #     assert func.args[0].description == "This is fine"
    #     assert "No colon here" in func.description

    def test_return_in_middle(self):
        @toolify
        def func(x: int, y: int) -> int:
            """
            Return in middle.

            :param x: First number
            :return: The sum
            :param y: Second number
            """
            return x + y

        assert len(func.args) == 2
        assert "The sum" in func.description
        assert func.args[1].name == "y"

    def test_duplicate_sections(self):
        @toolify
        def func(x: str) -> str:
            """
            Duplicate sections.

            Args:
                x: First definition
            Returns:
                First return

            :param x: Second definition
            :return: Second return

            Parameters:
                x: Third definition
            Returns:
                Third return
            """
            return x

        # Should use first definitions encountered
        assert "First definition" in func.args[0].description
        assert "First return" in func.description


class TestToolifyDecorator:
    def test_with_parentheses(self):
        @toolify()
        def func():
            pass

        assert isinstance(func, Tool)

    def test_without_parentheses(self):
        @toolify
        def func():
            pass

        assert isinstance(func, Tool)

    def test_with_name_override(self):
        @toolify(tool_name="custom_name")
        def func():
            pass

        assert func.name == "custom_name"

    def test_with_description_override(self):
        @toolify(tool_description="custom description")
        def func():
            """Original description"""
            pass

        assert func.description == "custom description"


class TestTypeHandling:
    def test_basic_types(self):
        @toolify
        def func(
            a: int,
            b: str,
            c: float,
            d: bool,
            e: bytes,
        ) -> None:
            pass

        types = [arg.type for arg in func.args]
        assert types == ["int", "str", "float", "bool", "bytes"]

    def test_complex_types(self):
        @toolify
        def func(
            a: List[int],
            b: Optional[str],
            c: Union[int, float],
            d: dict[str, Any],
        ) -> None:
            pass

        types = [arg.type for arg in func.args]
        assert "List[int]" in types
        assert "Optional[str]" in types
        assert "Union[int, float]" in types
        assert "dict" in types
