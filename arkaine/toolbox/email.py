import os
import re
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional, Union

from arkaine.tools.tool import Argument, Context, Example, Tool


class EmailSender(Tool):
    """
    A tool for sending emails through various email services using SMTP.
    Supports plain text and HTML emails, multiple recipients, and common
    email providers including cloud services.

    Initializing the email_sender tool:

    Args:
        username: Email username/address. Can be:
                    - Direct string value
                    - Dict with 'env' key for environment variable name
                    - None (will check EMAIL_USERNAME env var)
        password: Email password/token. Can be:
                    - Direct string value
                    - Dict with 'env' key for environment variable name
                    - None (will check EMAIL_PASSWORD env var)
        service: Service name (gmail, aws_ses, google_cloud, etc.)
        smtp_host: Custom SMTP host (overrides service setting)
        smtp_port: Custom SMTP port (overrides service setting)
        aws_region: AWS region for SES (required if service is 'aws_ses')
        use_tls: Whether to use TLS encryption (recommended)
        allow_response: Whether to allow the tool to specify a message
            id as an argument as a response to the email.
        to: Recipient email address(es), defaulting to None. If set, then
            the "to" argument is never presented to the agent.
        env_prefix: Prefix for environment variables (default: "EMAIL")

    Environment variables:
        {env_prefix}_USERNAME: Email username/address
        {env_prefix}_PASSWORD: Email password/token
        {env_prefix}_SMTP_HOST: Custom SMTP host (overrides service setting)
        {env_prefix}_SMTP_PORT: Custom SMTP port (overrides service setting)
    """

    # Common SMTP servers and their ports
    COMMON_SMTP_SERVERS = {
        "gmail": ("smtp.gmail.com", 587),
        "outlook": ("smtp-mail.outlook.com", 587),
        "yahoo": ("smtp.mail.yahoo.com", 587),
        "aws_ses": ("email-smtp.{region}.amazonaws.com", 587),
        "google_cloud": ("smtp-relay.gmail.com", 587),
        "godaddy": ("smtp.godaddy.com", 587),
        "zoho": ("smtp.zoho.com", 587),
        "aol": ("smtp.aol.com", 587),
        "icloud": ("smtp.mail.me.com", 587),
        "fastmail": ("smtp.fastmail.com", 587),
        "yandex": ("smtp.yandex.com", 587),
        "protonmail": ("smtp.protonmail.com", 587),
        "mailgun": ("smtp.mailgun.org", 587),
        "sendgrid": ("smtp.sendgrid.net", 587),
        "mailchimp": ("smtp.mailchimp.com", 587),
        "postmark": ("smtp.postmarkapp.com", 587),
        "sparkpost": ("smtp.sparkpost.com", 587),
        "sendlane": ("smtp.sendlane.com", 587),
        "mailjet": ("in-v3.mailjet.com", 587),
        "mailtrap": ("smtp.mailtrap.io", 587),
    }

    def __init__(
        self,
        username: Optional[Union[str, dict]] = None,
        password: Optional[Union[str, dict]] = None,
        service: Optional[str] = None,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        aws_region: Optional[str] = None,
        use_tls: bool = True,
        allow_response: bool = False,
        to: Optional[Union[str, List[str]]] = None,
        env_prefix: str = "EMAIL",
    ):
        self.use_tls = use_tls

        # Handle credential loading
        self.username = self._load_credential(
            username, f"{env_prefix}_USERNAME"
        )
        self.password = self._load_credential(
            password, f"{env_prefix}_PASSWORD"
        )

        self.aws_region = aws_region

        # Handle SMTP settings
        if smtp_host and smtp_port:
            self.smtp_host = smtp_host
            self.smtp_port = smtp_port
        elif service:
            self.smtp_host, self.smtp_port = self._get_service_settings(service)
        else:
            self.smtp_host = self._load_credential(
                None, f"{env_prefix}_SMTP_HOST"
            )
            self.smtp_port = int(
                self._load_credential(
                    None, f"{env_prefix}_SMTP_PORT", required=False
                )
                or 587
            )

        args = [
            Argument(
                name="subject",
                description="Email subject line",
                type="str",
                required=True,
            ),
            Argument(
                name="body",
                description="Email body content (plain text or HTML)",
                type="str",
                required=True,
            ),
        ]

        if allow_response:
            args.append(
                Argument(
                    name="message_id",
                    description=(
                        "Message ID of the email you are responding "
                        "to (if any)",
                    ),
                    type="str",
                    required=False,
                )
            )

        examples = [
            Example(
                name="Send Email",
                args={
                    "subject": "Hello",
                    "body": "This is a test email",
                },
                output="Email sent successfully",
                description="Send a simple email",
            ),
            Example(
                name="Send HTML Email",
                args={
                    "subject": "Hello",
                    "body": "<p>This is a <b>formatted</b> email</p>",
                },
                output="Email sent successfully",
            ),
            Example(
                name="Send Email with Response",
                args={
                    "subject": "Re: Hello!",
                    "body": "In response to your e-mail, I'd like to suggest...",
                    "message_id": "1234567890",
                },
                output="Email sent successfully",
                description="Send an email in response to another email",
            ),
        ]

        description = "Sends plain text or HTML emails"
        self.to = to
        if not self.to:
            description += " to the specified recipient(s)"
            args.append(
                Argument(
                    name="to",
                    description="Recipient email address(es)",
                    type="Union[str, List[str]]",
                    required=True,
                )
            )

            for example in examples:
                example.args["to"] = "recipient@example.com"

        super().__init__(
            name="send_email",
            description=description,
            args=args,
            func=self.send,
            examples=examples,
        )

    def _load_credential(
        self,
        value: Optional[Union[str, dict]],
        env_var: str,
        required: bool = True,
    ) -> Optional[str]:
        """Load a credential from various sources."""
        if isinstance(value, str):
            return value
        if isinstance(value, dict) and "env" in value:
            value = os.getenv(value["env"])
        else:
            value = os.getenv(env_var)

        if required and not value:
            raise ValueError(
                f"Required credential not provided: direct value, "
                f"dict with 'env', or environment variable {env_var}"
            )
        return value

    def _get_service_settings(self, service: str) -> tuple[str, int]:
        """Get SMTP settings for a service."""
        if service not in self.COMMON_SMTP_SERVERS:
            raise ValueError(f"Unknown email service: {service}")

        host, port = self.COMMON_SMTP_SERVERS[service]

        # Handle AWS SES region
        if service == "aws_ses":
            if not self.aws_region:
                raise ValueError("aws_region is required for AWS SES service")
            host = host.format(region=self.aws_region)

        return host, port

    def _is_html(self, body: str) -> bool:
        """Detect if the body contains HTML content."""
        html_patterns = [
            r"<[^>]*>",  # HTML tags
            r"&[a-zA-Z]+;",  # HTML entities
            r"&#\d+;",  # Numeric HTML entities
        ]
        return any(re.search(pattern, body) for pattern in html_patterns)

    def send(self, context: Context, **kwargs) -> str:
        """
        Send an email using the specified settings.

        Returns:
            str: Success message if email is sent successfully

        Raises:
            ValueError: If required settings are missing
            SMTPException: If there's an error sending the email
        """
        # Get recipients
        if self.to:
            to_addrs = self.to
        else:
            to_addrs = kwargs["to"]
        if isinstance(to_addrs, str):
            to_addrs = [to_addrs]

        # Create message
        msg = MIMEMultipart()
        msg["From"] = self.username
        msg["To"] = ", ".join(to_addrs)
        msg["Subject"] = kwargs["subject"]

        if "message_id" in kwargs:
            msg["In-Reply-To"] = kwargs["message_id"]
            msg["References"] = kwargs["message_id"]

        # Attach body with auto-detection of HTML
        body = kwargs["body"]
        is_html = self._is_html(body)
        msg.attach(MIMEText(body, "html" if is_html else "plain"))

        # Send email
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls(context=ssl.create_default_context())
                server.login(self.username, self.password)
                server.send_message(msg)
                return "Email sent successfully"
        except Exception as e:
            raise Exception(f"Failed to send email: {str(e)}")
