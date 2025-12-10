"""Broad Scan Agent for AI-powered code analysis.

Orchestrates multi-model LLM scanning to detect issues across repositories.
Uses multiple models in parallel for consensus-based issue detection.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.services.llm_gateway import LLMError, LLMGateway

logger = logging.getLogger(__name__)


# =============================================================================
# Exceptions
# =============================================================================


class CostLimitExceededError(Exception):
    """Raised when AI scan cost exceeds the configured limit.

    Note: This exception is designed to be Celery-serializable by storing
    all data in the message string and using standard Exception behavior.
    """

    def __init__(self, current_cost: float, limit: float, message: str | None = None):
        self.current_cost = current_cost
        self.limit = limit
        msg = message or f"AI scan cost ${current_cost:.4f} exceeds limit ${limit:.2f}"
        # Store structured data in args for Celery serialization
        super().__init__(msg)

    def __reduce__(self):
        """Make exception picklable for Celery serialization."""
        return (self.__class__, (self.current_cost, self.limit, str(self)))


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class CandidateIssue:
    """Issue candidate from a single model.

    Represents a potential problem identified by an LLM during broad scan,
    pending validation and merging with other model results.

    Attributes:
        id_hint: Suggested ID from the model (e.g., "sec-001")
        dimension: Category of issue (security, db_consistency, api_correctness, code_health, other)
        severity: Issue severity (critical, high, medium, low)
        files: List of affected files with line ranges
        summary: Brief description of the issue
        detailed_description: Full explanation of the issue
        evidence_snippets: Code snippets demonstrating the issue
        potential_impact: Description of what could go wrong
        remediation_idea: Suggested fix approach
        confidence: Model's confidence level (high, medium, low)
        source_model: The model that identified this issue
    """
    id_hint: str
    dimension: str
    severity: str
    files: list[dict[str, Any]]  # [{path, line_start, line_end}]
    summary: str
    detailed_description: str
    evidence_snippets: list[str]
    potential_impact: str
    remediation_idea: str
    confidence: str
    source_model: str


@dataclass
class ModelScanResult:
    """Result from scanning with a single model.

    Attributes:
        model: Model identifier used for the scan
        repo_overview: Model's analysis of the repository structure
        candidates: List of candidate issues found
        tokens_used: Total tokens consumed by this model
        cost_usd: Estimated cost in USD
        success: Whether the scan completed successfully
        error: Error message if scan failed
    """
    model: str
    repo_overview: dict[str, Any] = field(default_factory=dict)
    candidates: list[CandidateIssue] = field(default_factory=list)
    tokens_used: int = 0
    cost_usd: float = 0.0
    success: bool = True
    error: str | None = None


@dataclass
class BroadScanResult:
    """Result from broad scan across all models.

    Aggregates results from multiple model scans into a single result.

    Attributes:
        repo_overview: Combined repository overview (from first successful model)
        candidates: All candidate issues from all models
        models_used: List of models that were called
        models_succeeded: List of models that returned results
        total_tokens: Total tokens used across all models
        total_cost: Total cost in USD across all models
        model_results: Individual results from each model
    """
    repo_overview: dict[str, Any] = field(default_factory=dict)
    candidates: list[CandidateIssue] = field(default_factory=list)
    models_used: list[str] = field(default_factory=list)
    models_succeeded: list[str] = field(default_factory=list)
    total_tokens: int = 0
    total_cost: float = 0.0
    model_results: list[ModelScanResult] = field(default_factory=list)


# =============================================================================
# System Prompt for Broad Scan
# =============================================================================

BROAD_SCAN_SYSTEM_PROMPT = """You are an expert code analyst performing a comprehensive security and quality review of a software repository.

Your task is to analyze the provided repository content and identify issues across multiple dimensions:

## Issue Dimensions

1. **security**: Vulnerabilities, hardcoded secrets, injection risks, authentication/authorization flaws, insecure configurations
2. **db_consistency**: Database schema issues, migration problems, ORM misconfigurations, data integrity risks
3. **api_correctness**: API contract violations, missing validation, incorrect error handling, versioning issues
4. **code_health**: Dead code, code duplication, complexity issues, anti-patterns, maintainability problems
5. **other**: Any other significant issues not fitting the above categories

