"""Business logic services.

Note: LLMGateway is NOT imported at module level to avoid fork-safety issues
with LiteLLM/aiohttp when used with Celery prefork pool on macOS.
Import directly: from app.services.llm_gateway import LLMGateway, get_llm_gateway
"""

# Lazy imports to avoid fork-safety issues
# from app.services.llm_gateway import LLMGateway, get_llm_gateway

__all__ = [
    "LLMGateway",
    "get_llm_gateway",
]


def __getattr__(name: str):
    """Lazy import for fork-safety."""
    if name in ("LLMGateway", "get_llm_gateway"):
        from app.services.llm_gateway import LLMGateway, get_llm_gateway
        return LLMGateway if name == "LLMGateway" else get_llm_gateway
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
