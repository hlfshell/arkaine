"""
This tutorial example demonstrates how to use the iterative researcher, create
agents, attach event listeners to a context, and make async agent calls. It
shows how arkaine's event broadcasting mechanism can track information no matter
how nested your agents might become...

..and also provides a useful tool for to research topics for you!

The iterative researcher is an agent that repeatedly studies a given
topic/question, querying a web search engine, collecting possibly relevant
websites, and then finally reading through the most likely to contain
information relevant to the topic/question, generating "findings" - short dense
summaries of important information relevant to the topic at hand.

Finally, it generates a report for human consumption.

Note: The researcher tends to hit rate limits pretty quickly - if you encounter
this by running into 429 errors, try taking a break between executions or swap
the search engine provider to a paid one.


Important points:
- arkaine's Context objects broadcast various events (e.g.,
  tool calls, tool returns, errors) during execution.
- These events allow you to monitor the progress and outputs of the tool in real
  time.
- Child contexts are created for sub-tasks; the root context propagates events
  from its children.
- By attaching listeners to the root context you can capture every event
  from the entire chain of agents.
"""

import json
import time
from threading import Lock


# Let's create a detailed topic. Make sure that it is not just a simple
# query, but rather a complex question worth the time of the large scale
# search we're performing.
topic = (
    "What are the must-know papers and techniques learned over the "
    "past two years about implementing AI (transformers, LLMs, VLMs, "
    "VLAs, diffusion models, world models) specifically for robotics "
    "applications."
)

# The depth for the iterative researcher is the number of iterations it
# will perform (1 indexed). So a depth of 2 means that it will perform
# significant research on the topic, consider its findings, then generate
# a second round of questions to further research.
depth = 2

"""
serp_provider is the search engine provider to use for the iterative researcher.
You can use duckduckgo for free, but you may get rate limited quickly. The
others will require an API key to utilize. We currently support:
1. duckduckgo (default)
2. google
3. bing
4. exa
5. firecrawl
6. tavily
"""
serp_provider = "duckduckgo"


# The key points to note on what we're importing:
# 1. The researchers (iterative and WebResearcher)
# 2. OpenAI LLM (you can use deepseek or google here)
# 3. The ReportGenerator, which is another agent generates a report from

from arkaine.llms.openai import OpenAI
from arkaine.toolbox.research.web_research import WebResearcher
from arkaine.toolbox.websearch import Websearch
from arkaine.toolbox.research.iterative_researcher import IterativeResearcher

# Alright, that's it! Now let's get to work building our research agent.

# Setup an OpenAI llm for the research process. We use o3-mini. Generally
# for this you want a large context *reasoning* model for best results, so
# DeepSeek R1 or Gemini or Claude-3.7-reasoning are all good choices.
llm = OpenAI("o3-mini")

"""
Initialize tools for web search and research. We only do this because we want to
set the provider; otherwise we could just skip this and directly instantiate
IterativeResearcher, which defaults to use the websearch tool. The WebResearcher
is a tool that extends the standard researcher tool, specifically pointing it at
web search. Other researchers can look at your documents, or specific subsets of
resources. For now, the sum total of human knowledge throughout the web should
be fine.
"""
websearch = Websearch(provider=serp_provider)
researcher = WebResearcher(llm, websearch=websearch)

"""
A researcher is an agent that, given an LLM, a way to search for resources,
will crawl through that searcher to find worthwhile resources, consume them,
and generate "findings". A finding is a short dense summary of important
information relevant to the topic or question at hand.

An IterativeResearcher takes a researcher and then allows it to iterate
over its information for longer times, allowing it to ask follow-up questions
presented during its existing research. It can be limited by a set of depth.
"""
iterative_researcher = IterativeResearcher(
    llm, max_depth=depth, researcher=researcher
)

# Run iterative research - this will take some time.
print("Starting iterative research...\n")

# We want to run out researcher - we could just call it like
# iterative_researcher.call(topic), but we want to monitor its
# progress so we'll do it with async_call.
ctx = iterative_researcher.async_call(topic)

# Here we'll store the data of progress as we receive it as events
# broadcasted throughout execution of our research. We use a lock to
# ensure that our data access is thread-safe.
update_lock = Lock()
data = {
    "topics_researched": [],
    "websites_considered": [],
    "websites_visited": [],
    "findings_generated": [],
}


# We'll import what we need for the event listeners and the context
# class for working with it.


from arkaine.tools.events import Event
from arkaine.toolbox.research.researcher import (
    FindingsGeneratedEvent,
    ResearchQueryEvent,
    ResourceFoundEvent,
)
from arkaine.tools.context import Context


# This is our event listener - it will be called whenever an event is
# broadcasted throughout the course of our research. We use the event type to
# determine what to do with the event data.
def update(ctx: Context, event: Event):
    with update_lock:
        if event.is_a(ResearchQueryEvent):
            data["topics_researched"].append(event.data["query"])
        elif event.is_a(ResourceFoundEvent):
            data["websites_considered"].append(event.data["resource"].source)
        elif event.is_a(FindingsGeneratedEvent):
            data["websites_visited"].extend(event.data["findings"])
            data["findings_generated"].extend(event.data["findings"])


# We attach listeners to the context to monitor the progress of the
# research, by looking for events we know are broadcasted in the
# researchers.
ctx.add_event_listener(update, ResearchQueryEvent)
ctx.add_event_listener(update, ResourceFoundEvent)
ctx.add_event_listener(update, FindingsGeneratedEvent)

# The context status is calculated on query, and can be either
# "running", "complete", or "error".
while ctx.status == "running":
    with update_lock:
        print("\033[K", end="")
        print(
            f"Depth: {ctx.get('iteration', 0)} | "
            f"Topics Researched: {len(data['topics_researched'])} | "
            f"Websites Considered: {len(data['websites_considered'])} | "
            f"Websites Visited: {len(data['websites_visited'])} | "
            f"Findings Generated: {len(data['findings_generated'])}",
            end="\r",
        )
    time.sleep(1)

print()

# If the context is in an error state, we raise the exception,
# also saved to the context for reference
if ctx.status == "error":
    print("Error:", ctx.exception)
    raise ctx.exception

print("*" * 100)
print("Findings:\n", ctx.output)
print("*" * 100)

# Save the findings to a json file so you can access them later to play with
# different generations, or to use as context for another agent! To do this
# we'll use arkaine's recursive_to_json function to convert the findings to a
# json string.

from arkaine.internal.to_json import recursive_to_json

with open("findings.json", "w") as f:
    json.dump(recursive_to_json(ctx.output), f, indent=2)

print("\nIterations:", ctx["iteration"])
print("Collected questions:", ctx["all_topics"], "\n")

# Generate a report based on the research findings. The generator is another
# agent that takes the topic and the findings and generates a report. We call it
# just like we would any other function.
from arkaine.toolbox.research.generator import ReportGenerator

generator = ReportGenerator(llm)

report = generator(topic, ctx.output)

print("Generated Report:\n", report)

# Write the report to markdown file.
with open("report.md", "w") as f:
    f.write(report)

print("Findings saved to findings.json")
print("Report saved to report.md")
