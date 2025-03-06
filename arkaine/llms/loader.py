import os
from typing import Optional
from arkaine.llms.openai import OpenAI
from arkaine.llms.ollama import Ollama
from arkaine.llms.claude import Claude
from arkaine.llms.google import Google
from arkaine.llms.groq import Groq
from arkaine.llms.deepseek import DeepSeek


def load_llm(provider: Optional[str] = None, model: Optional[str] = None):
    """
    load_llm will load an LLM based on the provider and model. If none is
    provided for the provider, it will try to infer from its running environment
    - if ollama is running, it will use that. Otherwise, it will check for
    environment variables for the other providers, choosing the first one it
    finds. If model is not provided, it will use the default model for the
    provider.
    """

    api_env_keys = {
        "openai": "OPENAI_API_KEY",
        "ollama": "OLLAMA_API_KEY",
        "claude": "ANTHROPIC_API_KEY",
        "google": "GOOGLE_API_KEY",
        "groq": "GROQ_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
    }
    if provider is None:
        provider = os.environ.get("LLM_PROVIDER", None)

    if provider is None:
        # First, see if we have an ollama instance running
        try:
            import ollama as ollama_module

            client = ollama_module.Client()
            models = client.list()
            print(models)
            provider = "ollama"
        except ImportError:
            pass

        if provider is None:
            # Now let's run through available env keys
            # and see if any are set
            for provider, env_key in api_env_keys.items():
                if os.environ.get(env_key, None) is not None:
                    provider = provider
                    break
        if provider is None:
            # At this point we don't know what to do,
            # so we'll raise an error
            raise ValueError("No provider specified or api keys found")

    if provider == "openai":
        llm = OpenAI
    elif provider == "ollama":
        llm = Ollama
    elif provider == "claude":
        llm = Claude
    elif provider == "google":
        llm = Google
    elif provider == "groq":
        llm = Groq
    elif provider == "deepseek":
        llm = DeepSeek
    else:
        raise ValueError(f"Invalid provider: {provider}")

    if model:
        return llm(model=model)
    else:
        return llm()
