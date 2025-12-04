"""Property-based tests for BroadScanAgent.

Uses Hypothesis for property-based testing to verify correctness properties
defined in the design document.
"""

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.services.broad_scan_agent import (
    BroadScanAgent,
    BroadScanResult,
    CandidateIssue,
    ModelScanResult,
    MODEL_CONFIGS,
    DEFAULT_MODEL_CONFIG,
    BROAD_SCAN_SYSTEM_PROMPT,
)


# =============================================================================
# Custom Strategies for Test Data Generation
# =============================================================================


@st.composite
def valid_dimension(draw) -> str:
    """Generate valid issue dimensions."""
    return draw(st.sampled_from([
        "security", "db_consistency", "api_correctness", "code_health", "other"
    ]))


@st.composite
def valid_severity(draw) -> str:
    """Generate valid severity levels."""
    return draw(st.sampled_from(["critical", "high", "medium", "low"]))


@st.composite
def valid_confidence(draw) -> str:
    """Generate valid confidence levels."""
    return draw(st.sampled_from(["high", "medium", "low"]))


@st.composite
def file_location(draw) -> dict[str, Any]:
    """Generate a valid file location dict."""
    line_start = draw(st.integers(min_value=1, max_value=1000))
    line_end = draw(st.integers(min_value=line_start, max_value=line_start + 100))
    # Generate path with guaranteed structure
    dirname = draw(st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_-"),
        min_size=1,
        max_size=20
    ).filter(lambda s: s.strip()))
    filename = draw(st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_-"),
        min_size=1,
        max_size=20
    ).filter(lambda s: s.strip()))
    ext = draw(st.sampled_from([".py", ".js", ".ts", ".go", ".rs", ".java"]))
    return {
        "path": f"{dirname}/{filename}{ext}",
        "line_start": line_start,
        "line_end": line_end,
    }


@st.composite
def candidate_issue_dict(draw) -> dict[str, Any]:
    """Generate a valid candidate issue dictionary (as returned by LLM)."""
    return {
        "id_hint": draw(st.text(min_size=1, max_size=20).filter(lambda s: s.strip())),
        "dimension": draw(valid_dimension()),
        "severity": draw(valid_severity()),
        "files": draw(st.lists(file_location(), min_size=1, max_size=3)),
        "summary": draw(st.text(min_size=5, max_size=100).filter(lambda s: s.strip())),
        "detailed_description": draw(st.text(min_size=10, max_size=500).filter(lambda s: s.strip())),
        "evidence_snippets": draw(st.lists(
            st.text(min_size=5, max_size=200).filter(lambda s: s.strip()),
            min_size=1,
            max_size=3
        )),
        "potential_impact": draw(st.text(min_size=5, max_size=200).filter(lambda s: s.strip())),
        "remediation_idea": draw(st.text(min_size=5, max_size=200).filter(lambda s: s.strip())),
        "confidence": draw(valid_confidence()),
    }


@st.composite
def repo_overview_dict(draw) -> dict[str, Any]:
    """Generate a valid repo overview dictionary."""
    return {
        "guessed_project_type": draw(st.text(min_size=5, max_size=100).filter(lambda s: s.strip())),
        "main_languages": draw(st.lists(
            st.sampled_from(["python", "javascript", "typescript", "go", "rust", "java"]),
            min_size=1,
            max_size=3,
            unique=True
        )),
        "main_components": draw(st.lists(
            st.text(min_size=3, max_size=30).filter(lambda s: s.strip()),
            min_size=1,
            max_size=5
        )),
        "frameworks_detected": draw(st.lists(
            st.sampled_from(["FastAPI", "Django", "React", "Next.js", "Express", "Spring"]),
            min_size=0,
            max_size=3,
            unique=True
        )),
        "overall_assessment": draw(st.text(min_size=10, max_size=200).filter(lambda s: s.strip())),
    }


@st.composite
def valid_llm_response(draw) -> dict[str, Any]:
    """Generate a valid LLM response with repo_overview and issues."""
    num_issues = draw(st.integers(min_value=0, max_value=5))
    issues = [draw(candidate_issue_dict()) for _ in range(num_issues)]
    
    return {
        "repo_overview": draw(repo_overview_dict()),
        "issues": issues,
    }


