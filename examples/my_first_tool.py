"""
This example demonstrates two methods for creating a tool:

1. Creating a tool by directly wrapping a plain function using the Tool
   constructor. This is the simplest way to expose a function as a tool.

2. Creating a tool by subclassing the Tool class and implementing your own
   method. This approach is useful if you need custom behavior or wish to
   override default methods.

3. The toolifydecorator, and how to work with it.

In this file we create a "discount calculator" tool. The calculator takes
an original price, a discount percentage, and an optional tax percentage,
and computes the final price.
"""

from arkaine.tools.tool import Tool

"""
A tool is essentially a function, with extra capabilities. You'll see what
I mean as we explore creating a simple tool. We'll also import some additional
objects that help us better define our tool:
"""

from arkaine.tools.argument import Argument
from arkaine.tools.example import Example
from arkaine.tools.result import Result

from arkaine.tools.argument import Argument
from arkaine.tools.example import Example
from arkaine.tools.result import Result

"""
The use of Argument, Example, and Result definitions in tool creation provides
clear metadata that informs language models about the tool's behavior,
capabilities, and requirements. This means that, no matter how the language
model is trained to handle tool calling, or whatever style we utilize to prompt
the agent to use the tool, we will be able to easily define it to the model.

- Argument: Always required - Defines the expected parameters (type,
  description, requirement) for the tool, allowing robust error checking,
  auto-generated documentation, and improved usability.

- Example: Optional -Supplies sample inputs and outputs for the tool, which aids
  in testing, documentation, and provides usage examples. If the prompting
  technique requires few-shot examples, these can be utilize to demonstrate to
  the model how to use the tool.

- Result: Optional - Describes the expected format and type of the tool's
  output, allowing some models to chain together multiple tools (if they support
  it).

"""

########################
# 1. Function-Based Tool
########################


def calc_discounted_price(
    price: float, discount: float, tax: float = 0.0
) -> float:
    """
    Calculate the final price after a discount and optional tax.

    Args:
        price (float): Original price.
        discount (float): Discount percentage (e.g., 20 for 20% off).
        tax (float): Tax percentage to add after discount.

    Returns:
        float: Final price rounded to 2 decimal places.
    """
    # Compute the price after discount
    discounted_price = price * (1 - discount / 100)
    # Add tax if provided
    final_price = discounted_price * (1 + tax / 100)
    return round(final_price, 2)


# Create the tool instance by directly wrapping the function.
discount_tool = Tool(
    name="discount_calculator",
    # Remember - a clear description is important to properly convey to
    # the model what the tool does.
    description=(
        "Calculates final price after applying a discount and optional tax."
    ),
    # Define each of our arguments. You can specify the type, it's description,
    # and optionally whether it's required and it's default value.
    args=[
        Argument(
            "price", "Original price of the product", "float", required=True
        ),
        Argument(
            "discount", "Discount percentage (0-100)", "float", required=True
        ),
        Argument(
            "tax",
            "Optional tax percentage (default 0)",
            "float",
            required=False,
            default=0.0,
        ),
    ],
    # Specify our function to call
    func=calc_discounted_price,
    # Examples are important if you want to use the tool in few-shot prompting,
    # but can be ignored if you're confident the tool is simple or you'll only
    # use it on models that don't do well with multiple examples; ie reasoning
    # models.
    examples=[
        Example(
            name="Basic Discount Example",
            args={"price": 100, "discount": 20, "tax": 5},
            output="84.0",
            description="Calculates the final price for a $100 product with 20% off and 5% tax.",
        )
    ],
    # This is optional, but good form
    result=Result(
        "float",
        "Final price rounded to 2 decimal places.",
    ),
)

print("=" * 100)
print("Function-based tool:")
print(discount_tool)
print("Trying out the tool:")
test = discount_tool(100, 20, 5)
print("discount_tool(100, 20, 5) =", test)
print("Success: ", test == 84.0)
print("=" * 100)
print()

########################
# 2. Inheritance-Based Tool
########################


