"""
This example demonstrates how to use Context objects in arkaine. Contexts are a
powerful feature that allow you to track state, manage execution flow, and
handle asynchronous operations across tools and agents.

We'll cover:
1. Basic context usage
2. State tracking at different levels
3. Child contexts and execution graphs
4. Asynchronous execution with contexts
5. Retrying failed operations
6. Context events and listeners
"""

# First, let's create a simple tool that we'll use to demonstrate context
# features
from arkaine.tools.tool import Tool
from arkaine.tools.argument import Argument
from arkaine.tools.context import Context


# A simple counter tool that increments a value in the context
def counter_tool(context, increment: int = 1):
    """
    A simple tool that increments a counter in the context.

    Args:
        context: The execution context
        increment: Amount to increment by (default: 1)

    Returns:
        The new counter value
    """
    # Initialize the counter if it doesn't exist
    if "counter" not in context:
        context["counter"] = 0

    # Increment the counter
    context["counter"] += increment

    return context["counter"]


# Create the tool
counter = Tool(
    name="counter",
    description="Increments a counter stored in the context",
    args=[
        Argument(
            "increment",
            "Amount to increment by",
            "int",
            required=False,
            default=1,
        )
    ],
    func=counter_tool,
)

print("=" * 80)
print("CONTEXT BASICS")
print("=" * 80)

"""
Every tool in arkaine receives a Context object when it's called. This Context
object provides thread-safe state tracking and other utilities. If your function
passed into the tool's `func` parameter contains a first argument that is
"context" and a Context object, you can utilize it. If not, it won't be passed.

You can either:
1. Let the tool create a context automatically when called
2. Create a context yourself and pass it to the tool
"""

# Method 1: Let the tool create a context automatically
result1 = counter(increment=5)
print(f"Auto-created context result: {result1}")

# Method 2: Create a context explicitly and pass it to the tool
context = Context()
result2 = counter(context, increment=3)
print(f"Explicit context result: {result2}")

# The context now contains our counter state
print(f"Context counter value: {context['counter']}")

print("\n" + "=" * 80)
print("CONTEXT STATE LEVELS")
print("=" * 80)

"""
Contexts provide three different levels of state:

1. Local state: Accessible via context["key"] - specific to this context only
2. Execution state: Accessible via context.x["key"] - shared across the
   execution graph. We'll touch on that one in a bit.
3. Debug state: Accessible via context.debug["key"] - only active when debugging
   is enabled

Each level serves a different purpose and has different visibility rules.
"""

# Create a new context and use it with a tool.
context = Context()
result = counter(context, increment=10)

# 1. Local state - only visible to this specific context
context["local_value"] = "I'm only visible to this context"

# 3. Debug state - only visible when debugging is enabled
from arkaine.internal.options.context import ContextOptions

# Debug state is ignored by default
context.debug["debug_info"] = "This won't be stored unless debugging is enabled"

# Enable debugging to see debug state
ContextOptions.debug(True)
context.debug["debug_info"] = "Now I'll be stored and visible"

print("Local state:", context["local_value"])
print("Debug state:", context.debug.get("debug_info", "Not found"))

# Disable debugging again
ContextOptions.debug(False)

"""
Contexts have helper functions to work with this data in thread safe manners
beyond accessing it like context["key"]
"""

# .init checks to see if a key exists. If it doesn't, it initializes it with the
# given value. If it does, it doesn't change it.
context.init("local_value", "I'm the default value")
print("Local state:", context["local_value"])
context.init("local_value", "I'm a different value")
print("Local state:", context["local_value"])

# .get is a thread safe way to get a value from the context. If the key doesn't
# exist, it returns the default value.
print(context.get("local_value", "I'm the default value"))

# We also have list functions:
context["list"] = []
context.append("list", "I'm a new item")
context.append("list", "I'm another item")
print("List:", context["list"])

context.concat("list", ["I'm a third item", "I'm a fourth item"])
print("List:", context["list"])

# We can also increment and decrement values:
context["number"] = 0
context.increment("number", 1)
print("Number:", context["number"])

context.decrement("number", 1)
print("Number:", context["number"])

# And string functions
context["string"] = "Hello "
context.concat("string", "World")
print("String:", context["string"])

# There exists an "operate" function that applies a function to
# a given value in a context. Note that you can *NOT* access
# other context values while using this.
context["number"] = 10
context.operate("number", lambda x: x * 2)
print("Number:", context["number"])


print("\n" + "=" * 80)
print("CHILD CONTEXTS AND EXECUTION GRAPHS")
print("=" * 80)