@st.composite
def model_list(draw) -> list[str]:
    """Generate a list of model identifiers."""
    available_models = list(MODEL_CONFIGS.keys())
    num_models = draw(st.integers(min_value=2, max_value=len(available_models)))
    return draw(st.lists(
        st.sampled_from(available_models),
        min_size=num_models,
        max_size=num_models,
        unique=True
    ))


# =============================================================================
# Mock LLM Gateway for Testing
# =============================================================================


def create_mock_llm_gateway(
    responses: dict[str, dict[str, Any]] | None = None,
    failures: set[str] | None = None,
) -> MagicMock:
    """Create a mock LLMGateway for testing.
    
    Args:
        responses: Dict mapping model names to their response data
        failures: Set of model names that should raise exceptions
        
    Returns:
        Mock LLMGateway instance
    """
    mock_gateway = MagicMock()
    failures = failures or set()
    responses = responses or {}
    
    async def mock_complete(
        prompt: str,
        model: str,
        system_prompt: str | None = None,
        response_format: dict | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.2,
        fallback: bool = True,
        **kwargs,
    ) -> dict[str, Any]:
        if model in failures:
            from app.services.llm_gateway import LLMError
            raise LLMError(f"Mock failure for {model}")
        
        # Get response data for this model, or generate default
        response_data = responses.get(model, {
            "repo_overview": {
                "guessed_project_type": "Test project",
                "main_languages": ["python"],
                "main_components": ["API"],
                "frameworks_detected": [],
                "overall_assessment": "Test assessment",
            },
            "issues": [],
        })
        
        return {
            "content": json.dumps(response_data),
            "model": model,
            "usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 500,
                "total_tokens": 1500,
            },
            "cost": 0.01,
        }
    
    mock_gateway.complete = AsyncMock(side_effect=mock_complete)
    return mock_gateway


# =============================================================================
# Property Tests for Multi-Model Execution
# =============================================================================


class TestMultiModelExecution:
    """Property tests for multi-model execution.

    **Feature: ai-scan-integration, Property 7: Multi-Model Execution**
    **Validates: Requirements 3.1**
    """

    @given(model_list())
    @settings(max_examples=100)
    def test_all_configured_models_called(self, models: list[str]):
        """
        **Feature: ai-scan-integration, Property 7: Multi-Model Execution**
        **Validates: Requirements 3.1**

        Property: For any broad scan, the system SHALL call at least two LLM models
        (or all configured models if fewer than two).
        """
        assume(len(models) >= 2)
        
        # Track which models were called
        called_models: list[str] = []
        
        async def tracking_complete(
            prompt: str,
            model: str,
            **kwargs,
        ) -> dict[str, Any]:
            called_models.append(model)
            return {
                "content": json.dumps({
                    "repo_overview": {"guessed_project_type": "Test"},
                    "issues": [],
                }),
                "model": model,
                "usage": {"total_tokens": 100},
                "cost": 0.001,
            }
        
        mock_gateway = MagicMock()
        mock_gateway.complete = AsyncMock(side_effect=tracking_complete)
        
        agent = BroadScanAgent(mock_gateway, models=models)
        
        # Run the scan
        result = asyncio.run(agent.scan("# Test repo view"))
        
        # Property: All configured models should be called
        assert set(called_models) == set(models), (
            f"Not all models were called. Expected {models}, got {called_models}"
        )
        
        # Property: At least 2 models should be used
        assert len(result.models_used) >= 2, (
            f"Expected at least 2 models, got {len(result.models_used)}"
        )

    @given(model_list())
    @settings(max_examples=100)
    def test_models_used_tracked_correctly(self, models: list[str]):
        """
        **Feature: ai-scan-integration, Property 7: Multi-Model Execution**
        **Validates: Requirements 3.1**

        Property: The models_used field should contain all models that were configured.
        """
        assume(len(models) >= 2)
        
        mock_gateway = create_mock_llm_gateway()
        agent = BroadScanAgent(mock_gateway, models=models)
        
        result = asyncio.run(agent.scan("# Test repo view"))
        
        # Property: models_used should match configured models
        assert set(result.models_used) == set(models), (
            f"models_used mismatch. Expected {models}, got {result.models_used}"
        )


# =============================================================================
# Property Tests for JSON Response Parsing
# =============================================================================


