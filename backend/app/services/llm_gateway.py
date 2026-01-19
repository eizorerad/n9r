"""LLM Gateway - Unified interface using LiteLLM.

LiteLLM provides a unified API for 100+ LLM providers with:
- Automatic format translation to OpenAI format
- Built-in retry/fallback logic
- Cost tracking
- Caching support

Note: LiteLLM is imported lazily to avoid fork-safety issues with Celery prefork pool.
"""

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

# Lazy import of litellm to avoid fork-safety issues on macOS
# LiteLLM uses aiohttp which creates threads/event loops at import time
if TYPE_CHECKING:
    pass

from app.core.config import settings

logger = logging.getLogger(__name__)

# Module-level flag to track if litellm is initialized
_litellm_initialized = False


def _ensure_litellm():
    """Lazy initialize LiteLLM on first use."""
    global _litellm_initialized
    if _litellm_initialized:
        return

    import os

    import litellm

    # Use environment variable instead of deprecated set_verbose
    if settings.debug:
        os.environ['LITELLM_LOG'] = 'DEBUG'

    litellm.drop_params = True  # Drop unsupported params instead of error

    # Disable LiteLLM's internal logging callbacks to prevent LoggingWorker timeout errors
    # These callbacks use async workers that can timeout and spam logs with errors
    litellm.success_callback = []
    litellm.failure_callback = []
    litellm._async_success_callback = []
    litellm._async_failure_callback = []

    _litellm_initialized = True
    logger.debug("LiteLLM initialized")


class LLMError(Exception):
    """LLM Gateway error."""
    pass


