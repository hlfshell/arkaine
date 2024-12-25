# arcAIne

*We've trapped lightning into a rock and tricked it to think. Add some incantations (programming) and some summoning words (prompts) and let's see what we can cook up...*

Empower your summoned AI agents. arcAIne is a batteries-included framework built for DIY builders to create easy tool enhanced AI agents. Utilize completed agents to compose ever-more complex agents.

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



## Key Concepts

The framework uses the following key concepts:

- **LLM**: An instruct-based model that generates text (e.g., GPT-3.5, Claude, Llama, etc).
- **Tool**: A properly formatted piece of functionality that contains descriptors of what it does, how it works, and possibly includes examples. Can be called as a normal function in code, hiding much of the complexity.
- **Agent**: A type of tool that utilizes an LLM and possibly other tools to perform a function. The default agent is merely a singular LLM call performing the function for the agent.
    - **MetaAgent** - A meta agent is an agent that can repeatedly call an LLM to try and perform its task, where the agent can identify when it is complete with its task.
    - **BackendAgent** - A backend agent is an agent that utilizes a **backend** to perform its task.
- **Backend**: A backend is a system that empowers an LLM to utilize tools and detect when it is finished with its task.

## Installation

## Quick Start

Here's a simple example of creating and using an agent:

```python
TODO
```