class TestJSONResponseParsing:
    """Property tests for JSON response parsing.

    **Feature: ai-scan-integration, Property 8: JSON Response Parsing**
    **Validates: Requirements 3.2**
    """

    @given(valid_llm_response())
    @settings(max_examples=100)
    def test_valid_json_parsed_successfully(self, response_data: dict[str, Any]):
        """
        **Feature: ai-scan-integration, Property 8: JSON Response Parsing**
        **Validates: Requirements 3.2**

        Property: For any valid JSON response from an LLM containing repo_overview
        and issues fields, parsing SHALL succeed and extract both fields.
        """
        mock_gateway = MagicMock()
        agent = BroadScanAgent(mock_gateway, models=["test/model"])
        
        # Parse the response
        json_str = json.dumps(response_data)
        repo_overview, candidates = agent._parse_response(json_str, "test/model")
        
        # Property: repo_overview should be extracted
        assert isinstance(repo_overview, dict), "repo_overview should be a dict"
        assert repo_overview == response_data["repo_overview"], (
            "repo_overview should match input"
        )
        
        # Property: issues should be parsed into CandidateIssue objects
        assert len(candidates) == len(response_data["issues"]), (
            f"Expected {len(response_data['issues'])} candidates, got {len(candidates)}"
        )
        
        # Property: Each candidate should have source_model set
        for candidate in candidates:
            assert candidate.source_model == "test/model", (
                "source_model should be set correctly"
            )

    @given(candidate_issue_dict())
    @settings(max_examples=100)
    def test_issue_fields_preserved(self, issue_data: dict[str, Any]):
        """
        **Feature: ai-scan-integration, Property 8: JSON Response Parsing**
        **Validates: Requirements 3.2**

        Property: All fields from a valid issue should be preserved in the
        CandidateIssue object.
        """
        mock_gateway = MagicMock()
        agent = BroadScanAgent(mock_gateway, models=["test/model"])
        
        response_data = {
            "repo_overview": {},
            "issues": [issue_data],
        }
        
        json_str = json.dumps(response_data)
        _, candidates = agent._parse_response(json_str, "test/model")
        
        assert len(candidates) == 1, "Should parse exactly one candidate"
        candidate = candidates[0]
        
        # Property: All fields should be preserved
        assert candidate.id_hint == issue_data["id_hint"]
        assert candidate.dimension == issue_data["dimension"]
        assert candidate.severity == issue_data["severity"]
        assert candidate.files == issue_data["files"]
        assert candidate.summary == issue_data["summary"]
        assert candidate.detailed_description == issue_data["detailed_description"]
        assert candidate.evidence_snippets == issue_data["evidence_snippets"]
        assert candidate.potential_impact == issue_data["potential_impact"]
        assert candidate.remediation_idea == issue_data["remediation_idea"]
        assert candidate.confidence == issue_data["confidence"]

    @given(st.text(min_size=1, max_size=100).filter(lambda s: s.strip()))
    @settings(max_examples=50)
    def test_invalid_json_raises_error(self, invalid_json: str):
        """
        **Feature: ai-scan-integration, Property 8: JSON Response Parsing**
        **Validates: Requirements 3.2**

        Property: Invalid JSON should raise a ValueError.
        """
        # Make sure it's actually invalid JSON
        try:
            json.loads(invalid_json)
            # If it parses, skip this test case
            assume(False)
        except json.JSONDecodeError:
            pass
        
        mock_gateway = MagicMock()
        agent = BroadScanAgent(mock_gateway, models=["test/model"])
        
        with pytest.raises(ValueError, match="Invalid JSON"):
            agent._parse_response(invalid_json, "test/model")

    @given(st.dictionaries(
        keys=st.text(min_size=1, max_size=20),
        values=st.text(min_size=1, max_size=50),
        min_size=0,
        max_size=5
    ))
    @settings(max_examples=50)
    def test_missing_fields_handled_gracefully(self, partial_data: dict[str, Any]):
        """
        **Feature: ai-scan-integration, Property 8: JSON Response Parsing**
        **Validates: Requirements 3.2**

        Property: JSON with missing fields should be handled gracefully,
        using defaults where appropriate.
        """
        mock_gateway = MagicMock()
        agent = BroadScanAgent(mock_gateway, models=["test/model"])
        
        json_str = json.dumps(partial_data)
        repo_overview, candidates = agent._parse_response(json_str, "test/model")
        
        # Property: Should not raise, should return empty defaults
        assert isinstance(repo_overview, dict)
        assert isinstance(candidates, list)


