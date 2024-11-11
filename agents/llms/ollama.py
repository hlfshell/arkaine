from ollama import Client

from agents.agent import Prompt
from agents.llms.llm import LLM


class OllamaModel(LLM):
    def __init__(
        self,
        model: str,
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

    def completion(self, prompt: Prompt) -> str:
        return self.__client.chat(
            model=self.model,
            messages=prompt,
        )[
            "message"
        ]["content"]
