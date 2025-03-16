from arkaine.tools.agent import Agent

"""
This example demonstrates how to create your first Agent. We'll cover
two kinds of agents and how to use them.

The first concept to understand that an Agent is a Tool. You call it,
it does "stuff", and it returns, just like a function. It has all
the niceties that a tool has. Thus, similar to how we can pass tools
to LLM models to allow them to figure out tool calling, so too can
we pass agents and except similar results. This allows us to build
increasingly more complex behavior by just *composing* agents from
other agents and tools.

These examples require an LLM, so let's create one. You'll need
an API key to use it (unless you use the local LLM options like
ollama).
"""

# LoadLLM is a helper function that allows quickly loading LLMs
# based on some global or environmental configuration.
# You don't have to use it - you can directly import that LLM
# you want from the arkaine.llms.<llm_provider> packages.
from arkaine.llms.loader import load_llm

llm = load_llm("openai")

# An LLM we can call like a function; it accepts a string or a Prompt (more on
# that in a moment).
first = llm(
    "Hello! How much wood would a woodchuck chuck if a woodchuck "
    "could chuck wood?"
)
print("LLM response:", first)

"""
Let's take a moment to talk about prompts. LLMs can take a string or a
Prompt, but what's a Prompt? Let's load it in.
"""

from arkaine.llms.llm import Prompt, RolePrompt

"""
A RolePrompt is a dict that typically specifies a role, and a set of content.

Basically, this:

{
    "role": "system",
    "content": "You are a helpful assistant that can answer questions."
}

This is a common pattern across LLM providers.

A Prompt is a list of RolePrompts.

LLMs are converting strings fed in into Prompts.

This is just something to keep in mind if you wish to specify roles for
given input, but otherwise can be ignored and you can just utilize strings.
"""

# Ok, now let's create an agent.


# We're often importing these from arkaine.tools to build out our tool / agents.
from arkaine.tools.argument import Argument
from arkaine.tools.example import Example
from arkaine.tools.result import Result
from arkaine.tools.agent import SimpleAgent, SimpleIterativeAgent

###############################################
# 0. What do you need to create an agent?
###############################################
"""
1. An LLM
2. A prompt
3. A function that takes the arguments fed to an agent, and returns the prompt
4. A function that takes the LLM output, and extracts the result

That's it! Let's see it in practice.
"""


###############################################
# 1. Creating an Agent with SimpleAgent
###############################################
"""
SimpleAgent lets you quickly create an agent by providing two helper functions:
  - prepare_prompt: Format the incoming arguments into a prompt for the LLM.
  - extract_result: Process the LLM's output to produce your final result.

This technique is analogous to building a function-based tool.
"""


# Let's create a simple prepare_prompt function. You'll always be passed
# a context, and the arguments passed to the agent. Here I specify it as
# a single argument, a keyword argument, or just expect arguments as a dict
# through *args and **kwargs. The surrounding tool will figure out the best
# way to pass the arguments to your function, but order must be preserved
# if using positional arguments.
def simple_prepare_prompt(context, question: str) -> str:
    """
    Prepare a prompt by asking the LLM to answer the provided question.
    """
    # Remember, a prompt or a string is fine to return.
    return f"Please answer the following question: {question}"


# Here we get the raw output from the LLM, and extract the result from the text.
# If you don't have any special extraction logic, you can just return the output
# as-is. That's it!
def simple_extract_result(context, output: str) -> str:
    """
    Extract the result from the dummy LLM response. Our dummy LLM prefixes
    responses with 'Simulated response: ', so we remove that.
    """
    return output.strip()


# Now let's create the simple agent. Note that it's really similar to making
# a tool!
simple_agent = SimpleAgent(
    name="simple_agent",
    description="A simple agent that answers a question",
    args=[
        Argument(
            "question", "The question to be answered", "str", required=True
        )
    ],
    llm=llm,  # Tell it what our LLM is
    # Pass it our functions
    prepare_prompt=simple_prepare_prompt,
    extract_result=simple_extract_result,
    examples=[],  # We could create examples if we wanted to for other tools
)

# That's it! Let's try it out.
print("=" * 100)
print("Simple Agent (simple_agent) demonstration:")
response = simple_agent(question="What is the capital of France?")
print("Response from simple_agent:", response)
print("=" * 100)


###############################################
# 2. Creating an Agent by subclassing Agent
###############################################
"""
Making a class a child of Agent allows you to have a lot more control
over the agent's behavior and some ability to handle state for the agent.

You'll need to implement the two methods we discussed above, but otherwise
it's quite simple.
"""


