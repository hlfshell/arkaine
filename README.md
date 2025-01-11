# arkaine

Empower your summoned AI agents. arkaine is a batteries-included framework built for DIY builders, individuals, and small scale solutions.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

## Overview

arkaine is built to allow individuals with a little python knowledge to easily create deployable AI agents enhanced with tools. While other frameworks are focused on scalable web-scale solutions, arkaine is focused on the smaller scale projects - the prototype, the small cron job, the weekend project. arkaine attempts to be batteries included - multiple features and tools built in to allow you to go from idea to execution rapidly.

## WARNING
This is a *very* early work in progress. Expect breaking changes, bugs, and rapidly expanding features.

## Features

- 🔧 Easy tool creation and programmatic tool prompting for models
- 🤖 Agents can be "composed" by simply combining these tools and agents together
- 🔀 Thread safe async routing built in
- 🔄 Multiple backend implementations for different LLM interfaces
    - OpenAI (GPT-3.5, GPT-4)
    - Anthropic Claude
    - Groq
    - Ollama (local models)
    - More coming soon...
- 🧰 Built-in common tools (web search, file operations, etc.)

## Key Concepts

- 🔧 **Tools** - Tools are functions (with some extra niceties) that can be called and do something. That's it!
- 🤖 **Agents** - Agents are tools that use LLMS. Different kinds of agents can call other tools, which might be agents themselves!
    -  **MetaAgents** - MetaAgents are multi-shot agents that can repeatedly call an LLM to try and perform its task, where the agent can identify when it is complete with its task.
    - &#129520; **BackendAgents** - BackendAgents are agents that utilize a **Backend** to perform its task.
-  **Backends** - Backends are systems that empower an LLM to utilize tools and detect when it is finished with its task. You probably won't need to worry about them!
- 📦 **Integrations** - Integrations are systems that can trigger your agents in a configurable manner. Want a web server for your agents? Or want your agent firing off every hour? arkaine has you covered.
- **Context** - Context provides thread-safe state across tools. No matter how complicated your workflow gets by plugging agents into agents, contexts will keep track of everything.

## Installation

To install arkaine, ensure you have Python 3.8 or higher installed. Then, you can install the package using pip:

```bash
bash
pip install arkaine
```

# Creating Your Own Tools and Agents

## Creating a Tool

To create a tool, define a class that inherits from the `Tool` class. Implement the required methods and define the arguments it will accept.

```python
python

from arkaine.tools.tool import Tool, Argument
class MyTool(Tool):
    def __init__(self):
        args = [
            Argument("input", "The input data for the tool", "str", required=True)
        ]
        super().__init__("my_tool", "A custom tool", args)

    def invoke(self, context, kwargs):
        # Implement the tool's functionality here
        return f"Processed {kwargs['input']}"
```

### toolify

Since `Tool`s are essentially functions with built-in niceties for arkaine integration, you may want to simply quickly turn an existing function in your project into a `Tool`. To do this, arkaine contains `toolify`.

```python
from arkaine.tools import toolify

@toolify
def func(name: str, age: Optional[int] = None) -> str:
    """
    Formats a greeting for a person.

    name -- The person's name
    age -- The person's age (optional)
    returns -- A formatted greeting
    """
    return f"Hello {name}!"

@toolify
def func2(text: str, times: int = 1) -> str:
    """
    Repeats text a specified number of times.

    Args:
        text: The text to repeat
        times: Number of times to repeat the text

    Returns:
        The repeated text
    """
    return text * times

def func3(a: int, b: int) -> int:
    """
    Adds two numbers together

    :param a: The first number to add
    :param b: The second number to add
    :return: The sum of the two numbers
    """
    return a + b
func3 = toolify(func3)
```

#### docstring scanning

Not only will `toolify` turn `func1/2/3` into a `Tool`, it also attempts to read the type hints and documentation to create a fully fleshed out tool for you, so you don't have to rewrite descriptions or argument explainers.

## Creating an Agent

To create an agent, define a class that inherits from the `Agent` class. Implement the `prepare_prompt` method to convert arguments into a prompt for the LLM.

Remember, that all agents are also tools!


```python
from arkaine.agent import Agent
from arkaine.llms.llm import LLM

class MyAgent(Agent):
    def __init__(self, llm: LLM):
        args = [
            Argument("task", "The task description", "str", required=True)
        ]
        super().__init__("my_agent", "A custom agent", args, llm)
        
    def prepare_prompt(self, kwargs):
        return f"Perform the following task: {kwargs['task']}"
```

## Creating MetaAgents

