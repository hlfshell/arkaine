# arkaine

*We've trapped lightning into a rock and tricked it to think. Add some incantations (programming) and some summoning words (prompts) and let's see what we can cook up...*

Empower your summoned AI agents. arkaine is a batteries-included framework built for DIY builders to create easy tool enhanced AI agents. Utilize completed agents to compose ever-more complex agents.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

## Overview

This is a framework for experimenting with agent construction using Large Language Models (LLMs). The goal is to create a set of tools that make it possible to work with a wide variety of LLMs to create capable, simple agents. Agents themselves are also tools, allowing agents to consist of sub-agents for increasingly complex tasks.

## Who is this for?

This is a framework dedicated to making it easy to create agentic tools to perform a wide variety of tasks for the average DIY coder.

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

## Supported LLMs

- OpenAI (GPT-3.5, GPT-4)
- Anthropic Claude
- Groq
- Ollama (local models)

## Key Concepts

The framework uses the following key concepts:

- **LLM**: An instruct-based model that generates text (e.g., GPT-3.5, Claude, Llama, etc).
- **Tool**: A properly formatted piece of functionality that contains descriptors of what it does, how it works, and possibly includes examples. Can be called as a normal function in code, hiding much of the complexity.
- **Agent**: A type of tool that utilizes an LLM and possibly other tools to perform a function. The default agent is merely a singular LLM call performing the function for the agent.
    - **MetaAgent** - A meta agent is an agent that can repeatedly call an LLM to try and perform its task, where the agent can identify when it is complete with its task.
    - **BackendAgent** - A backend agent is an agent that utilizes a **backend** to perform its task.
- **Backend**: A backend is a system that empowers an LLM to utilize tools and detect when it is finished with its task.

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

toolify
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


## LLMs

Arkaine supports multiple integrations with different LLM interfaces:

- **OpenAI**: Supports GPT-3.5 and GPT-4 models.
- **Anthropic Claude**: A powerful LLM for various tasks.
- **Groq**: For specialized LLM tasks.
- **Ollama**: Supports local models for offline use.

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

# Flow

Agents can feed into other agents, but the flow of information between these agents can be complex! To make this easier, arkaine provdies several flow tools that maintain observability and handles a lot of the complexity for you.

- `Linear` - A flow tool that will execute a set of agents in a linear fashion, feeding into one another.

- `Conditional` - A flow tool that will execute a set of agents in a conditional fashion, allowing a branching of if/then/else logic.

- `Branch` - Given a singular input, execute in parallel multiple tools/agents and aggregate their results at the end.

- `ParallelList` - Given a list of inputs, execute in parallel the same tool/agent and aggregate their results at the end.

- `Retry` - Given a tool/agent, retry it until it succeeds or up to a set amount of attempts. Also provides a way to specify which exceptions to retry on.

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