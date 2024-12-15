# composable-agents

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

A framework for building composable LLM agents that can utilize tools and other agents as building blocks for complex tasks.

## Overview

This is a framework for experimenting with agent construction using Large Language Models (LLMs). The goal is to create a set of tools that make it possible to work with a wide variety of LLMs to create capable, simple agents. Agents themselves are also tools, allowing agents to consist of sub-agents for increasingly complex tasks.

## Features

- 🔧 Easy tool creation and programmatic tool prompting for models
- 🤖 Agents are tools that can be used by other agents
- 🧩 Agents can be "composed" by simply combining these tools and agents together
- 🔀 Internal asynchronous and parallel routing for agents
- 🔄 Multiple backend implementations for different LLM interfaces
- 🧰 Built-in common tools (web search, file operations, etc.)

## Supported LLMs

- OpenAI (GPT-3.5, GPT-4)
- Anthropic Claude
- Groq
- Ollama (local models)
- More coming soon...

## Key Concepts

The framework uses the following key concepts:

- **LLM**: An instruction-following model that generates text (e.g., GPT-3.5, Claude, Llama)
- **Tool**: A properly formatted piece of functionality that contains descriptors of what it does, how it works, and possibly includes examples. When called like a function, it executes as a normal function.
- **Agent**: A type of tool that utilizes an LLM and possibly other tools to perform a function. The default agent is merely a singular LLM call performing the function for the agent.
    - **MetaAgent** - A meta agent is an agent that can repeatedly call an LLM to try and perform its task.
    - **BackendAgent** - A backend agent is an agent that utilizes a **backend** to perform its task.
- **Backend**: A backend is a system that empowers an LLM to utilize tools and detect when it is finished with its task.S

## Installation

## Quick Start

Here's a simple example of creating and using an agent:

```python
TODO
```
