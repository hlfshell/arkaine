# Examples

These examples are meant to both educate you on how to utilize arkaine ***AND*** provide some interesting step by step projects to learn from. ~~Crossed out~~ examples are works in progress.

## Getting Started

If you're completely new to arkaine, you should start with these examples in order, as they act as mini lessons.

* **my_first_tool.py** - walk through what tools are, what they do, how to use them, and how to make your own

* **my_first_agent.py** - tools are cool, but AI is cooler. Let's add some AI to our tools.

* **agents_at_work.py** - Agents are at their best when they can call tools.

* **context_state_and_you.py** - learn about arkaine's context system - how it tracks state, how to pass information between tools and their children, retry a failed long running agent job, and more.

* ~~**flow_control.py**~~ - learn about flow control in arkaine for more complex agent behaviors.

* ~~**debugging_with_spellbook.py**~~ - learn about ***spellbook***, arkaine's web debugging tool. Learn how to utilize it with your own programs and deep dive into what your programs are doing.

## Advanced

Once you've got a handle of things, you're probably excited to start building your own agents. Here's some mini sample projects that also walk you through, step by step, how to build your own projects.

* **scheduled_sms.py** - Using the `schedule` connector, we can schedule our AI agent to run on a regular interval, sending us a text message with an poem about how cool Ninja Turtles were. Like seriously that show was a banger.

* **inbox_agent.py** - In this example, we connect an AI agent to our e-mail `Inbox` connector. If we receive an e-mail from ourselves, the AI agent will read it and respond. Armed with a Google Maps powered local search tool, it's perfect for asking about where to grab food or buy a book.

* **research_agent.py** - In this example, we have an iterative search agent repeatedly scour the internet, finding relevant information to your question. Then it generates a full report on your question just minutes later.

* ~~**rss_and_email.py**~~ - In this example, we utilize an RSS feed to monitor a website for updates. Once an update is detected, we read the site, summarize it, and send ourselves an e-mail with the update
