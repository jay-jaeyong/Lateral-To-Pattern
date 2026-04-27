from services.gemini_client import GeminiClient
from services.openai_client import OpenAIClient


def get_client(provider: str):
    """provider 이름에 맞는 API 클라이언트를 반환합니다.

    Args:
        provider: "gemini" 또는 "openai" / "gpt"
    """
    p = (provider or "").strip().lower()
    if p in ("openai", "gpt", "chatgpt"):
        return OpenAIClient()
    if p in ("gemini", "google", ""):
        return GeminiClient()
    raise ValueError(f"알 수 없는 provider: {provider!r} (사용 가능: gemini, gpt)")


__all__ = ["GeminiClient", "OpenAIClient", "get_client"]
