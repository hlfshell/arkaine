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


# The key points to note here are we import:
# 1. The researchers (iterative and WebResearcher)
# 2. OpenAI LLM (you can use deepseek or gemini here)
# 3. The ReportGenerator, which is another agent generates a report from
from arkaine.internal.to_json import recursive_to_json
from arkaine.llms.openai import OpenAI
from arkaine.toolbox.research.generator import ReportGenerator
from arkaine.toolbox.research.iterative_researcher import IterativeResearcher
from arkaine.toolbox.research.researcher import (
    FindingsGeneratedEvent,
    ResearchQueryEvent,
    ResourceFoundEvent,
)
from arkaine.toolbox.research.web_research import WebResearcher
from arkaine.toolbox.websearch import Websearch
from arkaine.tools.context import Context
from arkaine.tools.events import Event


def main():
    # First we are just going to collect information from the user with
    # some sensible defaults.
    default_topic = (
        "What are the must-know papers and techniques learned over the "
        "past two years about implementing AI (transformers, LLMs, VLMs, "
        "VLAs, diffusion models, world models) specifically for robotics "
        "applications."
    )
    while True:
        user_topic = input(
            "Enter your research topic (press Enter to use default topic): "
        ).strip()
        topic = user_topic if user_topic else default_topic

        depth_raw = input("Enter the depth of the research (default is 2): ")
        depth = int(depth_raw) if depth_raw else 2

        provider = print("\nEnter the search provider. Your choices are:\n")
        print("1. duckduckgo (default)")
        print("2. google")
        print("3. bing")
        print("4. exa")
        print("5. firecrawl")
        print("6. tavily")

        provider_raw = input(
            "Enter the name of the provider or just hit enter: "
        ).strip()
        provider = provider_raw if provider_raw else "duckduckgo"

        print(f"\nResearching:\n{topic}\n")
        print(f"Depth: {depth}")
        print(f"Provider: {provider}")

        if input("Continue (yes/no)? : ").lower().strip() == "yes":
            break

    # Setup OpenAI llm for the research process. We use o3-mini. Generally
    # for this you want a large context reasoning model for best results.
    llm = OpenAI("o3-mini")

    # Initialize tools for web search and research. We only do this
    # because we want to set the provider; otherwise we could just
    # skip this and directly instantiate IterativeResearcher.
    websearch = Websearch(provider=provider)
    researcher = WebResearcher(llm, websearch=websearch)

    # Create the iterative research agent with a shared context.
    iterative_researcher = IterativeResearcher(
        llm, max_depth=depth, researcher=researcher
    )

    # Run iterative research
    print("Starting iterative research...\n")

    # We want to run out researcher - we could just call it like
    # iterative_researcher.call(topic), but we want to monitor its
    # progress so we'll do it with async_call.
    ctx = iterative_researcher.async_call(topic)

    update_lock = Lock()
    data = {
        "topics_researched": [],
        "websites_considered": [],
        "websites_visited": [],
        "findings_generated": [],
    }

    def update(ctx: Context, event: Event):
        with update_lock:
            if event._event_type == "research_query":
                data["topics_researched"].append(event.data["query"])
            elif event._event_type == "resource_found":
                data["websites_considered"].append(
                    event.data["resource"].source
                )
            elif event._event_type == "findings_generated":
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

    # Save the findings to a json file so you can access them
    # later to play with different generations.
    with open("findings.json", "w") as f:
        json.dump(recursive_to_json(ctx.output), f, indent=2)

    print("\nIterations:", ctx["iteration"])
    print("Collected questions:", ctx["all_topics"], "\n")

    # Generate a report based on the research findings. The generator
    # is another agent that takes the topic and the findings and generates
    # a report. We call it just like we would any other function.
    generator = ReportGenerator(llm)

    report = generator(topic, ctx.output)

    print("Generated Report:\n", report)

    # Write the report to markdown file.
    with open("report.md", "w") as f:
        f.write(report)

    print("Findings saved to findings.json")
    print("Report saved to report.md")


if __name__ == "__main__":
    main()
