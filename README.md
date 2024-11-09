# Composable Agents

This is the working repository for an experiment in agent construction in LLMs. The goal is create a set of tools that make it possible to work with tools with a wide variety of LLMs to create capable, simple agents. Then agents themselves are also tools, allowing agents to consist of sub agents for increasingly complex tasks.

# Definitions

The terms I am using follow these definitions:

LLM
: an instruction following model that generates text

Tool
: a properly formatted piece of functionality that contains descriptors of what it does, how it works, and possibly includes examples. When called like a function, it executes as a normal function.

Agent
: a type of tool that utilizes an LLM in some manner and possibly some tools to perform a function

Backend
: a manager of tool calling for an LLM, handling parsing results, tool calls, and other core components