# =============================================================================
# Property Tests for Model Failure Resilience
# =============================================================================


class TestModelFailureResilience:
    """Property tests for model failure resilience.

    **Feature: ai-scan-integration, Property 10: Model Failure Resilience**
    **Validates: Requirements 3.4**
    """

    @given(model_list(), st.integers(min_value=1))
    @settings(max_examples=100)
    def test_scan_continues_with_partial_failures(
        self, 
        models: list[str], 
        failure_seed: int
    ):
        """
        **Feature: ai-scan-integration, Property 10: Model Failure Resilience**
        **Validates: Requirements 3.4**

        Property: For any broad scan where one model fails, the scan SHALL
        complete successfully using results from remaining models.
        """
        assume(len(models) >= 2)
        
        # Deterministically select one model to fail
        failing_model = models[failure_seed % len(models)]
        failures = {failing_model}
        
        # Create responses for successful models
        responses = {}
        for model in models:
            if model not in failures:
                responses[model] = {
                    "repo_overview": {"guessed_project_type": f"Project from {model}"},
                    "issues": [{
                        "id_hint": f"issue-{model}",
                        "dimension": "security",
                        "severity": "high",
                        "files": [{"path": "test.py", "line_start": 1, "line_end": 10}],
                        "summary": f"Issue from {model}",
                        "detailed_description": "Test description",
                        "evidence_snippets": ["code snippet"],
                        "potential_impact": "Test impact",
                        "remediation_idea": "Test fix",
                        "confidence": "high",
                    }],
                }
        
        mock_gateway = create_mock_llm_gateway(responses=responses, failures=failures)
        agent = BroadScanAgent(mock_gateway, models=models)
        
        # Run the scan - should not raise
        result = asyncio.run(agent.scan("# Test repo view"))
        
        # Property: Scan should complete (not raise)
        assert isinstance(result, BroadScanResult)
        
        # Property: Successful models should be tracked
        expected_succeeded = set(models) - failures
        assert set(result.models_succeeded) == expected_succeeded, (
            f"Expected succeeded: {expected_succeeded}, got: {result.models_succeeded}"
        )
        
        # Property: Should have candidates from successful models
        assert len(result.candidates) == len(expected_succeeded), (
            f"Expected {len(expected_succeeded)} candidates, got {len(result.candidates)}"
        )

    @given(model_list())
    @settings(max_examples=50)
    def test_all_models_fail_returns_empty_result(self, models: list[str]):
        """
        **Feature: ai-scan-integration, Property 10: Model Failure Resilience**
        **Validates: Requirements 3.4**

        Property: If all models fail, the scan should still complete
        with an empty result (not raise an exception).
        """
        assume(len(models) >= 2)
        
        # All models fail
        failures = set(models)
        
        mock_gateway = create_mock_llm_gateway(failures=failures)
        agent = BroadScanAgent(mock_gateway, models=models)
        
        # Run the scan - should not raise
        result = asyncio.run(agent.scan("# Test repo view"))
        
        # Property: Should return empty result, not raise
        assert isinstance(result, BroadScanResult)
        assert len(result.models_succeeded) == 0
        assert len(result.candidates) == 0
        assert result.repo_overview == {}

    @given(model_list())
    @settings(max_examples=100)
    def test_failed_models_logged_in_results(self, models: list[str]):
        """
        **Feature: ai-scan-integration, Property 10: Model Failure Resilience**
        **Validates: Requirements 3.4**

        Property: Failed models should be tracked in model_results with
        success=False and an error message.
        """
        assume(len(models) >= 2)
        
        # First model fails
        failing_model = models[0]
        failures = {failing_model}
        
        mock_gateway = create_mock_llm_gateway(failures=failures)
        agent = BroadScanAgent(mock_gateway, models=models)
        
        result = asyncio.run(agent.scan("# Test repo view"))
        
        # Property: model_results should contain all models
        assert len(result.model_results) == len(models)
        
        # Property: Failed model should have success=False and error message
        failed_results = [r for r in result.model_results if r.model == failing_model]
        assert len(failed_results) == 1
        failed_result = failed_results[0]
        assert failed_result.success is False
        assert failed_result.error is not None
        assert len(failed_result.error) > 0


# =============================================================================
# Unit Tests for Model Configuration
# =============================================================================


