import os
from importlib import import_module
from typing import Optional, Union

from typing_extensions import Literal

from arkaine.tools.tool import Argument, Context, Example, Tool


class SMSSender(Tool):
    """
    A tool for sending SMS messages through various providers including Twilio,
    AWS SNS, MessageBird, Vonage (formerly Nexmo), and others.
    """

    def __init__(
        self,
        service: Literal["twilio", "aws_sns", "messagebird", "vonage"],
        credentials: Optional[dict] = None,
        env_prefix: Optional[str] = "",
        aws_region: Optional[str] = None,
        to: Optional[str] = None,
    ):
        """
        Initialize the SMSSender tool.

        Args:
            service: SMS service provider to use
            credentials: Dict containing service-specific credentials. Can use:
                       - Direct values
                       - None (will check environment variables)
            env_prefix: Prefix for environment variables
            aws_region: AWS region for SNS (required if service is 'aws_sns')
            to: Recipient phone number - if set, then the "to" argument is
                never presented to the agent
        """
        self.service = service
        self.env_prefix = env_prefix
        self.aws_region = aws_region
        self.to = to
        self._credentials = credentials or {}
        self._client = None

        args = [
            Argument(
                name="message",
                description="The message text to send",
                type="str",
                required=True,
            ),
        ]

        examples = [
            Example(
                name="Send SMS",
                args={
                    "message": "Hello from the SMS tool!",
                },
                output="SMS sent successfully",
                description="Send a simple SMS message",
            ),
        ]

        if not self.to:
            args.append(
                Argument(
                    name="to",
                    description="Recipient phone number in E.164 format "
                    "(e.g., +1234567890)",
                    type="str",
                    required=True,
                ),
            )
            for example in examples:
                example.args["to"] = ("+1234567890",)

        super().__init__(
            name="SMSSender",
            description="Sends SMS messages",
            args=args,
            func=self.send,
            examples=examples,
        )

    def _load_credential(
        self,
        key: str,
        env_var: str,
        required: bool = True,
    ) -> Optional[str]:
        """Load a credential from various sources."""
        value = self._credentials.get(key)
        if self.env_prefix:
            env_var = f"{self.env_prefix}_{env_var}"

        if value is None:
            value = os.getenv(env_var)

        if required and not value:
            raise ValueError(
                f"Required credential not provided: {key} " f"(env: {env_var})"
            )
        return value

    @property
    def client(self):
        """Lazy load the appropriate SMS service client."""
        if self._client is None:
            if self.service == "twilio":
                self._init_twilio()
            elif self.service == "aws_sns":
                self._init_aws_sns()
            elif self.service == "messagebird":
                self._init_messagebird()
            elif self.service == "vonage":
                self._init_vonage()
            else:
                raise ValueError(f"Unsupported SMS service: {self.service}")
        return self._client

    def _init_twilio(self):
        """Initialize Twilio client."""
        try:
            twilio = import_module("twilio.rest")
        except ImportError:
            raise ImportError(
                "Twilio package not installed. Run: pip install twilio"
            )

        account_sid = self._load_credential("account_sid", "TWILIO_ACCOUNT_SID")
        auth_token = self._load_credential("auth_token", "TWILIO_AUTH_TOKEN")
        self.from_number = self._load_credential(
            "from_number", "TWILIO_FROM_NUMBER"
        )
        self._client = twilio.Client(account_sid, auth_token)

    def _init_aws_sns(self):
        """Initialize AWS SNS client."""
        try:
            boto3 = import_module("boto3")
        except ImportError:
            raise ImportError(
                "Boto3 package not installed. Run: pip install boto3"
            )

        if not self.aws_region:
            raise ValueError("aws_region is required for AWS SNS")

        access_key = self._load_credential("access_key_id", "AWS_ACCESS_KEY_ID")
        secret_key = self._load_credential(
            "secret_access_key", "AWS_SECRET_ACCESS_KEY"
        )
        self.sender_id = self._load_credential("sender_id", "AWS_SENDER_ID")

        self._client = boto3.client(
            "sns",
            region_name=self.aws_region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

    def _init_messagebird(self):
        """Initialize MessageBird client."""
        try:
            messagebird = import_module("messagebird")
        except ImportError:
            raise ImportError(
                "MessageBird package not installed. "
                "Run: pip install messagebird"
            )

        api_key = self._load_credential("api_key", "MESSAGEBIRD_API_KEY")
        self.from_number = self._load_credential(
            "from_number", "MESSAGEBIRD_FROM_NUMBER"
        )
        self._client = messagebird.Client(api_key)

    def _init_vonage(self):
        """Initialize Vonage client."""
        try:
            vonage = import_module("vonage")
        except ImportError:
            raise ImportError(
                "Vonage package not installed. Run: pip install vonage"
            )

        api_key = self._load_credential("api_key", "VONAGE_API_KEY")
        api_secret = self._load_credential("api_secret", "VONAGE_API_SECRET")
        self.from_number = self._load_credential(
            "from_number", "VONAGE_FROM_NUMBER"
        )
        self._client = vonage.Client(api_key, api_secret)

    def send(self, context: Context, **kwargs) -> str:
        """
        Send an SMS message using the configured service.

        Returns:
            str: Success message if SMS is sent successfully

        Raises:
            ValueError: If required settings are missing
            Exception: If there's an error sending the SMS
        """
        to_number = kwargs["to"]
        message = kwargs["message"]

        try:
            if self.service == "twilio":
                self.client.messages.create(
                    body=message,
                    from_=self.from_number,
                    to=to_number,
                )

            elif self.service == "aws_sns":
                self.client.publish(
                    PhoneNumber=to_number,
                    Message=message,
                    MessageAttributes={
                        "AWS.SNS.SMS.SendererId": {
                            "DataType": "String",
                            "StringValue": self.sender_id,
                        }
                    },
                )

            elif self.service == "messagebird":
                self.client.message_create(
                    self.from_number,
                    to_number,
                    message,
                )

            elif self.service == "vonage":
                self.client.sms.send_message(
                    {
                        "from": self.from_number,
                        "to": to_number,
                        "text": message,
                    }
                )

            return "SMS sent successfully"

        except Exception as e:
            raise Exception(f"Failed to send SMS: {str(e)}")