`MetaAgents` are agents that can repeatedly call an LLM to try and perform its task, where the agent can identify when it is complete with its task. To create one, inherit from the `MetaAgent` class.

```python
from arkaine.agent import MetaAgent

class MyMetaAgent(MetaAgent):
    def __init__(self, llm: LLM):
        super().__init__("my_meta_agent", "A custom meta agent", [], llm)
    
    def prepare_prompt(self, context, **kwargs):
        return f"Perform the following task: {kwargs['task']}"
    
    def extract_result(self, context, output):
        # If this function returns None, the agent will be called again
        # with the ability to "prepare" the prompt again to include
        # its prior call.
        ... generate output
        return output
```

## BackendAgents

`BackendAgents` are agents that utilize a `Backend` to perform its task. A `Backend` is a system that empowers an LLM to utilize tools and detect when it is finished with its task. To create one, inherit from the `BackendAgent` class.

```python
from arkaine.agent import BackendAgent

class MyBackendAgent(BackendAgent):
    def __init__(self, backend: Backend):
        super().__init__("my_backend_agent", "A custom backend agent", [], backend)
    
    def prepare_for_backend(self, **kwargs):
        # Given the arguments for the agent, transform them
        # (if needed) for the backend's format. These will be
        # passed to the backend as arguments.
        ...
        return kwargs
```

If you wish to create a custom backend, you have to implement several functions.

```python

class MyBackend(BaseBackend):
    def __init__(self, llm: LLM, tools: List[Tool]):
        super().__init__(llm, tools)

    def parse_for_tool_calls(self, context: Context, text: str, stop_at_first_tool: bool = False) -> ToolCalls:
        # Given a response from a model, isolate any calls to tools
        ...
        return []

    def parse_for_result(self, context: Context, text: str) -> Optional[Any]:
        # Given a response from a model, isolate any result. If a result
        # is provided, the backend will continue calling itself.
        ...
        return None
    
    def tool_results_to_prompts(self, context: Context, prompt: Prompt, results: ToolResults) -> List[Prompt]:
        # Given the results of a tool call, transform them into a prompt
        # friendly format.
        ...
        return []
    
    def prepare_prompt(self, context: Context, **kwargs) -> Prompt:
        # Given the arguments for the agent, create a prompt that tells
        # our BackendAgent what to do.
        ...
        return []
```

### Choosing a Backend

When in doubt, trial and error works. You have the following backends available:

- `OpenAI` - utilizes OpenAI's built in tool calling API
- `Simple` - a simple scanner to see if the model's response starts a line with a tool call. Nothing fancy.
- `REACT` - a backend that utilizes the Thought/Action/Answer paradigm to call tools and think through tasks.
- `Python` - utilize python coding within a docker environment to safely execute LLM code with access to your tools to try and solve problems.


## LLMs

Arkaine supports multiple integrations with different LLM interfaces:

- **OpenAI**
- **Anthropic Claude**
- **Groq**
- **Ollama** - local offline models supported!

### Expanding to other LLMs

Adding support to existing LLMs is easy - you merely need to implement the `LLM` interface. Here's an example:

```python
from arkaine.llms.llm import LLM

class MyLLM(LLM):
    def __init__(self, api_key: str):
        self.api_key = api_key

    def context_length(self) -> int:
        # Return the maximum number of tokens the model can handle.
        return 8192

    def completion(self, prompt: Prompt) -> str:
        # Implement the LLM's functionality here
        return self.call_llm(prompt)
```

# Quick Start

Here's a simple example of creating and using an agent:

```python
from arkaine.llms.openai import OpenAILLM
from arkaine.agent import Agent

# Initialize the LLM
llm = OpenAILLM(api_key="your-api-key")

# Define a simple agent
class SimpleAgent(Agent):

    def init(self, llm):
        super().init("simple_agent", "A simple agent", [], llm)

    def prepare_prompt(self, kwargs):
        return "Hello, world!"

# Create and use the agent
agent = SimpleAgent(llm)
result = agent.invoke(context={})
print(result)
```

# Contexts, State, and You

This is a bit of an advanced topic, so feel free to skip this section if you're just getting started.

All tools and agents are passed at execution time (when they are called) a `Context` object. The goal of the context object is to track tool state, be it the tool's specific state or its children. Similarly, it provides a number of helper functions to make it easier to work with tooling. All of a context's functionalities are thread safe.

Contexts are acyclic graphs with a single root node. Children can branch out, but ultimately return to the root node as execution completes.

Contexts track the progress, input, output, and possible exceptions of the tool and all sub tools. They can be saved (`.save(filepath)`) and loaded (`.load(filepath)`) for future reference.

Contexts are automatically created when you call your tool, but a blank one can be passed in as the first argument to all tools as well.