class TestModelConfiguration:
    """Unit tests for model configuration."""

    def test_known_models_have_config(self):
        """Known models should have specific configurations."""
        assert "gemini/gemini-3-pro-preview" in MODEL_CONFIGS
        assert "bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0" in MODEL_CONFIGS

    def test_gemini_config(self):
        """Gemini 3 Pro should have correct config."""
        config = MODEL_CONFIGS["gemini/gemini-3-pro-preview"]
        assert config["max_tokens"] == 65536
        assert config["extra_headers"] == {}

    def test_bedrock_claude_config(self):
        """Claude Sonnet 4.5 on Bedrock should have 1M context header."""
        config = MODEL_CONFIGS["bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0"]
        assert config["max_tokens"] == 8192
        assert "anthropic-beta" in config["extra_headers"]
        assert "context-1m" in config["extra_headers"]["anthropic-beta"]

    def test_unknown_model_gets_default_config(self):
        """Unknown models should get default configuration."""
        mock_gateway = MagicMock()
        agent = BroadScanAgent(mock_gateway, models=["unknown/model"])
        
        config = agent._get_model_config("unknown/model")
        assert config == DEFAULT_MODEL_CONFIG


# =============================================================================
# Unit Tests for System Prompt
# =============================================================================


class TestSystemPrompt:
    """Unit tests for system prompt."""

    def test_system_prompt_contains_dimensions(self):
        """System prompt should document all issue dimensions."""
        assert "security" in BROAD_SCAN_SYSTEM_PROMPT
        assert "db_consistency" in BROAD_SCAN_SYSTEM_PROMPT
        assert "api_correctness" in BROAD_SCAN_SYSTEM_PROMPT
        assert "code_health" in BROAD_SCAN_SYSTEM_PROMPT
        assert "other" in BROAD_SCAN_SYSTEM_PROMPT

    def test_system_prompt_contains_severities(self):
        """System prompt should document all severity levels."""
        assert "critical" in BROAD_SCAN_SYSTEM_PROMPT
        assert "high" in BROAD_SCAN_SYSTEM_PROMPT
        assert "medium" in BROAD_SCAN_SYSTEM_PROMPT
        assert "low" in BROAD_SCAN_SYSTEM_PROMPT

    def test_system_prompt_contains_json_schema(self):
        """System prompt should contain JSON output schema."""
        assert "repo_overview" in BROAD_SCAN_SYSTEM_PROMPT
        assert "issues" in BROAD_SCAN_SYSTEM_PROMPT
        assert "id_hint" in BROAD_SCAN_SYSTEM_PROMPT
        assert "dimension" in BROAD_SCAN_SYSTEM_PROMPT
        assert "severity" in BROAD_SCAN_SYSTEM_PROMPT


# =============================================================================
# Property Tests for Cost Tracking
# =============================================================================


def create_mock_llm_gateway_with_cost(
    model_costs: dict[str, tuple[int, float]],
    failures: set[str] | None = None,
) -> MagicMock:
    """Create a mock LLMGateway that returns specific costs per model.
    
    Args:
        model_costs: Dict mapping model names to (tokens, cost_usd) tuples
        failures: Set of model names that should raise exceptions
        
    Returns:
        Mock LLMGateway instance
    """
    mock_gateway = MagicMock()
    failures = failures or set()
    
    async def mock_complete(
        prompt: str,
        model: str,
        system_prompt: str | None = None,
        response_format: dict | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.2,
        fallback: bool = True,
        **kwargs,
    ) -> dict[str, Any]:
        if model in failures:
            from app.services.llm_gateway import LLMError
            raise LLMError(f"Mock failure for {model}")
        
        tokens, cost = model_costs.get(model, (1000, 0.01))
        
        return {
            "content": json.dumps({
                "repo_overview": {"guessed_project_type": "Test project"},
                "issues": [],
            }),
            "model": model,
            "usage": {
                "prompt_tokens": tokens // 2,
                "completion_tokens": tokens // 2,
                "total_tokens": tokens,
            },
            "cost": cost,
        }
    
    mock_gateway.complete = AsyncMock(side_effect=mock_complete)
    return mock_gateway


