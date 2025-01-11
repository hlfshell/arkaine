"""
Arkaine - A batteries-included framework for DIY AI agents.

This module provides the core functionality for creating and managing AI agents
with built-in tools and capabilities.
"""

from arkaine.agent import Agent, BackendAgent, MetaAgent
from arkaine.backends.base import BaseBackend
from arkaine.tools.tool import Tool
from arkaine.tools.toolify import toolify

__version__ = "0.0.1-beta.1"
__author__ = "Keith Chester"
__email__ = "keith@hlfshell.ai"

__all__ = [
    "Agent",
    "MetaAgent",
    "BackendAgent",
    "Tool",
    "BaseBackend",
    "toolify",
]