## Severity Levels

- **critical**: Immediate security risk or data loss potential, must be fixed before deployment
- **high**: Significant issue that should be addressed soon, potential for serious problems
- **medium**: Notable issue that should be planned for fixing, affects quality or maintainability
- **low**: Minor issue or improvement suggestion, nice to have

## Confidence Levels

- **high**: Clear evidence in the code, high certainty this is a real issue
- **medium**: Likely an issue based on patterns observed, but may need verification
- **low**: Possible issue, but context-dependent or uncertain

## Output Format

You MUST respond with valid JSON in the following structure:

```json
{
  "repo_overview": {
    "guessed_project_type": "Description of what this project appears to be",
    "main_languages": ["language1", "language2"],
    "main_components": ["component1", "component2"],
    "frameworks_detected": ["framework1", "framework2"],
    "overall_assessment": "Brief overall assessment of code quality"
  },
  "issues": [
    {
      "id_hint": "sec-001",
      "dimension": "security",
      "severity": "high",
      "files": [
        {"path": "path/to/file.py", "line_start": 10, "line_end": 15}
      ],
      "summary": "Brief one-line summary of the issue",
      "detailed_description": "Detailed explanation of what the issue is and why it matters",
      "evidence_snippets": ["relevant code snippet showing the issue"],
      "potential_impact": "What could go wrong if this is not fixed",
      "remediation_idea": "Suggested approach to fix this issue",
      "confidence": "high"
    }
  ]
}
```

## Guidelines

1. Be thorough but avoid false positives - only report issues you're confident about
2. Focus on actionable issues that developers can fix
3. Provide specific file paths and line numbers when possible
4. Include relevant code snippets as evidence
5. Prioritize security issues and critical bugs
6. Consider the context - what's acceptable in a prototype may not be in production code
7. Don't report issues in test files unless they indicate problems in production code
8. Be language and framework agnostic - analyze any codebase objectively

## Important Context Notes

- **Database indexes**: Indexes may be defined in migration files (e.g., `alembic/versions/`, `migrations/`) rather than in ORM model definitions. Before reporting missing index issues, check migration files for `create_index` statements. If you cannot verify against migrations, set confidence to "medium" and note that verification is needed.
- **ORM vs Database schema**: The ORM model file shows the application's view of the schema, but the actual database schema is defined by migrations. Discrepancies between model annotations and migration-defined indexes are documentation issues, not performance issues.
- **Foreign key indexes**: Many databases automatically create indexes for foreign key columns. Don't assume missing `index=True` on a foreign key means no index exists.

