import os

from langchain_core.language_models import BaseChatModel


def get_llm(provider: str = "anthropic", model: str | None = None) -> BaseChatModel:
    """Create an LLM instance for the given provider and model."""
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        model = model or "claude-sonnet-4-20250514"
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")
        return ChatAnthropic(model=model, api_key=api_key)  # type: ignore[arg-type]

    elif provider == "openai":
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            raise ImportError(
                "langchain-openai is required for OpenAI provider. "
                "Install it with: uv add langchain-openai"
            )

        model = model or "gpt-4o"
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        return ChatOpenAI(model=model, api_key=api_key)  # type: ignore[arg-type]

    elif provider == "google":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError:
            raise ImportError(
                "langchain-google-genai is required for Google provider. "
                "Install it with: uv add langchain-google-genai"
            )

        model = model or "gemini-2.5-flash"
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is required")
        return ChatGoogleGenerativeAI(model=model, google_api_key=api_key)  # type: ignore[arg-type]

    else:
        raise ValueError(f"Unknown provider: {provider}. Supported: anthropic, openai, google")
