from ollama import Client

from arkaine.llms.llm import LLM
from arkaine.tools.agent import Prompt


class Ollama(LLM):

    CONTEXT_LENGTHS = {
        "llama3.1": 8192,
    }

    def __init__(
        self,
        model: str = "llama3.1",
        context_length: int = 1024,
        host: str = "http://localhost:11434",
        default_temperature: float = 0.7,
        request_timeout: float = 120.0,
        verbose: bool = False,
    ):
        self.model = model
        self.default_temperature = default_temperature
        self.verbose = verbose
        self.host = host
        self.__client = Client(host=self.host)
        self.__context_length = context_length

        super().__init__(name=f"ollama:{model}")

    @property
    def context_length(self) -> int:
        return self.__context_length

    def completion(self, prompt: Prompt) -> str:
        return self.__client.chat(
            model=self.model,
            messages=prompt,
        )[
            "message"
        ]["content"]