class LLMGateway:
    """
    Unified LLM Gateway using LiteLLM.

    Supports 100+ LLM providers through a single interface:
    - Google Gemini 3 Pro (gemini-3-pro-preview) - 1M context, Nov 2025
    - Anthropic Claude Sonnet 4.5 via Bedrock - Sep 2025
    - Azure OpenAI Codex 5.1 Mini (gpt-5.1-codex-mini) - 400K context, Nov 2025
    - OpenAI (gpt-4o, gpt-5, o1, o3)
    - OpenRouter
    - And many more...

    Model naming convention:
    - gemini/gemini-3-pro-preview
    - bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0
    - azure/gpt-5.1-codex-mini
    - openai/gpt-4o
    """

    # Default models for different tasks (updated Dec 2025)
    # Using LATEST models: Gemini 3 Pro, Claude Sonnet 4.5, Codex 5.1 Mini
    DEFAULT_MODELS = {
        "chat": "gemini/gemini-3-pro-preview",                    # Gemini 3 Pro (1M context, Nov 2025)
        "analysis": "gemini/gemini-3-pro-preview",                # Gemini 3 Pro for analysis
        "fast": "azure/gpt-5.1-codex-mini",                       # Azure Codex 5.1 Mini (400K context)
        "embedding": "openai/text-embedding-3-small",
        "code": "bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0",  # Claude Sonnet 4.5 via Bedrock
    }

    # Fallback chain for reliability (newest models first)
    FALLBACK_MODELS = [
        "gemini/gemini-3-pro-preview",                            # Gemini 3 Pro (primary)
        "bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0",      # Claude Sonnet 4.5 via AWS Bedrock
        "azure/gpt-5.1-codex-mini",                               # Azure Codex 5.1 Mini
    ]

    # Mapping of model prefixes to environment variable names
    _MODEL_KEY_MAPPING = {
        "openai/": "OPENAI_API_KEY",
        "anthropic/": "ANTHROPIC_API_KEY",
        "gemini/": "GEMINI_API_KEY",
        "azure/": "AZURE_API_KEY",
        "openrouter/": "OPENROUTER_API_KEY",
        "bedrock/": "AWS_ACCESS_KEY_ID",
        "vertex_ai/": "VERTEX_PROJECT",
    }

    def __init__(self):
        """Initialize LLM Gateway with configured API keys."""
        self._setup_api_keys()
        self._setup_cache()

    def _setup_api_keys(self):
        """Set up API keys from settings for all supported providers."""
        # OpenAI
        if settings.openai_api_key:
            os.environ["OPENAI_API_KEY"] = settings.openai_api_key

        # Anthropic
        if settings.anthropic_api_key:
            os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key

        # Google Gemini (AI Studio)
        if settings.gemini_api_key:
            os.environ["GEMINI_API_KEY"] = settings.gemini_api_key

        # Google Vertex AI
        if settings.vertex_project:
            os.environ["VERTEX_PROJECT"] = settings.vertex_project
            os.environ["VERTEX_LOCATION"] = settings.vertex_location

        # Azure OpenAI
        if settings.azure_api_key:
            os.environ["AZURE_API_KEY"] = settings.azure_api_key
            os.environ["AZURE_API_BASE"] = settings.azure_api_base
            os.environ["AZURE_API_VERSION"] = settings.azure_api_version

        # AWS Bedrock
        if settings.aws_access_key_id:
            os.environ["AWS_ACCESS_KEY_ID"] = settings.aws_access_key_id
            os.environ["AWS_SECRET_ACCESS_KEY"] = settings.aws_secret_access_key
            os.environ["AWS_REGION_NAME"] = settings.aws_region_name

        # OpenRouter
        if settings.openrouter_api_key:
            os.environ["OPENROUTER_API_KEY"] = settings.openrouter_api_key

        # Store provider-specific settings for embedding model selection
        self._azure_embedding_deployment = settings.azure_embedding_deployment
        self._azure_chat_deployment = settings.azure_chat_deployment
        self._bedrock_embedding_model = settings.bedrock_embedding_model
        self._vertex_embedding_model = settings.vertex_embedding_model
        self._embedding_model_override = settings.embedding_model

    def _get_available_fallbacks(self, exclude_model: str) -> list[str]:
        """Get fallback models that have API keys configured.

        Only includes models whose API keys are set in environment variables.
        This prevents wasted API calls and clearer error messages.

        Args:
            exclude_model: The primary model to exclude from fallbacks

        Returns:
            List of fallback model names with valid API keys
        """
        available = []
        for model in self.FALLBACK_MODELS:
            if model == exclude_model:
                continue
            # Check if this model's API key is configured
            for prefix, env_key in self._MODEL_KEY_MAPPING.items():
                if model.startswith(prefix):
                    if os.environ.get(env_key):
                        available.append(model)
                    break

        if not available:
            logger.warning(
                f"No fallback models available for {exclude_model}. "
                "Consider setting API keys for: OPENAI_API_KEY, ANTHROPIC_API_KEY, or GEMINI_API_KEY"
            )

        return available

    def _setup_cache(self):
        """Set up Redis cache for LiteLLM responses."""
        if getattr(settings, "redis_url", None):
            try:
                _ensure_litellm()
                import litellm
                litellm.cache = litellm.Cache(
                    type="redis",
                    host=settings.redis_host,
                    port=settings.redis_port,
                )
                logger.info("LiteLLM Redis cache enabled")
            except Exception as e:
                logger.warning(f"Failed to enable Redis cache: {e}")

    async def complete(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        system_prompt: str | None = None,
        response_format: dict | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Generate a completion with automatic fallback.

        Args:
            prompt: User prompt
            model: Model name with provider prefix (e.g., "openai/gpt-4o")
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            system_prompt: Optional system prompt
            response_format: Optional response format (e.g., {"type": "json_object"})
            **kwargs: Additional parameters passed to LiteLLM

        Returns:
            dict with:
                - content: Response text
                - model: Model used
                - usage: Token usage stats
                - cost: Estimated cost in USD
        """
        model = model or self.DEFAULT_MODELS["chat"]

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        return await self.chat(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            **kwargs,
        )

    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        response_format: dict | None = None,
        fallback: bool = True,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Send chat messages with automatic fallback.

        Args:
            messages: List of message dicts with role and content
            model: Model name with provider prefix
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            response_format: Optional response format (e.g., {"type": "json_object"})
            fallback: Enable automatic fallback to other models
            **kwargs: Additional parameters passed to LiteLLM

        Returns:
            Dict with content, model, usage stats, and cost
        """
        # Lazy import litellm
        _ensure_litellm()
        from litellm import acompletion, completion_cost

        model = model or self.DEFAULT_MODELS["chat"]

        params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }

        if response_format:
            params["response_format"] = response_format

        # Add fallback models if enabled (only those with configured API keys)
        if fallback:
            available_fallbacks = self._get_available_fallbacks(model)
            if available_fallbacks:
                params["fallbacks"] = available_fallbacks

        try:
            response = await acompletion(**params)

            return {
                "content": response.choices[0].message.content,
                "model": response.model,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
                "cost": completion_cost(response),
            }
        except Exception as e:
            logger.error(f"LLM completion failed: {e}")
            raise LLMError(f"All models failed: {str(e)}")

    async def complete_stream(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        system_prompt: str | None = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        """
        Generate a streaming completion.

        Yields:
            Text chunks as they are generated
        """
        model = model or self.DEFAULT_MODELS["chat"]

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        async for chunk in self.chat_stream(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        ):
            yield chunk

    async def chat_stream(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs,
    ) -> AsyncIterator[str]:
        """
        Send chat messages with streaming response.

        Yields:
            Text chunks as they are generated
        """
        # Lazy import litellm
        _ensure_litellm()
        from litellm import acompletion

        model = model or self.DEFAULT_MODELS["chat"]

        try:
            response = await acompletion(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                **kwargs,
            )

            async for chunk in response:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            logger.error(f"LLM streaming failed: {e}")
            raise LLMError(f"Streaming failed: {str(e)}")

    async def chat_stream_with_usage(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs,
    ) -> tuple[AsyncIterator[str], "asyncio.Future[dict[str, Any]]"]:
        """
        Stream chat response while also collecting final usage/cost.

        Returns:
            (token_iterator, final_stats_future)

        final_stats_future resolves to:
            {
              "model": str,
              "usage": {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int} | None,
              "cost": float | None,
            }
        """
        import asyncio

        _ensure_litellm()
        from litellm import acompletion, completion_cost

        model = model or self.DEFAULT_MODELS["chat"]

        loop = asyncio.get_running_loop()
        final_future: asyncio.Future[dict[str, Any]] = loop.create_future()

        async def _iterator() -> AsyncIterator[str]:
            try:
                response = await acompletion(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                    stream_options={"include_usage": True},
                    **kwargs,
                )

                final_model: str | None = None
                final_usage: dict[str, int] | None = None
                final_cost: float | None = None

                async for chunk in response:
                    # Some providers include usage only on the final chunk
                    if getattr(chunk, "model", None):
                        final_model = chunk.model

                    usage_obj = getattr(chunk, "usage", None)
                    if usage_obj is not None:
                        # LiteLLM usage object mirrors OpenAI usage fields
                        final_usage = {
                            "prompt_tokens": getattr(usage_obj, "prompt_tokens", 0) or 0,
                            "completion_tokens": getattr(usage_obj, "completion_tokens", 0) or 0,
                            "total_tokens": getattr(usage_obj, "total_tokens", 0) or 0,
                        }
                        try:
                            final_cost = completion_cost(chunk)
                        except Exception:
                            final_cost = None

                    if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content

                if not final_future.done():
                    final_future.set_result(
                        {
                            "model": final_model or model,
                            "usage": final_usage,
                            "cost": final_cost,
                        }
                    )
            except Exception as e:
                if not final_future.done():
                    final_future.set_exception(e)
                logger.error(f"LLM streaming failed: {e}")
                raise LLMError(f"Streaming failed: {str(e)}")

        return _iterator(), final_future

    def _get_embedding_model(self) -> str:
        """Determine the best embedding model based on configured providers.

        Priority:
        1. Explicit EMBEDDING_MODEL override
        2. Azure (if configured with embedding deployment)
        3. Bedrock (if configured with embedding model)
        4. Vertex AI (if configured with embedding model)
        5. OpenAI (default)
        """
        # Check for explicit override
        if self._embedding_model_override:
            return self._embedding_model_override

        # Azure OpenAI
        if settings.azure_api_key and self._azure_embedding_deployment:
            return f"azure/{self._azure_embedding_deployment}"

        # AWS Bedrock
        if settings.aws_access_key_id and self._bedrock_embedding_model:
            return self._bedrock_embedding_model

        # Google Vertex AI
        if settings.vertex_project and self._vertex_embedding_model:
            return self._vertex_embedding_model

        # Google Gemini (AI Studio)
        # LiteLLM expects provider-prefixed model names for non-OpenAI providers.
        if settings.gemini_api_key:
            return "gemini/text-embedding-004"

        # Default to OpenAI
        return self.DEFAULT_MODELS["embedding"]

    async def embed(
        self,
        texts: list[str] | str,
        model: str | None = None,
    ) -> list[list[float]]:
        """
        Generate embeddings for texts.

        Args:
            texts: Single text or list of texts
            model: Embedding model. If None, auto-detected based on configured provider.
                   Examples:
                   - openai/text-embedding-3-small
                   - azure/your-deployment-name
                   - bedrock/amazon.titan-embed-text-v2:0
                   - vertex_ai/text-embedding-004
                   - gemini/text-embedding-004

        Returns:
            List of embedding vectors
        """
        # Lazy import litellm
        _ensure_litellm()
        from litellm import aembedding

        # Determine model to use
        if model is None:
            model = self._get_embedding_model()

        if isinstance(texts, str):
            texts = [texts]

        try:
            # Build params
            params = {
                "model": model,
                "input": texts,
            }

            # Add provider-specific params
            if model.startswith("azure/"):
                params["api_base"] = settings.azure_api_base
                params["api_version"] = settings.azure_api_version
            elif model.startswith("vertex_ai/"):
                params["vertex_project"] = settings.vertex_project
                params["vertex_location"] = settings.vertex_location

            response = await aembedding(**params)
            return [item["embedding"] for item in response.data]
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise LLMError(f"Embedding failed: {str(e)}")

    async def analyze_code(
        self,
        code: str,
        language: str,
        analysis_type: str = "general",
        model: str | None = None,
    ) -> dict[str, Any]:
        """
        Analyze code with specialized prompts.

        Args:
            code: Source code to analyze
            language: Programming language
            analysis_type: Type of analysis (vibe_code, security, dead_code, architecture)
            model: Optional model override

        Returns:
            Analysis results with content, model, usage, and cost
        """
        system_prompts = {
            "vibe_code": """You are an expert code reviewer detecting "vibe-code" patterns.

Vibe-code indicators:
1. Excessive comments explaining obvious code
2. AI-generated boilerplate without customization
3. Copy-pasted code with minor variations
4. Over-engineered solutions for simple problems
5. Inconsistent naming conventions
6. Redundant null checks or type assertions
7. TODO/FIXME comments without tickets
8. Magic numbers and strings

Return findings as JSON:
{
    "findings": [...],
    "vibe_score": 0-100,
    "confidence": 0-100
}""",
            "security": """You are a security expert. Analyze the code for vulnerabilities including:
SQL injection, XSS, CSRF, insecure dependencies, hardcoded secrets.
Return findings in JSON format.""",
            "dead_code": """You are an expert code analyzer. Identify dead code, unused imports,
unreachable code blocks, and functions that are never called.
Return findings in JSON format.""",
            "architecture": """Analyze code architecture for: SOLID violations, tight coupling,
missing abstractions, circular dependencies, god classes.
Return JSON with suggestions.""",
            "general": """You are a senior code reviewer. Analyze the code for:
- Code quality issues
- Potential bugs
- Performance problems
- Best practice violations
Return a comprehensive analysis in JSON format.""",
        }

        system_prompt = system_prompts.get(analysis_type, system_prompts["general"])

        return await self.complete(
            prompt=f"Language: {language}\n\n```{language}\n{code}\n```",
            model=model or self.DEFAULT_MODELS["analysis"],
            system_prompt=system_prompt,
            temperature=0.1,
            response_format={"type": "json_object"},
        )

    def get_model_for_task(self, task: str) -> str:
        """Get recommended model for a specific task."""
        return self.DEFAULT_MODELS.get(task, self.DEFAULT_MODELS["chat"])


# Singleton instance
_llm_gateway: LLMGateway | None = None


def get_llm_gateway() -> LLMGateway:
    """Get or create LLM Gateway singleton."""
    global _llm_gateway
    if _llm_gateway is None:
        _llm_gateway = LLMGateway()
    return _llm_gateway