Analyze the repository content provided and return your findings in the JSON format specified above."""


# =============================================================================
# Model Configuration
# =============================================================================

# Model-specific configurations for 1M context window support
MODEL_CONFIGS: dict[str, dict[str, Any]] = {
    # Gemini 3 Pro - Native 1M context, most powerful agentic model
    "gemini/gemini-3-pro-preview": {
        "max_tokens": 65536,
        "extra_headers": {},
    },
    # Claude Sonnet 4.5 on Bedrock - 1M context with beta header
    # Uses cross-region inference profile format for on-demand access
    "bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0": {
        "max_tokens": 16384,
        "extra_headers": {
            "anthropic-beta": "context-1m-2025-08-07"
        },
    },
}

# Default configuration for unknown models
DEFAULT_MODEL_CONFIG: dict[str, Any] = {
    "max_tokens": 4096,
    "extra_headers": {},
}

# Default models to use for broad scan (1M context models only)
DEFAULT_SCAN_MODELS = [
    "gemini/gemini-3-pro-preview",  # Gemini 3 Pro with 1M context
    "bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0",  # Claude Sonnet 4.5 with 1M context
]


# =============================================================================
# BroadScanAgent Class
# =============================================================================


class BroadScanAgent:
    """Multi-model broad scan orchestrator.

    Sends repository content to multiple LLM models in parallel,
    parses their JSON responses, and aggregates the results.

    Attributes:
        llm: LLMGateway instance for making LLM calls
        models: List of model identifiers to use for scanning
        max_cost_usd: Maximum cost limit in USD (None for no limit)
    """

    def __init__(
        self,
        llm_gateway: LLMGateway,
        models: list[str] | None = None,
        max_cost_usd: float | None = None,
    ):
        """Initialize the BroadScanAgent.

        Args:
            llm_gateway: LLMGateway instance for making LLM calls
            models: List of model identifiers to use. Defaults to DEFAULT_SCAN_MODELS.
            max_cost_usd: Maximum cost limit in USD. If None, uses config default.
        """
        self.llm = llm_gateway
        self.models = models or DEFAULT_SCAN_MODELS.copy()

        # Set cost limit from parameter or config
        if max_cost_usd is not None:
            self.max_cost_usd = max_cost_usd
        else:
            from app.core.config import settings
            self.max_cost_usd = settings.ai_scan_max_cost_per_scan

    def _get_model_config(self, model: str) -> dict[str, Any]:
        """Get configuration for a specific model.

        Args:
            model: Model identifier

        Returns:
            Configuration dict with max_tokens and extra_headers
        """
        return MODEL_CONFIGS.get(model, DEFAULT_MODEL_CONFIG.copy())

    def _extract_json_from_response(self, response_content: str) -> str:
        """Extract JSON from response that may be wrapped in markdown code blocks.

        Some models (especially Claude) may wrap JSON in ```json ... ``` blocks
        or include markdown headers before the JSON content.

        Args:
            response_content: Raw response string from the model

        Returns:
            Cleaned JSON string
        """
        content = response_content.strip()

        # Check for markdown code block wrapping at the start
        if content.startswith("```"):
            # Find the end of the first line (```json or just ```)
            first_newline = content.find("\n")
            if first_newline != -1:
                # Remove opening ``` line
                content = content[first_newline + 1:]

            # Remove closing ```
            if content.endswith("```"):
                content = content[:-3].strip()
            return content

        # Look for ```json code block anywhere in the response
        # (Claude sometimes adds markdown headers before the JSON)
        import re
        json_block_match = re.search(r'```(?:json)?\s*\n([\s\S]*?)\n```', content)
        if json_block_match:
            logger.debug("Found JSON in markdown code block within response")
            return json_block_match.group(1).strip()

        # Try to find raw JSON object starting with {
        # This handles cases where there's text before the JSON
        json_start = content.find('{')
        if json_start > 0:
            # There's content before the JSON - try to extract just the JSON
            potential_json = content[json_start:]
            # Find the matching closing brace by counting braces
            brace_count = 0
            json_end = -1
            in_string = False
            escape_next = False

            for i, char in enumerate(potential_json):
                if escape_next:
                    escape_next = False
                    continue
                if char == '\\' and in_string:
                    escape_next = True
                    continue
                if char == '"' and not escape_next:
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        json_end = i + 1
                        break

            if json_end > 0:
                logger.debug(f"Extracted JSON object starting at position {json_start}")
                return potential_json[:json_end]

        return content

    def _parse_response(
        self,
        response_content: str,
        model: str
    ) -> tuple[dict[str, Any], list[CandidateIssue]]:
        """Parse JSON response from a model into structured data.

        Args:
            response_content: Raw JSON string from the model
            model: Model identifier (for attribution)

        Returns:
            Tuple of (repo_overview dict, list of CandidateIssue)

        Raises:
            ValueError: If JSON parsing fails or structure is invalid
        """
        # Debug: Log raw response preview
        preview_len = 500
        logger.debug(
            f"[{model}] Raw response preview (first {preview_len} chars): "
            f"{response_content[:preview_len]!r}"
        )
        logger.debug(
            f"[{model}] Raw response length: {len(response_content)} chars"
        )

        # Extract JSON from potential markdown wrapping
        cleaned_content = self._extract_json_from_response(response_content)
        if cleaned_content != response_content:
            logger.info(f"[{model}] Extracted JSON from markdown code block")

        try:
            data = json.loads(cleaned_content)
        except json.JSONDecodeError as e:
            logger.error(
                f"[{model}] Failed to parse JSON: {e}. "
                f"Content preview: {cleaned_content[:500]!r}"
            )
            raise ValueError(f"Invalid JSON response: {e}")

        # Debug: Log parsed structure
        logger.debug(f"[{model}] Parsed JSON keys: {list(data.keys())}")

        # Extract repo_overview
        repo_overview = data.get("repo_overview", {})
        if not isinstance(repo_overview, dict):
            logger.warning(f"[{model}] repo_overview is not a dict: {type(repo_overview)}")
            repo_overview = {}

        # Extract and parse issues
        issues_data = data.get("issues", [])
        logger.info(
            f"[{model}] Found 'issues' key with {len(issues_data) if isinstance(issues_data, list) else 'non-list'} items"
        )

        if not isinstance(issues_data, list):
            logger.warning(
                f"[{model}] 'issues' is not a list: {type(issues_data)}. "
                f"Value preview: {str(issues_data)[:200]!r}"
            )
            issues_data = []

        candidates: list[CandidateIssue] = []
        for idx, issue in enumerate(issues_data):
            if not isinstance(issue, dict):
                logger.warning(f"[{model}] Issue {idx} is not a dict: {type(issue)}")
                continue

            try:
                candidate = CandidateIssue(
                    id_hint=str(issue.get("id_hint", "")),
                    dimension=str(issue.get("dimension", "other")),
                    severity=str(issue.get("severity", "medium")),
                    files=issue.get("files", []) if isinstance(issue.get("files"), list) else [],
                    summary=str(issue.get("summary", "")),
                    detailed_description=str(issue.get("detailed_description", "")),
                    evidence_snippets=issue.get("evidence_snippets", []) if isinstance(issue.get("evidence_snippets"), list) else [],
                    potential_impact=str(issue.get("potential_impact", "")),
                    remediation_idea=str(issue.get("remediation_idea", "")),
                    confidence=str(issue.get("confidence", "medium")),
                    source_model=model,
                )
                candidates.append(candidate)
            except Exception as e:
                logger.warning(f"[{model}] Failed to parse issue {idx}: {e}")
                continue

        logger.info(f"[{model}] Successfully parsed {len(candidates)} candidates")

        return repo_overview, candidates

    async def _scan_with_model(
        self,
        model: str,
        repo_view: str,
        timeout_seconds: int = 300,  # 5 minute timeout per model
    ) -> ModelScanResult:
        """Scan repository with a single model.

        Calls the LLM with the repo view and parses the JSON response.
        Handles errors gracefully and returns a result indicating success/failure.

        Args:
            model: Model identifier to use
            repo_view: Markdown representation of the repository
            timeout_seconds: Timeout in seconds for the LLM call (default 5 minutes)

        Returns:
            ModelScanResult with scan results or error information
        """
        config = self._get_model_config(model)

        try:
            logger.info(f"Starting scan with model: {model}")

            # Build kwargs for the LLM call
            kwargs: dict[str, Any] = {}
            if config.get("extra_headers"):
                kwargs["extra_headers"] = config["extra_headers"]

            # Add timeout to kwargs for LiteLLM
            kwargs["timeout"] = timeout_seconds

            # IMPORTANT: Don't use response_format for Bedrock models!
            # Bedrock Claude interprets response_format as tool_calls and returns empty {}
            # Instead, we rely on the system prompt to request JSON output.
            is_bedrock = model.startswith("bedrock/")
            if not is_bedrock:
                kwargs["response_format"] = {"type": "json_object"}

            # Make the LLM call with timeout wrapper
            # Gemini 3 models need temperature=1.0 to avoid infinite loops and degraded reasoning
            is_gemini3 = "gemini-3" in model.lower() or "gemini-2.5" in model.lower()
            temperature = 1.0 if is_gemini3 else 0.1

            response = await asyncio.wait_for(
                self.llm.complete(
                    prompt=repo_view,
                    model=model,
                    system_prompt=BROAD_SCAN_SYSTEM_PROMPT,
                    max_tokens=config["max_tokens"],
                    temperature=temperature,
                    fallback=False,  # Don't use fallback - we want specific model results
                    **kwargs,
                ),
                timeout=timeout_seconds,
            )

            # Extract usage information
            usage = response.get("usage", {})
            tokens_used = usage.get("total_tokens", 0)
            cost_usd = response.get("cost", 0.0)

            # Parse the response - handle None content explicitly
            content = response.get("content") or ""
            repo_overview, candidates = self._parse_response(content, model)

            logger.info(
                f"Scan with {model} completed: "
                f"{len(candidates)} issues found, "
                f"{tokens_used} tokens used, "
                f"${cost_usd:.4f} cost"
            )

            return ModelScanResult(
                model=model,
                repo_overview=repo_overview,
                candidates=candidates,
                tokens_used=tokens_used,
                cost_usd=cost_usd,
                success=True,
                error=None,
            )

        except TimeoutError:
            logger.error(f"Timeout scanning with {model} after {timeout_seconds}s")
            return ModelScanResult(
                model=model,
                success=False,
                error=f"Timeout after {timeout_seconds} seconds",
            )
        except LLMError as e:
            logger.error(f"LLM error scanning with {model}: {e}")
            return ModelScanResult(
                model=model,
                success=False,
                error=f"LLM error: {str(e)}",
            )
        except ValueError as e:
            logger.error(f"Parse error scanning with {model}: {e}")
            return ModelScanResult(
                model=model,
                success=False,
                error=f"Parse error: {str(e)}",
            )
        except Exception as e:
            logger.error(f"Unexpected error scanning with {model}: {e}")
            return ModelScanResult(
                model=model,
                success=False,
                error=f"Unexpected error: {str(e)}",
            )

    async def scan(self, repo_view: str) -> BroadScanResult:
        """Run broad scan across all configured models.

        Sends the repo view to each model in parallel, parses JSON responses,
        and aggregates results. Continues even if some models fail.

        Args:
            repo_view: Markdown representation of the repository

        Returns:
            BroadScanResult with aggregated results from all models
        """
        logger.info(f"Starting broad scan with {len(self.models)} models: {self.models}")

        # Run all model scans in parallel
        tasks = [
            self._scan_with_model(model, repo_view)
            for model in self.models
        ]
        model_results = await asyncio.gather(*tasks, return_exceptions=False)

        # Aggregate results
        all_candidates: list[CandidateIssue] = []
        models_succeeded: list[str] = []
        total_tokens = 0
        total_cost = 0.0
        repo_overview: dict[str, Any] = {}

        for result in model_results:
            if result.success:
                models_succeeded.append(result.model)
                all_candidates.extend(result.candidates)
                total_tokens += result.tokens_used
                total_cost += result.cost_usd

                # Use first successful model's repo_overview
                if not repo_overview and result.repo_overview:
                    repo_overview = result.repo_overview
            else:
                logger.warning(
                    f"Model {result.model} failed: {result.error}"
                )

        logger.info(
            f"Broad scan completed: "
            f"{len(models_succeeded)}/{len(self.models)} models succeeded, "
            f"{len(all_candidates)} total candidates, "
            f"{total_tokens} total tokens, "
            f"${total_cost:.4f} total cost"
        )

        # Log warning if cost exceeds limit (but don't fail - work is already done)
        if self.max_cost_usd is not None and total_cost > self.max_cost_usd:
            logger.warning(
                f"AI scan cost ${total_cost:.4f} exceeds limit ${self.max_cost_usd:.2f}. "
                f"Consider increasing AI_SCAN_MAX_COST_PER_SCAN or reducing models."
            )

        return BroadScanResult(
            repo_overview=repo_overview,
            candidates=all_candidates,
            models_used=self.models.copy(),
            models_succeeded=models_succeeded,
            total_tokens=total_tokens,
            total_cost=total_cost,
            model_results=list(model_results),
        )


# =============================================================================
# Convenience Functions
# =============================================================================


def get_broad_scan_agent(
    llm_gateway: LLMGateway | None = None,
    models: list[str] | None = None,
    max_cost_usd: float | None = None,
) -> BroadScanAgent:
    """Create a BroadScanAgent instance.

    Args:
        llm_gateway: Optional LLMGateway instance. Creates one if not provided.
        models: Optional list of models to use. Uses defaults if not provided.
        max_cost_usd: Optional cost limit in USD. Uses config default if not provided.

    Returns:
        Configured BroadScanAgent instance
    """
    from app.services.llm_gateway import get_llm_gateway

    if llm_gateway is None:
        llm_gateway = get_llm_gateway()

    return BroadScanAgent(llm_gateway, models, max_cost_usd)
