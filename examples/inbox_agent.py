"""
This is an example of combining multiple tools with a *connector*. A connector
is a way to integrate your agents and tools into systems that you use every day
- e-mail, SMS, RSS feeds - or takes care of turning your agents into stand alone
applications - like the API or schedule connectors.

This example utilizes the *inbox* connector to check for e-mails that fulfill
certain criteria. When such an e-mail is found, a tool will be called, being
passed the e-mail message as an argument. From there, you can do whatever you
want to it.

For this one, we'll be using the LocalSearch tool to try to answer the e-mail's
query with a local search, a ChatInterface to ingest the message and to send an
e-mail message back to us with the results (with a personality of our choice).
"""

# Let's get some info straight - let's write down here your
# credentials and information
username = "your_email@email.com"
password = "your_password"
service = "gmail"  # Could be "outlook", "yahoo", "etc."
zipcode = "08902"  # Your zip code
name = "Jane Doe"


# We'll need an LLM, so let's load one up. We'll use the our LLM loader
# Feel free to specify your specific preference.
from arkaine.llms.loader import load_llm

llm = load_llm()

# Our LocalSearch tool atm only supports Google's Map API - we'll
# add more later, but this means you require a Google Maps API key
from arkaine.toolbox.local_search import LocalSearch

search = LocalSearch(
    formatted_str=True,  # This returns as a string versus a JSON string
    # Some descriptor of where you're from
    default_location=zipcode,
    radius_km=15,
    # Whether to force the default distance, or allow the agent to select
    # it.
    force_distance=True,
    # How many results to return; if it's not specified, the agent can
    # request some amount as it deems appropriate.
    enforced_limit=10,
)

# Try out the local search here if you want.
# print(search("bookstores"))
# exit()

"""
A Chat is a type of agent that handles some form of message -> response,
with tools optionally integrated. arkaine currently supports only a "Simple"
chat, which is a chat that, given a user's message, will return a response.
1 message -> 1 response, 1 user and 1 agent. Hence, Simple.
"""
from arkaine.chat.simple import SimpleChat

chat = SimpleChat(
    llm=llm,
    # We tell our agent that it has access to a local search tool
    tools=[search],
    # What do you want your agent to know its name to be?
    agent_name="Jarvis",
    # SimpleChat attempts to inject some human response to it.
    personality="someone who always responds with dry british wit",
    # The name of, well, you!
    user_name=name,
)

"""
An EmailSender is a tool that allows you to send e-mails through one of your
accounts. Specify the username, password, and service, and the agent will be
able to send an e-mail.

Note that gmail accounts require an app password to be used. See here on
doing that:

https://support.google.com/accounts/answer/185833?hl=en

The service is the name of the service you're using. It might be one we have
set up in EmailSender. If not, you'll have to set the smtp_host and
smtp_port manually.
"""

from arkaine.toolbox.email import EmailSender

sender = EmailSender(
    username=username, password=password, service=service, allow_response=True
)

"""
We have all the pieces we need! Let's build a tool that ties all of these
together!
"""

from arkaine.connectors.inbox import EmailMessage
from arkaine.tools.argument import Argument
from arkaine.tools.tool import Tool


class OurTool(Tool):

    def __init__(self):
        super().__init__(
            name="our_tool",
            description="Our super duper cool example tool",
            args=[
                Argument(
                    name="email",
                    description="The email we received",
                    type="EmailMessage",
                    required=True,
                )
            ],
            func=self.handle_email,
        )

    # This is where we handle the actual e-mail when it comes in.
    def handle_email(self, context, email: EmailMessage):
        print("Email received")
        print(f"ID: {email.message_id}")
        print(f"Subject: {email.subject}")
        print(f"From: {email.sender}")
        print(f"Body:\n{email.body}\n\n")

        # We'll use our chat to handle the e-mail and handle parsing our
        # request, forming a call to our local search tool, then parsing the
        # response in the manner we requested. Since chats are just
        # tools/agents, we can use them just like a function. We pass the
        # context in so that it is counted as a child tool call, allowing
        # the context to track our state through the call.
        response = chat(context, email.body)

        print(f"Response:\n{response}\n\n")

        # We'll send the response back to the sender of the e-mail.
        return sender(
            context,
            subject=email.subject,
            body=response,
            to=email.sender,
            # This allows us to respond to the same e-mail instead of it
            # being treated as a new one.
            message_id=email.message_id,
        )


"""
OK, we're ready to go! Let's create our inbox just like the e-mail sender.
BUT remember - you might need to specify the IMAP host and port if you're
not using one of the support services. If it gives you trouble, check the
other parameters or ask about it on the arkaine Discord.
"""
from arkaine.connectors.inbox import Inbox
from datetime import datetime, timedelta

inbox = Inbox(
    username=username,
    password=password,
    service=service,
    # This is how often we're going to check the inbox for new e-mails.
    check_every="1:minutes",
    # This is a defense mechanism to prevent the inbox connector from
    # going ham and processing every single e-mail you ever received;
    # great for a "first boot" kind of thing.
    ignore_emails_older_than=datetime.now() - timedelta(minutes=30),
)
"""
By default the inbox connector uses a file called EMAIL_SEEN_MESSAGES.json
to store what messages it has seen. You can specify a SeenMessageStore
instead, but for now just know that this is how we ensure that we don't
react to the same e-mail over and over and over and over and over again.
That'd be bad.
"""

"""
Inbox checks the inbox at the interval specified. Every time it checks, it
scans the inbox for a set of e-mails that match filters. You can specify
those on the instantiation
or add them later like we are here:
"""
from arkaine.connectors.inbox import EmailFilter

inbox.add_filter(
    EmailFilter(
        sender_pattern=username,
    ),
    tools=[OurTool()],
)

"""
This basically tells the inbox connector that, every time a new e-mail comes
through, check the sender. If it matches our pattern (in this case,
literally our username), then call all the tools we specified.

EmailFilters can be added together or combined in various ways to make a
pretty complex set of filters. This allows you to specify very clearly what
you want some agents to pay attention to, and others to ignore.
"""

# We start the inbox connector
inbox.start()

# keep_alive will keep the inbox bot running indefinitely until a kill
# signal is received.
from arkaine.quickstart import keep_alive

keep_alive(inbox.stop)