class PoemAgent(Agent):

    def __init__(self, llm=llm):
        super().__init__(
            llm=llm,
            name="poem_agent",
            description="Create a poem in a given style on a specific topic",
            args=[
                Argument(
                    "topic", "The topic of the poem", "str", required=True
                ),
                Argument(
                    "style",
                    "The style of the poem",
                    "str",
                    required=False,
                    default="Shakespearean",
                ),
            ],
        )

    # We need to implement prepare_prompt
    # Note that since we specify the default in the Argument, we don't
    # need to specify a default in the function signature.
    def prepare_prompt(self, context, topic: str, style: str):
        return f"Create a poem in the style of {style} on the topic of {topic}"

    # We need to implement extract_result
    def extract_result(self, context, output: str):
        return output


# Now let's create the agent.
poem_agent = PoemAgent()

# That's it! Let's try it out.
print("=" * 100)
print("Poem Agent (poem_agent) demonstration:")
topic = "A robot trying and failing to start a masked wrestling career"
style = "Shakespearean"
response = poem_agent(topic, style)
print(f"Topic: {topic}")
print(f"Style: {style}")
print(f"Poem:\n{response}")
topic = "A king charles cavalier being the cutest dog in the world"
style = "haiku"
response = poem_agent(topic, style)
print(f"Topic: {topic}")
print(f"Style: {style}")
print(f"Poem:\n{response}")
print("=" * 100)

"""
Pretty simple, but let's take a moment to talk about prompts and parsing.
"""
###############################################
# 3. Prompting and Parsing
###############################################
"""
Prompting is pretty important, so we have some tools built into arkaine to help
you out. First is the templater, which is designed to handle some niceties of
prompting for you. It's not fully featured like many other templating engines,
but you're welcome to bring those in to if you need it!
"""

from arkaine.utils.templater import PromptTemplate

# Let's say we have a prompt
prompt = """
You are a helpful assistant named {assistant_name}. Your responses should follow
as if you had a personality of {personality}.


The user has asked you to answer the following question:
{question}
Your response:
"""

# Make our template, setting some if we want.
template = PromptTemplate(
    prompt, defaults={"assistant_name": "Rose", "personality": "sassy"}
)

# We can render it with values to get our LLM ready prompts:
llm_prompt = template.render({"question": "What is the capital of France?"})
# or...
llm_prompt = template.render(
    {
        "question": "What is the capital of France?",
        "assistant_name": "Jane",
        "personality": "friendly",
    }
)
"""
We can also load from a file, which we won't do now since it doesn't exist. This
is useful because putting prompts in code can be a bit weird, or maybe you want
to dynamically choose prompts based on some condition.
"""
# template = PromptTemplate.from_file("my_prompt.prompt")


"""
...but loading prompts from a directory can be a bit weird if you're packaging
your code, so we have a helper for that.

Assuming that:

A) You have a prompts directory local to the caller's file
B) Have the extension of ".prompt"

PromptLoader is thread safe and will cache prompts in memory, preventing
multiple loads, but also only loading prompts when needed. Once loaded,
the prompt is cached and will be held in memory for faster access on the
next call.
"""

from arkaine.utils.templater import PromptLoader

# Load a prompt from the prompts directory.
# prompt = PromptLoader.load_prompt("my_prompt")
# ...we aren't doing it again for the reasons stated above. But you get
# the idea.

"""
Extracting the results from a stochastic model like an LLM can be tricky,
because we don't know if it will necessarily follow the output we desire
exactly. Thus we need to be quite flexible in how we extract results.

This can actually take the *most* time in the development of an agent, so
naturally arkaine has a helper for this. It won't work for every case, but
should take care of the most common ones!

Generally, this assumes you've prompted the model to make use of "labels"
for each kind of output that it is expected to return, such as:

THOUGHT: The thought of the model
ANSWER: The answer to the question

...and some combination thereof, case insensitive. So for this example,
we could...
"""

from arkaine.utils.parser import Parser

parser = Parser(["thought", "answer"])

# And then we could parse output such as...

output = """
gibberish gibberish gibberish gibberish gibberish gibberish 
gibberish?
gibberish!
thought: This is a useful thought the model output before it...
answer: creates an answer to the question.
"""

# We can parse thusly:
parsed_result, parse_errors = parser.parse(output)
print("=" * 100)
print("Parsing test 1")
print("Parsed Result:", parsed_result)
print("Parse Errors:", parse_errors)
print("=" * 100)

"""
If we have *more* rules we want to apply to these "labels", we can use
Label objects to specify them.
"""

from arkaine.utils.parser import Label

thought_label = Label(name="thought", required=True, data_type="str")
answer_label = Label(name="answer", required=True, data_type="str")

parser = Parser([thought_label, answer_label])

# This expands what we can do, such as:
some_label = Label(
    name="some_label",
    required=True,
    data_type="str",
    required_with=["thought", "answer"],
    is_json=True,
)