"""
Contexts form an acyclic graph with a single root node. When tools call other
tools, they create child contexts that inherit certain properties from their
parent.

All contexts have a "root" attribute, and a "parent" attribute. They may be None
if it is a solo context or the root context. (is_root is a boolean check for
root status as well). Contexts have a "children" attribute that returns a list
of all child contexts. Never attach a context to one of its children contexts or
you will create a cycle and have a bad infinite day.

You can create child contexts with the child_context() method.
"""

context = Context()
print("Context is root:", context.is_root)
print("Children:", context.children)
# We need a fake tool for this test
fake_tool = Tool(
    name="fake_tool", description="A fake tool", args=[], func=lambda x: x
)
# Normally None here would be a tool.
child_context = context.child_context(fake_tool)
print("Child context is root:", child_context.is_root)
print("Child context is parent:", child_context.parent is context)
print("Context children", context.children)

print("\n" + "=" * 80)

"""
In order to share state data across an entire execution graph (think of a
multi-step workflow using multiple agents branching out), you can use the "x"
attribute. This is a thread safe dictionary that is shared across all contexts
in the execution graph.
"""

# Create a parent context
parent_context = Context()
parent_context["local_value"] = "parent local"
parent_context.x["shared_value"] = "shared across all contexts"

# Create a child context
child_context = parent_context.child_context(fake_tool)

# Child can't see parent's local state
try:
    print(f"Child accessing parent local state: {child_context['local_value']}")
except KeyError:
    print("Child cannot access parent's local state")

# But child can see execution state
print(f"Child accessing execution state: {child_context.x['shared_value']}")

# Child can set its own local state
child_context["local_value"] = "child local"
print(f"Child local state: {child_context['local_value']}")
print(f"Parent local state: {parent_context['local_value']}")

# A child can also affect the parent's state
child_context.x["shared_value"] = "child changed it"
print(f"Parent state after child change: {parent_context.x['shared_value']}")

# Note that the parent context's regular data store (ie context["key"]) is
# NOT affected by changes to the x datastore - it is a separate datastore.
try:
    print(f"Parent local state: {parent_context['shared_value']}")
except KeyError:
    print("Parent local state is not affected by child changes")

print("\n" + "=" * 80)


print("ASYNCHRONOUS EXECUTION")
print("=" * 80)

"""
Contexts support asynchronous execution, allowing you to:
1. Start tool execution in the background
2. Continue with other work
3. Wait for completion when needed
4. Access results and handle errors

Contexts provide a number of features to help you out.
"""

import time


# Create a tool that simulates a long-running operation
def slow_tool(context, seconds: int = 2):
    """A tool that takes some time to complete"""
    print(f"Starting slow operation for {seconds} seconds...")
    time.sleep(seconds)
    return f"Completed after {seconds} seconds"


# Create the slow tool
slow = Tool(
    name="slow",
    description="A tool that takes time to complete",
    args=[
        Argument("seconds", "Seconds to wait", "int", required=False, default=2)
    ],
    func=slow_tool,
)

# Run the tool asynchronously
print("Starting async execution...")
async_context = slow.async_call(seconds=3)
print("Tool started in background!")

# Do other work while the tool runs
print("Doing other work while waiting...")
time.sleep(1)

# We can utilize wait to pause for the tool to complete.
print("Waiting for tool to complete...")
async_context.wait()
print("Waiting over.")

# Check if the tool has completed
print(f"Is tool complete? {async_context.status}")

# We can also use futures
print("Starting another async execution...")
async_context2 = slow.async_call(seconds=2)
print("Getting future...")
future = async_context2.future()
print("Waiting for future result...")
result = future.result()
print(f"Future result: {result}")


print("\n" + "=" * 80)
print("RETRYING FAILED OPERATIONS")
print("=" * 80)

"""
Contexts track execution state, including errors. This allows you to:
1. Detect when operations fail
2. Examine the error
3. Retry the operation if needed
"""


# Create a tool that sometimes fails
def unreliable_tool(context, fail_first: bool = True):
    """A tool that fails on first attempt if fail_first is True"""
    if fail_first and not context.get("retried", False):
        context["retried"] = True
        raise ValueError("First attempt failed!")
    return "Success!"


# Create the unreliable tool
unreliable = Tool(
    name="unreliable",
    description="A tool that sometimes fails",
    args=[
        Argument(
            "fail_first",
            "Whether to fail on first attempt",
            "bool",
            required=False,
            default=True,
        )
    ],
    func=unreliable_tool,
)