class TestCostTracking:
    """Property tests for cost tracking.

    **Feature: ai-scan-integration, Property 17: Cost Tracking**
    **Validates: Requirements 8.1**
    """

    @given(
        st.lists(
            st.tuples(
                st.sampled_from(list(MODEL_CONFIGS.keys())),
                st.integers(min_value=100, max_value=100000),
                st.floats(min_value=0.001, max_value=1.0, allow_nan=False, allow_infinity=False),
            ),
            min_size=2,
            max_size=4,
            unique_by=lambda x: x[0],  # Unique models
        )
    )
    @settings(max_examples=100, deadline=None)
    def test_total_cost_aggregated_correctly(
        self, 
        model_data: list[tuple[str, int, float]]
    ):
        """
        **Feature: ai-scan-integration, Property 17: Cost Tracking**
        **Validates: Requirements 8.1**

        Property: For any completed AI scan, the cache SHALL contain
        total_tokens_used > 0 and total_cost_usd >= 0.
        """
        models = [m[0] for m in model_data]
        model_costs = {m[0]: (m[1], m[2]) for m in model_data}
        
        expected_total_tokens = sum(m[1] for m in model_data)
        expected_total_cost = sum(m[2] for m in model_data)
        
        mock_gateway = create_mock_llm_gateway_with_cost(model_costs)
        agent = BroadScanAgent(mock_gateway, models=models, max_cost_usd=None)
        
        result = asyncio.run(agent.scan("# Test repo view"))
        
        # Property: total_tokens should be sum of all model tokens
        assert result.total_tokens == expected_total_tokens, (
            f"Expected {expected_total_tokens} tokens, got {result.total_tokens}"
        )
        
        # Property: total_cost should be sum of all model costs
        assert abs(result.total_cost - expected_total_cost) < 0.0001, (
            f"Expected ${expected_total_cost:.4f}, got ${result.total_cost:.4f}"
        )
        
        # Property: total_tokens > 0 for completed scan
        assert result.total_tokens > 0, "total_tokens should be > 0"
        
        # Property: total_cost >= 0 for completed scan
        assert result.total_cost >= 0, "total_cost should be >= 0"

    @given(model_list())
    @settings(max_examples=100, deadline=None)
    def test_cost_tracked_per_model(self, models: list[str]):
        """
        **Feature: ai-scan-integration, Property 17: Cost Tracking**
        **Validates: Requirements 8.1**

        Property: Each model's tokens and cost should be tracked individually
        in model_results.
        """
        assume(len(models) >= 2)
        
        # Assign different costs to each model
        model_costs = {model: (1000 * (i + 1), 0.01 * (i + 1)) for i, model in enumerate(models)}
        
        mock_gateway = create_mock_llm_gateway_with_cost(model_costs)
        agent = BroadScanAgent(mock_gateway, models=models, max_cost_usd=None)
        
        result = asyncio.run(agent.scan("# Test repo view"))
        
        # Property: Each model should have its cost tracked
        for model_result in result.model_results:
            if model_result.success:
                expected_tokens, expected_cost = model_costs[model_result.model]
                assert model_result.tokens_used == expected_tokens, (
                    f"Model {model_result.model}: expected {expected_tokens} tokens, "
                    f"got {model_result.tokens_used}"
                )
                assert abs(model_result.cost_usd - expected_cost) < 0.0001, (
                    f"Model {model_result.model}: expected ${expected_cost:.4f}, "
                    f"got ${model_result.cost_usd:.4f}"
                )

    @given(
        model_list(),
        st.integers(min_value=1)
    )
    @settings(max_examples=100)
    def test_failed_models_dont_contribute_to_cost(
        self, 
        models: list[str],
        failure_seed: int
    ):
        """
        **Feature: ai-scan-integration, Property 17: Cost Tracking**
        **Validates: Requirements 8.1**

        Property: Failed models should not contribute to total cost.
        """
        assume(len(models) >= 2)
        
        # Select one model to fail
        failing_model = models[failure_seed % len(models)]
        failures = {failing_model}
        
        # Assign costs
        model_costs = {model: (1000, 0.01) for model in models}
        
        mock_gateway = create_mock_llm_gateway_with_cost(model_costs, failures=failures)
        agent = BroadScanAgent(mock_gateway, models=models, max_cost_usd=None)
        
        result = asyncio.run(agent.scan("# Test repo view"))
        
        # Property: Total cost should only include successful models
        successful_models = set(models) - failures
        expected_cost = sum(model_costs[m][1] for m in successful_models)
        expected_tokens = sum(model_costs[m][0] for m in successful_models)
        
        assert abs(result.total_cost - expected_cost) < 0.0001, (
            f"Expected ${expected_cost:.4f} (excluding failed), got ${result.total_cost:.4f}"
        )
        assert result.total_tokens == expected_tokens, (
            f"Expected {expected_tokens} tokens (excluding failed), got {result.total_tokens}"
        )