```python
context = Context()
my_tool(context, {"input": "some input"})
```

## State Tracking

Contexts can track state for its own tool, temporary debug information, or provide overall tool state.

To track information within the execution of a tool (and only in that tool), you can access the context's thread safe state by using it like a `dict`.

```python
context["your_variable"] = "some information"
print(context["your_variable"])
```

To make working with this data in a threadsafe manner easier, arkaine provides additional functionality not found in a normal `dict`:

- `append` - append a value to a list value contained within the context
- `concat` - concatenate a value to a string value contained within the context
- `increment` - increment a numeric value contained within the context
- `decrement` - decrement a numeric value contained within the context
- `update` - update a value contained within the context using a function, allowing more complex operations to be performed atomically

This information is stored on the context it is accessed from.

Again, context contains information for its own state, but children context can not access this information (or vice versa).

```python
context.x["your_variable"] = "it'd be neat if we just were nice to each other"
print(context.x["your_variable"])
# it'd be neat if we just were nice to each other

child_context = context.child_context()
print(child_context.x["your_variable"])
# KeyError: 'your_variable'
```

### Execution Level State

It may be possible that you want state to persist across the entire chain of contexts. arkaine considers this as "execution" state, which is not a part of any individual context, but the entire entity of all contexts for the given execution. This is useful for tracking state across multiple tools and being able to access it across children.

To utilize this, you can use `.x` on any `Context` object. Just as with the normal state, it is thread safe and provides all features.

```python
context.x["your_variable"] = "robots are pretty cool"
print(context.x["your_variable"])
# robots are pretty cool

child_context = context.child_context()
print(child_context.x["your_variable"])
# robots are pretty cool
```

### Debug State

It may be necessary to report key information if you wish to debug the performance of a tool. To help this along, arkaine provides a debug state. Values are only written to it if the global context option of debug is et to true.

```python
context.debug["your_variable"] = "robots are pretty cool"
print(context.debug["your_variable"])
# KeyError: 'your_variable'

from arkaine.options.context import ContextOptions
ContextOptions.debug(True)

context.debug["your_variable"] = "robots are pretty cool"
print(context.debug["your_variable"])
# robots are pretty cool
```

Debug states are entirely contained within the context it is set to, like the base state.

## Retrying Failed Contexts

Let's say you're developing a chain of tools and agents to create a complex behavior. Since we're possibly talking about multiple tools likely making web calls and multiple LLM calls, it may take a significant amount of time and compute to re-run everything from scratch. To help with this, you can save the context and call call `retry(ctx)` on its tool. It will utilize the same arguments, and call down to its children until it finds an incomplete or error'ed out context, and then pick up the re-run from that. You can thus skip re-running the entire chain if setup right.

## Asynchronous Execution

You may want to trigger your tooling in a non-blocking manner. `arkaine` has you covered.

```python
ctx = my_tool.async_call({"input": "some input"})

# do other things

ctx.wait()
print(ctx.result)
```

If you prefer futures, you can request a future from any context.

```python
ctx = my_tool.async_call({"input": "some input"})

# do other things

ctx.future().result()
```

# Flow

Agents can feed into other agents, but the flow of information between these agents can be complex! To make this easier, arkaine provdies several flow tools that maintain observability and handles a lot of the complexity for you.

- `Linear` - A flow tool that will execute a set of agents in a linear fashion, feeding into one another.

- `Conditional` - A flow tool that will execute a set of agents in a conditional fashion, allowing a branching of if/then/else logic.

- `Branch` - Given a singular input, execute in parallel multiple tools/agents and aggregate their results at the end.

- `ParallelList` - Given a list of inputs, execute in parallel the same tool/agent and aggregate their results at the end.

- `Retry` - Given a tool/agent, retry it until it succeeds or up to a set amount of attempts. Also provides a way to specify which exceptions to retry on.

## Linear

You can make tools out of the `Linear` tool, where you pass it a name, description, and a list of steps. Each step can be a tool, a function, or a lambda. - lambdas and functions are `toolify`d into tools when created.

```python
from arkaine.flow.linear import Linear

def some_function(x: int) -> int:
    return str(x) + " is a number"

my_linear_tool = Linear(
    name="my_linear_flow",
    description="A linear flow",
    steps=[
        tool_1,
        lambda x: x**2,
        some_function,
        ...
    ],
)

my_linear_tool({"x": 1})
```

## Conditional

A `Conditional` tool is a tool that will execute a set of agents in a conditional fashion, allowing a branching of if->then/else logic. The then/otherwise attributes are the true/false branches respectively, and can be other tools or functions.