# Try the tool and handle failure
context = Context()
try:
    result = unreliable(context)
    print(f"Tool succeeded with result: {result}")
except ValueError as e:
    print(f"Tool failed with error: {e}")
    print("Retrying...")
    # The retry method uses the same arguments as the original call
    result = unreliable.retry(context)
    print(f"Retry result: {result}")

print("\n" + "=" * 80)
print("CONTEXT EVENTS AND LISTENERS")
print("=" * 80)

"""
Contexts can broadcast events and register listeners, allowing you to:
1. Monitor tool execution
2. React to specific events
3. Build complex workflows with event-driven architecture
"""

from arkaine.tools.events import ToolCalled, ToolReturn

# Create a context with event listeners
context = Context()


# Add event listeners
def on_tool_called(event):
    print(f"Tool called with args: {event.args}")


def on_tool_return(event):
    print(f"Tool returned: {event.result}")


# Register the listeners
context.add_event_listener(on_tool_called, ToolCalled)
context.add_event_listener(on_tool_return, ToolReturn)

# Use the context with our counter tool
result = counter(context, increment=10)
print(f"Final result: {result}")

print("\n" + "=" * 80)
print("SAVING AND LOADING CONTEXTS")
print("=" * 80)

"""
Contexts can be saved to disk and loaded later, allowing you to:
1. Persist execution state between runs
2. Analyze execution history
3. Resume long-running operations
"""

# Create and populate a context
context = Context(fake_tool)
context["important_data"] = "This needs to be saved"
context.x["shared_data"] = "This is shared across the execution"

# Save the context to a file
import tempfile

with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as temp:
    filepath = temp.name
    context.save(filepath)
    print(f"Context saved to {filepath}")

# Load the context from the file
loaded_context = Context.load(filepath)
print(f"Loaded local data: {loaded_context['important_data']}")
print(f"Loaded shared data: {loaded_context.x['shared_data']}")

# Clean up
import os

os.unlink(filepath)

print("\n" + "=" * 80)
print("PRACTICAL EXAMPLE: MULTI-STEP WORKFLOW")
print("=" * 80)

"""
Let's put it all together with a practical example: a multi-step workflow
that uses contexts to track state across multiple tool calls.
"""


# Step 1: Data collection tool
def collect_data(context, source: str):
    """Collect data from a source"""
    print(f"Collecting data from {source}...")
    # Simulate data collection
    if source == "database":
        data = {"users": 100, "active": 75}
    elif source == "api":
        data = {"status": "healthy", "requests": 1250}
    else:
        data = {"source": source, "data": "generic data"}

    # Store in context
    context.x["collected_data"] = data
    return data


# Step 2: Processing tool
def process_data(context):
    """Process data collected in a previous step"""
    if "collected_data" not in context.x:
        raise ValueError("No data collected yet")

    data = context.x["collected_data"]
    print(f"Processing data: {data}")

    # Simulate processing
    processed = {"processed": True, "original": data}
    context.x["processed_data"] = processed
    return processed


# Step 3: Reporting tool
def generate_report(context):
    """Generate a report from processed data"""
    if "processed_data" not in context.x:
        raise ValueError("No processed data available")

    processed = context.x["processed_data"]
    print(f"Generating report from: {processed}")

    # Simulate report generation
    report = f"REPORT: Processed data from {processed['original']}"
    context.x["report"] = report
    return report


# Create the tools
collector = Tool(
    name="collector",
    description="Collects data from a source",
    args=[Argument("source", "Data source", "str", required=True)],
    func=collect_data,
)

processor = Tool(
    name="processor",
    description="Processes collected data",
    args=[],
    func=process_data,
)

reporter = Tool(
    name="reporter",
    description="Generates a report from processed data",
    args=[],
    func=generate_report,
)

# Run the workflow
workflow_context = Context()
print("Starting workflow...")

# Step 1: Collect data
collector(workflow_context, source="database")

# Step 2: Process data
processor(workflow_context)

# Step 3: Generate report
report = reporter(workflow_context)
print(f"Workflow complete. Final report: {report}")

print("\n" + "=" * 80)
print("CONCLUSION")
print("=" * 80)
print(
    """
Contexts are a powerful feature in arkaine that enable:

1. Thread-safe state management at multiple levels
2. Tracking execution flow across tools and agents
3. Asynchronous execution with proper state handling
4. Retry mechanisms for failed operations
5. Event-driven architecture for complex workflows

By understanding and leveraging contexts, you can build more robust,
stateful, and complex AI agent systems.
"""
)