# =============================================================================
# Property Tests for Cost Limit
# =============================================================================


class TestCostLimit:
    """Property tests for per-scan cost limit.

    **Feature: ai-scan-integration, Property 18: Per-Scan Cost Limit**
    **Validates: Requirements 8.2**
    """

    @given(
        st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False),
        st.floats(min_value=1.1, max_value=10.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_cost_exceeding_limit_raises_error(
        self, 
        limit: float,
        cost_multiplier: float
    ):
        """
        **Feature: ai-scan-integration, Property 18: Per-Scan Cost Limit**
        **Validates: Requirements 8.2**

        Property: For any scan that would exceed the per-scan cost limit,
        the scan SHALL abort and raise CostLimitExceededError.
        """
        from app.services.broad_scan_agent import CostLimitExceededError
        
        # Cost that exceeds the limit
        actual_cost = limit * cost_multiplier
        
        models = ["gemini/gemini-3-pro-preview", "bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0"]
        model_costs = {model: (10000, actual_cost / 2) for model in models}
        
        mock_gateway = create_mock_llm_gateway_with_cost(model_costs)
        agent = BroadScanAgent(mock_gateway, models=models, max_cost_usd=limit)
        
        # Property: Should raise CostLimitExceededError
        with pytest.raises(CostLimitExceededError) as exc_info:
            asyncio.run(agent.scan("# Test repo view"))
        
        # Property: Error should contain cost and limit info
        assert exc_info.value.current_cost > limit
        assert exc_info.value.limit == limit

    @given(
        st.floats(min_value=1.0, max_value=10.0, allow_nan=False, allow_infinity=False),
        st.floats(min_value=0.1, max_value=0.9, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_cost_under_limit_succeeds(
        self, 
        limit: float,
        cost_fraction: float
    ):
        """
        **Feature: ai-scan-integration, Property 18: Per-Scan Cost Limit**
        **Validates: Requirements 8.2**

        Property: Scans with cost under the limit should complete successfully.
        """
        # Cost that is under the limit
        actual_cost = limit * cost_fraction
        
        models = ["gemini/gemini-3-pro-preview", "bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0"]
        model_costs = {model: (10000, actual_cost / 2) for model in models}
        
        mock_gateway = create_mock_llm_gateway_with_cost(model_costs)
        agent = BroadScanAgent(mock_gateway, models=models, max_cost_usd=limit)
        
        # Property: Should complete without raising
        result = asyncio.run(agent.scan("# Test repo view"))
        
        assert isinstance(result, BroadScanResult)
        assert result.total_cost < limit

    @given(model_list())
    @settings(max_examples=50)
    def test_high_limit_allows_high_cost(self, models: list[str]):
        """
        **Feature: ai-scan-integration, Property 18: Per-Scan Cost Limit**
        **Validates: Requirements 8.2**

        Property: When max_cost_usd is set very high, high costs should be allowed.
        """
        assume(len(models) >= 2)
        
        # Very high cost
        model_costs = {model: (100000, 100.0) for model in models}
        expected_total_cost = sum(model_costs[m][1] for m in models)
        
        mock_gateway = create_mock_llm_gateway_with_cost(model_costs)
        # Set a very high limit that exceeds the expected cost
        agent = BroadScanAgent(mock_gateway, models=models, max_cost_usd=expected_total_cost + 1000.0)
        
        # Property: Should complete without raising even with high cost
        result = asyncio.run(agent.scan("# Test repo view"))
        
        assert isinstance(result, BroadScanResult)
        assert result.total_cost > 0

    def test_cost_limit_from_config(self):
        """
        **Feature: ai-scan-integration, Property 18: Per-Scan Cost Limit**
        **Validates: Requirements 8.2**

        Property: When max_cost_usd is not specified, it should use config default.
        """
        from app.core.config import settings
        
        mock_gateway = MagicMock()
        agent = BroadScanAgent(mock_gateway, models=["test/model"])
        
        # Property: Should use config default
        assert agent.max_cost_usd == settings.ai_scan_max_cost_per_scan
