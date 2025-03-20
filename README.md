# arkaine

Empower your summoned AI agents. arkaine is a batteries-included framework built for DIY builders, individuals, and small scale solutions.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

[![Join our Discord!](https://img.shields.io/badge/Discord-7289DA?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/6k7N2sV5xA)

## Overview

arkaine is built to allow individuals with a little python knowledge to easily create deployable AI agents enhanced with tools. While other frameworks are focused on scalable web-scale solutions, arkaine is focused on the smaller scale projects - the prototype, the small cron job, the weekend project. arkaine attempts to be batteries included - multiple features and tools built in to allow you to go from idea to execution rapidly.

# [📖 Documentation 👩‍🏫](https://arkaine.dev)

Documentation can be found at [arkaine.dev](https://arkaine.dev).

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