```python
from arkaine.flow.conditional import Conditional

my_tool = Conditional(
    name="my_conditional_flow",
    description="A conditional flow",
    args=[Argument("x", "An input value", "int", required=True)],
    condition=lambda x: x > 10,
    then=tool_1,
    otherwise=lambda x: x**2,
)

my_tool(x=11)
```


## Branch

A `Branch` tool is a tool that will execute a set of agents in a parallel fashion, allowing a branching from an input to multiple tools/agents.

```python
from arkaine.flow.branch import Branch

my_tool = Branch(
    name="my_branch_flow",
    description="A branch flow",
    args=[Argument("x", "An input value", "int", required=True)],
    tools=[tool_1, tool_2, ...],
)

my_tool(11)
```

The output of each function can be formatted using the `formatters` attribute; it accepts a list of functions wherein the index of the function corresponds to the index of the associated tool.

By default, the branch assumes the `all` completion strategy (set using the `completion_strategy` attribute). This waits for all branches to complete. You also have access to `any` for the first, `n` for the first n, and `majority` for the majority of branches to complete.

Similarly, you can set an `error_strategy` on whether or not to fail on any exceptions amongst the children tools.

## ParallelList

A `ParallelList` tool is a tool that will execute a singular tool across a list of inputs. These are fired off in parallel (with an optional `max_workers` setting).

```python
from arkaine.flow.parallel_list import ParallelList

@toolify
def my_tool(x: int) -> int:
    return x**2

my_parallel_tool = ParallelList(
    tool=my_tool,
)

my_tool([1, 2, 3])
```

If you have a need to format the items prior to being fed into the tool, you can use the `item_formatter` attribute, which runs against each input individually.

```python
my_parallel_tool = ParallelList(
    tool=my_tool,
    item_formatter=lambda x: int(x),
)

my_parallel_tool(["1", "2", "3"])
```

...and as before with `Branch`, you can set attributes for `completion_strategy`, `completion_count`, and `error_strategy`.

## Retry

A `Retry` tool is a tool that will retry a tool/agent until it succeeds or up to a set amount of attempts, with an option to specify which exceptions to retry on.

```python
from arkaine.flow.retry import Retry

my_tool = ...

my_resilient_tool = Retry(
    tool=tool_1,
    max_retries=3,
    delay=0.5,
    exceptions=[ValueError, TypeError],
)

my_resilient_tool("hello world")
```

# Toolbox

Since arkaine is trying to be a batteries-included framework, it comes with a set of tools that are ready to use that will hopefully expand soon.

- `ContentFilter` - Filter a large body of text based on semantic similarity to a query - great for small context window models.

- `ContentQuery` - An agent that, given a large body of text, will read through it in manageable chunks and attempt to answer posed questions to it by making notes on information as it reads.

- `EmailSender` - Send e-mails through various email services (including G-Mail) using SMTP.

- `NoteTaker` - Given a large body of text, this agent will attempt to create sructured outlines of the content.

- `PDFReader` - Given a local PDF file or a remotely hosted PDF file, this tool converts the content to LLM friendly markdown.

- `SMS` - Send text messages through various SMS services (Vonage, AWS SNS, MessageBird, Twilio, etc.)

- `Summarizer` - Given a large body of text, this agent will attempt to summarize the content to a requested length

- `WebSearcher` - given a topic or task, generate a list of potentially relevant queries perform a web search (defaults to DuckDuckGo, but compatible with Google and Bing). Then, given the results, isolate the relevant websites that have a high potential of containing relevant information.

- `Wikipedia` - Given a question, this agent will attempt to retrieve the Wikipedia page on that topic and utilize it to answer the question.

# Integrations

It's one thing to get an agent to work, it's another to get it to work when you specifically want it to, or in reaction to something else. For this arkaine provides *integrations* - components that stand alone and accept your agents as tools, triggering them in a configurable manner.

Current integrations include:

- `API` - Given a set of tools, instantly create a web API that can expose your agents to any other tools.
- `CLI` - Create a set of terminal applications for your agents for quick execution.
- `Schedule` - Schedule your agents to trigger at a set time or at recurring intervals 
- `RSS` - Have your agents routinely check RSS feeds and react to new content.

### Coming Soon:

These are planned integrations:

- `Chat` - a chat interface that is powered by your agentic tools.
- `Inbox` - Agents that will react to your incoming e-mails.
- `Discord` - Agents that will react to your Discord messages.
- `HomeAssistant` - implement AI into your home automation systems
- `Slack` - Agents that will react to your Slack messages or act as a bot
- `SMS` - an SMS gateway for your text messages to trigger your agents