"""
Here, we demonstrate a few more features.

- data_type: This is a string that indicates the type of data that the label
  should be. It can be "str", "int", "float", "bool". arkaine will *attempt* to
  convert the data to the specified type, but the input must be convertible to
  the specified type and one of the basic types listed.
- required: This is a boolean that indicates if the label is required. If a
  label is not required, it will create an error in the errors returned if it
  is not present.
- required_with: This is a list of labels that must be present for this label to
  be required. If label "A" has required_with=["B", "C"], then whenever "A"
  appears in the input, both "B" and "C" must also appear or an error will be
  raised
- is_json: This is a boolean that indicates if the label should be parsed as
  JSON - it thus returns a DICT instead of just a raw string
"""

# But wait, what if we want to parse *multiple* entities of data from the same
# output? For instance, what if we had:
output = """
THOUGHT: This is a thought
RATING: 3

THOUGHT: This is another thought
TITLE: My little pony's wonderful adventures
RATING: 5
"""

# Since we have multiple entities, we can set up our parser to be different:
parser = Parser(
    [
        Label(
            name="thought", required=True, data_type="str", is_block_start=True
        ),
        Label(name="title", required=False, data_type="str"),
        Label(name="rating", required=True, data_type="int"),
    ]
)

# The key difference in the labels is the is_block_start=True flag. This tells
# the parser that whenever a "thought" label is found, it should be treated as
# the start of a new block of data. It's important that it's a label the LLM
# knows to always output first.

# We can now parse our output:
parsed_result, parse_errors = parser.parse_blocks(output)
print("=" * 100)
print("Parsing test 2")
print("Parsed Result:", parsed_result)
print("Parse Errors:", parse_errors)
print("=" * 100)


###############################################
# 4. Creating an Iterative Agent with SimpleIterativeAgent
###############################################
"""
IterativeAgents are useful for tasks that require multiple iterations to reach a
final answer. They are agents that call themselves repeatedly until either a
terminal number of steps are reached, or until extract_result returns a non-None
value. That's it!

This is preferred when you have a task where you want to ask an LLM something,
then react to its output, and possibly ask it to expand or improve on its
answer.

SimpleIterativeAgent enables you to supply functions that prepare the prompt for
each iteration and determine when to terminate the iterative process.

In this example, our iterative agent simulates processing a piece of text over
three iterations. The accumulated result is then returned.
"""

from arkaine.tools.agent import IterativeAgent


def iterative_prepare_prompt(context, add: int) -> str:
    """
    Have the LLM add numbers together. What a great use of compute power.
    """
    # To learn more about contexts, read the docs- but for now, just know
    # that it's a thread safe variable that allows you to share state during
    # the execution of an agent or tool.
    return f"Add {add} to {context['total']} and return *only* the result."


def iterative_extract_result(context, output: str) -> int:
    """
    Extract the final result from the iterative process.
    Return the accumulated result when the LLM indicates completion with 'DONE'.
    Otherwise, return None to signal that another iteration is required.
    """
    # We can also access the args from the context
    context["total"] += context.args["add"]
    if "11" in output:
        return 11
    else:
        return None


# Create a SimpleIterativeAgent instance.
iterative_agent = SimpleIterativeAgent(
    name="iterative_echo_agent",
    description="Continually add a number to a base value",
    args=[
        Argument(
            "add", "The value to add to the running total", "int", required=True
        ),
    ],
    llm=llm,
    prepare_prompt=iterative_prepare_prompt,
    extract_result=iterative_extract_result,
    initial_state={
        "total": 1,
    },
    max_steps=5,
)

"""
initial_state is a dict of variables that are set on the context when the agent
is initially called for each execution. This allows you to set up initial state
for the agent.
"""

# Let's try it out!
print("=" * 100)
print("Iterative Agent (iterative_agent) demonstration:")
response = iterative_agent(add=5)
print("Response:", response)
print("=" * 100)

"""
Just like before, you can also just inherit the IterativeAgent class and create
a more complicated agent.
"""


class AnotherIterativeAgent(IterativeAgent):
    def __init__(self, llm=llm):
        super().__init__(
            llm=llm,
            name="another_iterative_agent",
            description="Continually add a number to a base value",
            args=[
                Argument(
                    "add",
                    "The value to add to the running total",
                    "int",
                    required=True,
                ),
            ],
            initial_state={
                "total": 1,
            },
            max_steps=5,
        )

    def prepare_prompt(self, context, add: int) -> str:
        return f"Add {add} to {context['total']} and return *only* the result."

    def extract_result(self, context, output: str) -> int:
        context["total"] += context.args["add"]
        if "11" in output:
            return 11
        else:
            return None


another_iterative_agent = AnotherIterativeAgent()

print("=" * 100)
print("Another Iterative Agent (another_iterative_agent) demonstration:")
response = another_iterative_agent(5)
print("Response:", response)
print("=" * 100)
