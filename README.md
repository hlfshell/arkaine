# arkaine

Empower your summoned AI agents. arkaine is a batteries-included framework built for DIY builders, individuals, and small scale solutions.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

[![Join our Discord!](https://img.shields.io/badge/Discord-7289DA?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/6k7N2sV5xA)

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
    -  **IterativeAgents** - IterativeAgents are multi-shot agents that can repeatedly call an LLM to try and perform its task, where the agent can identify when it is complete with its task.
    - &#129520; **BackendAgents** - BackendAgents are agents that utilize a **Backend** to perform its task.
    - 💬 **Chats** - Chats are agents that interact with a user over a prolonged interaction in some way, and can be pair with tools, backends, and other agents.
-  **Backends** - Backends are systems that empower an LLM to utilize tools and detect when it is finished with its task. You probably won't need to worry about them!
- 📦 **Connectors** - Connectors are systems that can trigger your agents in a configurable manner. Want a web server for your agents? Or want your agent firing off every hour? arkaine has you covered.
- **Context** - Context provides thread-safe state across tools. No matter how complicated your workflow gets by plugging agents into agents, contexts will keep track of everything.

## Installation

To install arkaine, ensure you have Python 3.8 or higher installed. Then, you can install the package using pip:

```bash
bash
pip install arkaine
```

## Spellbook

Spellbook is an in-browser tool for monitoring and debugging your agents as they act in real time. To run, in your terminal do either:

```bash
spellbook
```

or

```bash
python -m arkaine.spellbook.server
```

More on how Spellbook can be integrated with your project is later in this document.

# Creating Your Own Tools and Agents

## Creating a Tool

There are several ways to create a tool. You can do this through inheritance, a function call, or a decorator. Let's cover each.

### Just using `Tool`

First, we can just implement a tool by calling it.

```python
from arkaine.tools.tool import Tool

my_tool = Tool(
    name="my_tool",
    description="A custom tool",
    args=[Argument("name", "The name of the person to greet", "str", required=True)],
    func=lambda context, kwargs: f"Hello, {kwargs['name']}!",
)

my_tool({"name": "Jeeves"})
```

### Inheriting from `Tool`

Second, we can define a class that inherits from the `Tool` class. Implement the required methods and define the arguments it will accept.

```python
python

from arkaine.tools.tool import Tool, Argument
class MyTool(Tool):
    def __init__(self):
        args = [
            Argument("input", "The input data for the tool", "str", required=True)
        ]
        super().__init__("my_tool", "A custom tool", args, self._my_func)

    def _my_func(self, context, kwargs):
        # Implement the tool's functionality here
        return f"The meaning of life is {kwargs['input']}"

my_tool(42)
```

By default, the model calls `invoke` internally, which in turn calls the passed `func` argument. So you can either act as above, or instead override `invoke`. You do lose some additiona parameter checking that is useful, however, and thus it is not recommended.

### `toolify` decorator

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

To create an agent, you have several options. All agents are tools that utilize LLMs, and there are a few different ways to implement them based on your needs.

In order to create an agent, you generally need to provide:

1. An explanation for what the overall goal of the agent is (and how to accomplish it) and...
2. A method to take the output from the LLM and extract a result from it.

### Using SimpleAgent

The easiest way to create an agent is to use `SimpleAgent`, which allows you to create an agent by passing functions for prompt preparation and result extraction:

```python
from arkaine.tools.agent import SimpleAgent
from arkaine.tools.tool import Argument
from arkaine.llms.llm import LLM

# Create agent with functions
agent = SimpleAgent(
    name="my_agent",
    description="A custom agent",
    args=[Argument("task", "The task description", "str", required=True)],
    llm=my_llm,
    prepare_prompt=lambda context, **kwargs: f"Perform the following task: {kwargs['task']}",
    extract_result=lambda context, output: output.strip()
)
```

### Inheriting from Agent

For more complex agents, you can inherit from the `Agent` class. Implement the required `prepare_prompt` and `extract_result` methods:

```python
from arkaine.tools.agent import Agent

class MyAgent(Agent):
    def __init__(self, llm: LLM):
        args = [
            Argument("task", "The task description", "str", required=True)
        ]
        super().__init__("my_agent", "A custom agent", args, llm)
        
    def prepare_prompt(self, context, **kwargs) -> Prompt:
        """
        Given the arguments for the agent, create the prompt to feed to the LLM
        for execution.
        """
        return f"Perform the following task: {kwargs['task']}"

    def extract_result(self, context, output: str) -> Optional[Any]:
        """
        Given the output of the LLM, extract and optionally transform the result.
        Return None if no valid result could be extracted.
        """
        return output.strip()
```

### Creating IterativeAgents

`IterativeAgents` are agents that can repeatedly call an LLM to try and perform its task, where the agent can identify when it is complete with its task by returning a non-None value from `extract_result`. To create one, inherit from the `IterativeAgent` class:

```python
from arkaine.tools.agent import IterativeAgent

class MyIterativeAgent(IterativeAgent):
    def __init__(self, llm: LLM):
        super().__init__(
            name="my_iterative_agent",
            description="A custom iterative agent",
            args=[],
            llm=llm,
            initial_state={"attempts": 0},  # Optional initial state
            max_steps=5  # Optional maximum iterations
        )
    
    def prepare_prompt(self, context, **kwargs) -> Prompt:
        attempts = context["attempts"]
        context["attempts"] += 1
        return f"Attempt {attempts}: Perform the following task: {kwargs['task']}"
    
    def extract_result(self, context, output: str) -> Optional[Any]:
        # Return None to continue iteration, or a value to complete
        if "COMPLETE" in output:
            return output
        return None
```

The key differences in `IterativeAgent` are:
- You can provide `initial_state` to set up context variables
- You can set `max_steps` to limit the number of iterations
- Returning `None` from `extract_result` will cause another iteration
- The agent continues until either a non-None result is returned or `max_steps` is reached

You can optionally pass an initial state when implementing your `IterativeAgent`. This is a dictionary of key-value pairs that will be used to initialize the context of the agent, allowing you to utilize the context to handle state throughout the `prepare_prompt` and `extract_result` methods.

## Chats

Chats are assumed to inherit from the `Chat` abstract class. They follow some pattern of interaction with the user. Chats create `Conversation`s - these are histories of messages shared between 2 or more entities - typically the user or the agent, but not necessarily limited to this scope. The `Chat` class includes the ability to determine whether an incoming message is a new conversation, or a continuation of the previous conversation.


### SimpleChat

The `SimpleChat` class is currently the sole implementation, though more are planned. It is deemed "simple" as it only supports the pattern of one user to one agent in a typical user message to agent response pattern.

- Multiple conversations with isolated histories
- Tool/agent integration for enhanced capabilities  
- Conversation persistence
- Custom agent personalities
- Multiple LLM backends

#### Basic Usage

Here's a simple example of creating and using SimpleChat:

```python
from arkaine.chat.simple import SimpleChat
from arkaine.chat.conversation import FileConversationStore
from arkaine.llms.openai import OpenAI

# Initialize components
llm = OpenAI()
store = FileConversationStore("path/to/store")
tools = [tool1, agent1]

# Create chat instance
chat = SimpleChat(
    llm=llm,
    tools=tools,
    store=store,
    agent_name="Rose",  # Optional, defaults to "Arkaine"
    user_name="Abigail",      # Optional, defaults to "User"
)

while True:
    msg = input("Abigail: ")
    if msg.lower() in ["quit", "exit"]:
        break

    response = chat(message=msg)
    print(f"Rose: {response}")
```

#### Advanced Usage

SimpleChat can be customized with different backends, personalities, and tool configurations:

* `personality` - a brief sentence or so describing the prefered personality of the agent's responses.
* `conversation_auto_active` - if set, the chat will automatically continue a conversation if it has been within the specified time window of the prior conversation; otherwise, an LLM is asked to consider whether or not the current message belongs in a new conversation or the prior.

#### Tool Integration

SimpleChat can leverage tools to enhance its capabilities. When a user's message implies a task that could be handled by a tool, SimpleChat will automatically identify and use the appropriate tool.

It does this by asking an LLM to identify from the prior message and the context of prior messages in the conversation, paired with descriptions of the tools, if any "tasks" can be identified that could benefit from a tool. Once generated, each task is individually fed into a `Backend`.

## BackendAgents

`BackendAgents` are agents that utilize a `Backend` to perform its task. A `Backend` is a system that empowers an LLM to utilize tools and detect when it is finished with its task. To create one, inherit from the `BackendAgent` class.

You need two things for a BackendAgent:

1. An agent_explanation, which is fed to the LLM through the backend's prompt to tell the LLM what it is expected to be.
2. A method that, given the arguments, returns a dictionary of arguments for the backend. Almost always (unless the backend specifies otherwise) the expected format is:

```python
{
    "task": "..."
}
```

...wherein `task` is a text that describes the individual task at hand.

```python
from arkaine.tools.agent import BackendAgent

class MyBackendAgent(BackendAgent):
    def __init__(self, backend: Backend):
        super().__init__("my_backend_agent", "A custom backend agent", [], backend)
    
    def prepare_for_backend(self, **kwargs):
        # Given the arguments for the agent, transform them
        # (if needed) for the backend's format. These will be
        # passed to the backend as arguments.
        
        question = kwargs["question"]

        return {
            "task": f"Answer the following question: {question}",
        }
```

Note that the `prepare_for_backend` method is optional. If you do not implement it, the backend agent will pass the arguments as-is to the backend.

### Creating a Custom Backend

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
        return ?
    
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
- `Google` - utilizes Google Gemini's built in tool calling API
- `Ollama` - utilizes Ollama's built in tool calling API for models that support it - be sure to check the Ollama docs for more information.
- `ReAct` - a backend that utilizes the Thought/Action/Answer paradigm to call tools and think through tasks.
- `Python` - utilize python coding within a docker environment to safely execute LLM code with access to your tools to try and solve problems.


## LLMs

Arkaine supports multiple integrations with different LLM interfaces:

- **OpenAI**
- **Anthropic Claude**
- **Groq** - cheap hosted offering of multiple open sourced models
- **Ollama** - local offline models supported!
- **Google** - utilizes Google's Gemini API

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

Often it is necessary to include the context limits of models so the context_length can be properly set.

# Quick Start

Here's a simple example of creating and using an agent:

```python
from arkaine.llms.openai import OpenAI
from arkaine.tools.agent import Agent

# Initialize the LLM
llm = OpenAI(api_key="your-api-key")

# Define a simple agent
class MyAgent(Agent):

    def init(self, llm):
        super().init("simple_agent", "A simple agent", [], llm)

    def prepare_prompt(self, ctx, kwargs):
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

- `Weather` - Get current weather information for any location using OpenWeatherMap API. Supports multiple unit systems (metric/imperial) and dict or nice readable string outputs.

- `LocalSearch` - Given a query, location and radius (or hardcode the location), this tool allows for searching for local entities via Google Maps/Google Places API. Great for scanning for local businesses or locations.

- `WebSearcher` - given a topic or task, generate a list of potentially relevant queries perform a web search (defaults to DuckDuckGo, but compatible with Google and Bing). Then, given the results, isolate the relevant websites that have a high potential of containing relevant information.

- `Wikipedia` - Given a question, this agent will attempt to retrieve the Wikipedia page on that topic and utilize it to answer the question.

# Connectors

It's one thing to get an agent to work, it's another to get it to work when you specifically want it to, or in reaction to something else. For this arkaine provides *connectors* - components that stand alone and accept your agents as tools, triggering them in a configurable manner.

Current connectors include:

- [`API`](#api) - Given a set of tools, instantly create a web API that can expose your agents to any other tools.
- [`CLI`](#cli) - Create a set of terminal applications for your agents for quick execution.
- [`Schedule`](#schedule) - Schedule your agents to trigger at a set time or at recurring intervals 
- [`RSS`](#rss) - Have your agents routinely check RSS feeds and react to new content.
- [`Inbox`](#inbox) - Agents that will react to your incoming e-mails.


## API

The API connector allows you to expose your tools and agents as HTTP endpoints, complete with automatic OpenAPI documentation, authentication support (JWTs), and flexible input/output handling.

### Basic Usage

The simplest way to expose a tool is to create an API instance with your tool and start serving:

```python
from arkaine.connections import API

# Create API with a single tool
api = API(my_agent)
api.serve()  # Starts server at http://localhost:8000
```

For multiple tools with a custom prefix:

```python
# Create API with multiple tools and custom route prefix
api = API(
    tools=[agent1, tool1, agent2],
    name="MyAPI",
    prefix="/api/v1"
)
api.serve(port=9001)
```

### Authentication

The API connector supports JWT-based authentication. You can either create your own Auth implementation or use the built-in `JWTAuth`:

```python
from arkaine.connections import API, JWTAuth

# Create auth handler with secret and API keys
auth = JWTAuth.from_file("auth_config.json")  # Or JWTAuth.from_env()

# Create authenticated API
api = API(
    tools=my_tools,
    auth=auth
)

# Get auth token
token = auth.issue(AuthRequest(tools=["tool1"], key="my-api-key"))

# Make authenticated request
# curl -H "Authorization: Bearer {token}" http://localhost:8000/api/tool1
```

To generate an authentication configuration file:

```python
auth = JWTAuth(secret="your-secret", keys=["your-api-key"])
auth.create_key_file("auth_config.json")
```

Note that this handles authorizaton as well as authentication, wherein a JWT token can give access to either "all" or individual agents/tools.

### Advanced Usage

```python
api = API(
    tools=[tool1, tool2],
    name="MyAPI",
    description="Custom API description",
    prefix="/api/v1",
    api_docs="/docs",  # OpenAPI docs location
    auth=JWTAuth.from_env()
)

# Configure server options
api.serve(
    host="0.0.0.0",
    port=8080,
    ssl_keyfile="path/to/key.pem",
    ssl_certfile="path/to/cert.pem",
    workers=4,
    log_level="info"
)
```

### Headers

Special headers that modify API behavior:

- `X-Return-Context`: Set to "true" to include execution context in response
- `X-Context-ID`: Returned in response with context identifier
- `Authorization`: Bearer token for authenticated endpoints

### Response Format

Successful responses:
```json
{
    "result": "<tool output>",
    "context": "<context data if requested>"
}
```

Error responses:
```json
{
    "detail": "Error message",
    "context": "<context data if requested>"
}
```

### Custom Authentication

You can implement custom authentication by inheriting from the `Auth` class:

```python
from arkaine.connections import Auth, AuthRequest

class CustomAuth(Auth):
    def auth(self, request: Request, tool: Tool) -> bool:
        # Implement authentication logic
        return True
        
    def issue(self, request: AuthRequest) -> str:
        # Implement token issuance
        return "token"

api = API(tools=my_tools, auth=CustomAuth())
```

## CLI

The CLI connector allows you to instantly create command-line applications from your tools and agents. It provides rich help text, multiple input/output methods, and preserves all tool documentation.

### Basic Usage

The simplest way to create a CLI is to wrap a single tool:

```python
from arkaine.connections import CLI

# Create CLI for a single tool
cli = CLI(my_tool)
cli()
```

For multiple tools:

```python
# Create CLI with multiple tools
cli = CLI(
    tools=[tool1, agent1, tool2],
    name="MyToolkit",
    help_text="A collection of useful tools"
)
cli()
```

### Features

- **Rich Help Text**: Automatically generates help text from tool documentation
- **Multiple Input Methods**:
  - Standard arguments: `--arg value`
  - File input: `--arg @filename` or `--arg-file filename`
  - JSON input: `--json-input '{"arg": "value"}'` or `--json-input @file.json`
  - Pipe input: `echo 'value' | command` or `echo '{"arg":"value"}' | command`
- **Multiple Output Methods**:
  - Standard output (default)
  - File output: `--output-file filename`
  - Append mode: `--output-append --output-file filename`
- **Example Preservation**: Tool examples are converted to CLI usage examples

### Example Usage

For a single tool:

```bash
# Show help
$ my-tool --help

# Basic usage
$ my-tool --input "Hello World"

# File input
$ my-tool --input @input.txt
$ my-tool --input-file input.txt

# JSON input
$ my-tool --json-input '{"input": "Hello", "count": 3}'
$ my-tool --json-input @params.json

# Pipe input
$ echo "Hello World" | my-tool
$ echo '{"input": "Hello"}' | my-tool

# Output to file
$ my-tool --input "Hello" --output-file result.txt
$ my-tool --input "World" --output-file result.txt --output-append
```

For multiple tools:

```bash
# Show available tools
$ my-toolkit --help

# Use specific tool
$ my-toolkit tool1 --input "Hello"
$ my-toolkit agent1 --query "What is the weather?"
```

## Schedule

The Schedule connector allows you to run your agents on a schedule, whether that's a one-time future execution or a recurring task. It provides flexible scheduling options and persistent task storage.

### Basic Usage

The simplest way to schedule a task is to create a Task with a tool and when to trigger it:

```python
from arkaine.connections import Schedule, Task
from arkaine.utils.interval import Interval
from datetime import datetime, timedelta

# Create a task that runs once in 5 minutes
future_time = datetime.now() + timedelta(minutes=5)
one_time_task = Task(
    tool=my_tool,
    args={"input": "Hello World"},
    trigger_at=Interval(future_time)
)

# Create a task that runs every hour
hourly_task = Task(
    tool=my_agent,
    args={"query": "What's new?"},
    trigger_at=Interval(datetime.now(), recur_every=Interval.HOURLY)
)

# Add tasks to schedule and run
schedule = Schedule([one_time_task, hourly_task])
schedule.run()
```

### Intervals

Intervals define when tasks should trigger. They can be one-time or recurring:

```python
from arkaine.utils.interval import Interval

# One-time intervals
future = datetime.now() + timedelta(hours=2)
one_time = Interval(future)  # Triggers once at future time

# Built-in recurring intervals
hourly = Interval(datetime.now(), Interval.HOURLY)      # Every hour
daily = Interval(datetime.now(), Interval.DAILY)        # Every day
twice_daily = Interval(datetime.now(), Interval.TWICEADAY)  # Every 12 hours
weekday = Interval(datetime.now(), Interval.WEEKDAYS)   # Every weekday
weekend = Interval(datetime.now(), Interval.WEEKENDS)   # Every weekend day
weekly = Interval(datetime.now(), Interval.WEEKLY)      # Every week
monthly = Interval(datetime.now(), Interval.MONTHLY)    # Every month
yearly = Interval(datetime.now(), Interval.YEARLY)      # Every year

# Custom time-based intervals
custom_seconds = Interval(datetime.now(), "30:seconds")  # Every 30 seconds
custom_minutes = Interval(datetime.now(), "15:minutes")  # Every 15 minutes
custom_hours = Interval(datetime.now(), "4:hours")      # Every 4 hours
```

### Task Storage

Tasks can be persisted to disk and reloaded, allowing schedules to survive program restarts:

```python
from arkaine.connections import FileScheduleStore

# Create a store
store = FileScheduleStore("path/to/tasks")

# Create schedule with persistent storage
schedule = Schedule(store)

# Add new task - automatically persisted
task = Task(
    tool=my_tool,
    args={"input": "Hello"},
    trigger_at=Interval(datetime.now(), "1:hours")
)
schedule.add_task(task)
```

When reloaded, the schedule will utilize the store to load tasks and continue running as scheduled.

### Task Management

Tasks can be:
- Paused/unpaused
- Removed from schedule
- Monitored for execution time history
- Persisted to storage
- Automatically reloaded on schedule creation

## RSS

The RSS connector allows you to monitor RSS/Atom feeds and trigger agents when new items are detected. It supports multiple feeds with different check intervals and persistent storage of what items you've seen and processed.

### Basic Usage

The simplest way to monitor RSS feeds is to create Feed objects with check [intervals](#intervals) and agents/tools to trigger:

```python
from arkaine.connections import RSS, Feed
from datetime import datetime

# Create feeds with different check intervals
feeds = [
    Feed("http://example.com/rss", "30:minutes"),  # Check every 30 minutes
    Feed("http://another.com/feed", "1:hours"),    # Check every hour
]

# Create RSS monitor with feeds and tools
rss = RSS(feeds=feeds, tools=[my_agent])

# Start monitoring
rss.start()
```

Your tools will receive a list of `Item` objects that contain:
- title: The item's title
- description: A short description/summary
- link: URL to the full content
- published: Publication date
- content: The full content if available

### Features

- **Multiple Feed Support**: Monitor any number of RSS/Atom feeds
- **Flexible Check Intervals**: Set different check intervals per feed
- **Persistent Storage**: Track seen items to prevent duplicate processing
- **Parallel Processing**: Concurrent feed checking with configurable worker count
- **Content Extraction**: Built-in HTML-to-markdown conversion for content
- **PDF Support**: Automatic handling of PDF content in feeds

### Advanced Usage

```python
from arkaine.connections import RSS, Feed, FileStore
from arkaine.utils.interval import Interval

# Create persistent storage
store = FileStore("path/to/store")

# Create RSS monitor with custom configuration
rss = RSS(
    feeds=[
        Feed("http://news.com/rss", "15:minutes"),
        Feed("http://blog.com/feed", "1:hours")
    ],
    store=store,                # Persist seen items
    tools=[agent1, agent2],      # Multiple tools
    max_workers=5,             # Parallel feed checking
    feed_timeout=30            # Timeout for feed checks
)

# Start monitoring
rss.start()

# Add new feed while running
rss.add_feed(Feed("https://hlfshell.ai/index.xml", "45:minutes"))

# Add new tool while running
rss.add_tool(new_tool)

# Stop monitoring
rss.stop()
```

### Storage

By default, RSS uses a temporary file store that cleans up on exit. This does not allow persistence between program restarts. You can either use the `FileStore` or create your own.

Using `Filestore` is easy:
```python
from arkaine.connections import RSS, Feed, FileStore

# Create a store
store = FileStore("path/to/store")

# Create RSS monitor with custom configuration
rss = RSS(feeds=feeds, store=store)
```

You can also implement your own storage by inheriting from `Store`:

```python
from arkaine.connections import Store, Feed, Item

class CustomStore(Store):
    def save_feed(self, feed: Feed) -> None:
        # Save feed state
        pass
        
    def load_feed(self, feed: Feed) -> Optional[Feed]:
        # Load feed state
        pass
        
    def save_item(self, item: Item) -> None:
        # Save seen item
        pass
        
    def load_item(self, item: Item) -> Optional[Item]:
        # Load seen item
        pass

rss = RSS(feeds=feeds, store=CustomStore())
```

### Working with Items

The RSS connector provides rich item objects that can be used to extract content:

```python
from arkaine.connections import Item
from arkaine.tools.toolify import toolify


@toolify
def process_items(items: List[Item]):
    for item in items:
        # Basic metadata
        print(f"Title: {item.title}")
        print(f"Published: {item.published}")
        print(f"Link: {item.link}")
        
        # Get full content
        website = item.get_website()
        content = website.get_markdown()  # Convert to markdown
        
        # Process content...
```

### Error Handling

The RSS connector handles various error conditions:
- Feed connection timeouts
- Invalid feed formats
- Content extraction failures
- Storage errors

Failed feed checks will be retried on the next interval, and errors won't stop other feeds from being processed.

## Inbox

The Inbox connector allows you to monitor email accounts and trigger tools/agents based on incoming emails. It supports various email providers including Gmail, Outlook, Yahoo, AOL, and iCloud.

### Providers

The Inbox connector works with any IMAP server, but has built in "easy" support for the following services:

* gmail
* outlook
* yahoo
* icloud

### Usage

`call_when` is a dictionary that maps filters to tools/agents. The filter is a combination of one or more `EmailFilter` objects, and the tool is the tool to call when the filter is met.


```python
from arkaine.connections import Inbox, EmailFilter
from arkaine.tools import Tool

# Create an inbox that checks every 5 minutes
inbox = Inbox(
    call_when={
        EmailFilter(subject_pattern="Important:.*"): notification_tool,
        EmailFilter(sender_pattern="boss@company.com"): urgent_tool
    },
    username="your.email@gmail.com",
    password="your-app-password",  # For Gmail, use App Password
    service="gmail",
    check_every="5:minutes"
)

# Start monitoring
inbox.start()
```

You can scan multiple folders, specify different filters (or add them together), and use lambdas or other functions as filters as long as it returns a boolean.

```python
from arkaine.connections import Inbox, EmailFilter
from datetime import datetime, timedelta

# More complex setup
inbox = Inbox(
    call_when={
        # Combine multiple filters
        EmailFilter(subject_pattern="Urgent:.*") + 
        EmailFilter(sender_pattern=".*@company.com"): my_agent,
        
        # Custom filter function
        lambda msg: "priority" in msg.tags: priority_tool
    },
    username="your.email@gmail.com",
    password="your-app-password",
    service="gmail",
    check_every="5:minutes",
    folders=["INBOX", "[Gmail]/Important"],  # Monitor multiple folders
    ignore_emails_older_than=datetime.now() - timedelta(days=1),
    max_messages_to_process=100
)

# Add error handling
inbox.add_listener("error", lambda e: print(f"Error: {e}"))

# Add message handling
inbox.add_listener("send", lambda msg, filter, ctx: print(f"Processed: {msg.subject}"))

inbox.start()
```

### Note on Gmail usage

For Gmail accounts, you'll need to use an App Password instead of your regular account password. This is a security requirement from Google for third-party applications.

1. Go to [Google App Passwords](https://myaccount.google.com/apppasswords)
2. Select "Mail" and your device
3. Use the generated 16-character password as your `password` parameter

Note that the G-Mail `Important` folder is labeled as `[Gmail]/Important`, and can be specified in `Inbox`'s `folders` parameter.


### Custom Email Filters

You can create sophisticated email filters by combining patterns and custom functions:

```python
# Filter by subject
subject_filter = EmailFilter(subject_pattern=r"Important:.*")

# Filter by sender
sender_filter = EmailFilter(sender_pattern=r".*@company\.com")

# Filter by body content
body_filter = EmailFilter(body_pattern=r"urgent")

# Filter by tags
tag_filter = EmailFilter(tags=["important", "urgent"])

# Custom filter function
def custom_filter(message):
    return "priority" in message.subject.lower()

# Combine filters
combined_filter = subject_filter + sender_filter + custom_filter

# Use in inbox
inbox = Inbox(
    call_when={combined_filter: notification_tool},
    # ... other configuration ...
)
```

You can also specify whether you want all specified filters to be met, or if *any* of them are met, via the `match_all` attribute.

Filters can be combined by adding them together, creating a new filter that checks to see if both filters are met - this can be done ad infinitum.

`EmailFilter.all()` creates a filter that accepts all e-mails.

### Message Store

By default, the Inbox connector keeps track of processed messages in a local file. You can provide your own message store implementation by inheriting from `SeenMessageStore`:

```python
from arkaine.connections import SeenMessageStore

class CustomStore(SeenMessageStore):
    def add(self, message):
        # Implementation for storing a message
        pass
        
    def contains(self, message) -> bool:
        # Implementation for checking if a message exists
        return False

inbox = Inbox(
    # ... other configuration ...
    store=CustomStore()
)
```

# Spellbook

Spellbook provides a real-time web interface for monitoring and interacting with your arkaine tools and agents. It consists of two main components:

- A WebSocket server that broadcasts tool/agent events and accepts commands. This is hosted by your agent program.
- A web interface for visualizing execution, debugging, and triggering tools. This can be ran separately or from within your agent program.


# `quickstart` function

There are plenty of cool features that you'll commonly want to use when building arkaine AI agents. To make it easy to get set up with most of them, the `quickstart` function is provided.

- Context storage configuration
- Logging setup
- Spellbook socket/server initialization
- Proper cleanup on program exit

## Basic Usage

```python
from arkaine import quickstart

# Basic setup with in-memory context storage
done = quickstart()

# When finished
done()
```

## Configuration Options

The function accepts several optional parameters:

```python
quickstart(
    context_store=None,  # Context storage configuration
    logger=False,        # Enable global logging
    spellbook_socket=False,  # Spellbook socket configuration
    spellbook_server=False,  # Spellbook server configuration
) -> Callable[[], None]  # Returns cleanup function
```

### Context Storage

You can configure context storage in several ways:

```python
# Use in-memory storage (default)
quickstart()

# Use file-based storage with path
quickstart(context_store="path/to/store")

# Use custom context store
from arkaine.utils.store.context import CustomContextStore
quickstart(context_store=CustomContextStore())
```

### Logging

Enable global logging for better debugging:

```python
quickstart(logger=True)
```

### Spellbook Integration

Configure Spellbook socket and server:

```python
# Enable both with default ports
quickstart(spellbook_socket=True, spellbook_server=True)

# Specify custom ports
quickstart(spellbook_socket=8001, spellbook_server=8002)

# Use custom instances
from arkaine.spellbook.socket import SpellbookSocket
from arkaine.spellbook.server import SpellbookServer

quickstart(
    spellbook_socket=SpellbookSocket(port=8001),
    spellbook_server=SpellbookServer(port=8002)
)
```

## Cleanup

The function returns a cleanup callable that should be called when you're done:

```python
done = quickstart(
    context_store="path/to/store",
    logger=True,
    spellbook_socket=True,
    spellbook_server=True
)

# Your code here...

# Clean up when finished
done()
```

Note that cleanup is also automatically registered for program exit and signal handlers (SIGTERM/SIGINT).


### Coming Soon:

These are planned connectors:

- `Chat` - a chat interface that is powered by your agentic tools.
- `Discord` - Agents that will react to your Discord messages.
- `HomeAssistant` - implement AI into your home automation systems
- `Slack` - Agents that will react to your Slack messages or act as a bot
- `SMS` - an SMS gateway for your text messages to trigger your agents