class CustomDiscountTool(Tool):
    """
    A custom tool that calculates the final price after discount by subclassing
    Tool.

    By inheriting from Tool, you can override methods and add custom behavior.
    and add extra attributes and capabilities during tool execution. This is
    great if you're wrapping a client for another service or tracking any
    specific configuration or state for that tool.

    In this example, we define a 'calculate_discount' method and pass it to the
    Tool constructor. You might add logging or other side effects here.
    """

    def __init__(self):
        args = [
            Argument("price", "Original price", "float", required=True),
            Argument("discount", "Discount percentage", "float", required=True),
            Argument(
                "tax",
                "Tax percentage to add (optional)",
                "float",
                required=False,
                default=0.0,
            ),
        ]
        description = (
            "A Custom Discount Tool that calculates final prices "
            "with optional logging."
        )
        examples = [
            Example(
                name="Basic Discount Example",
                args={"price": 100, "discount": 20, "tax": 5},
                output="84.0",
                description=(
                    "Calculates the final price for a $100 product "
                    "with 20% off and 5% tax."
                ),
            )
        ]
        result = Result(
            "float",
            "Final price rounded to 2 decimal places.",
        )

        # Finally call super().__init__() to initialize the Tool
        super().__init__(
            name="custom_discount_calculator",
            description=description,
            args=args,
            func=self.calculate_discount,
            examples=examples,
            result=result,
        )

    """
    One important thing to note here - the called function may optionally
    accept as the first argument a Context object - if you do this, utilize
    the parameter name 'context' in the function signature, and if you
    use types be sure to import Context from arkaine.tools.context.

    The function below would then look like:
    def calculate_discount(
        self, context: Context, price: float, discount: float, tax: float = 0.0
    ) -> float:
        ...

    The context is an important object that tracks tool's execution states
    and provides a lot of great async functionality. We'll talk about that
    in another example.

    If the context isn't provided as the first argument, it won't be
    passed. This is perfectly fine if you don't plan on using the context.
    """

    def calculate_discount(
        self, price: float, discount: float, tax: float = 0.0
    ) -> float:
        """
        A custom method to calculate the discounted price.
        This method could be extended to include extra behavior such as logging.
        """
        discounted_price = price * (1 - discount / 100)
        final_price = discounted_price * (1 + tax / 100)
        return round(final_price, 2)


# Instantiate the custom tool.
custom_discount_tool = CustomDiscountTool()

print("=" * 100)
print("Inheritance-based tool:")
print(custom_discount_tool)
print("Trying out the tool:")
test = custom_discount_tool(200, discount=15)
print("custom_discount_tool(200, discount=15) =", test)
print("Success: ", test == 170.0)
print("=" * 100)
print()

########################
# 3. Decorator-Based Tool (Toolify)
########################

from arkaine.tools.toolify import toolify

"""
Perhaps you don't want to do all of this work, especially if you already
have a function that has been nicely documented in one of the standard
(RST, google, plain) documentation formats. If so, this decorator is for you.

toolify will read the docstring and type hints of the function, automatically
extracting the relevant information to create the Arguments and Result objects.

If the function lacks the documentation, it will do its best, but note that
it may be difficult for an LLM to discern just from the function name and
arguments what the tool does.

A lambda can also be used, and given a random name of lambda_<random_id>.

Note that in a lot of arkaine tooling (especially the flow and wrapper
classes) functions that are passed that are not tools are toolify'ed
automatically.

The docstring formats supported look like this:
"""

# RST
# def function(param1, param2):
#        """
#        Description of the function.
#
#        :param param1: Description of param1
#        :param param2: Description of param2
#        :returns: Description of return value
#        """

# Google
# def function(param1, param2):
#     """
#     Description of the function.
#
#     Args:
#         param1: Description of param1
#         param2: Description of param2
#
#     Returns:
#         Description of return value
#     """

# Plain
# def function(param1, param2):
#    """
#    Description of the function.
#
#    param1 -- Description of param1
#    param2 -- Description of param2
#
#    Returns -- Description of return value
#    """


# You can also specify a new name and description for the tool if you
# want, overriding the extracted information.
@toolify(
    tool_name="tax_calculator",
)
def calc_tax(price: float, tax: float = 0.0) -> float:
    """
    Calculate the tax amount given a price and tax rate.

    :param price: The base price.
    :param tax: The tax rate in percentage (e.g., 5 for 5%).
    :return: The calculated tax amount.
    """
    return round(price * tax / 100, 2)


print("=" * 100)
print("Decorator-based tool (tax_calculator):")
print(calc_tax)
print("Trying out the tool:")
test = calc_tax(200, tax=7)
print("calc_tax(200, tax=7) =", test)
print("Success: ", test == 14.0)
print("=" * 100)
print()
