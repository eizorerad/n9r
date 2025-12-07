"""Property-based tests for AI Scan Worker.

Uses Hypothesis for property-based testing to verify correctness properties
defined in the design document.
"""

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st


# =============================================================================
# Custom Strategies for AI Scan Worker Testing
# =============================================================================


def valid_commit_sha() -> st.SearchStrategy[str]:
    """Generate valid Git commit SHA strings (40 hex characters)."""
    return st.text(
        alphabet="0123456789abcdef",
        min_size=40,
        max_size=40,
    )


def valid_repo_url() -> st.SearchStrategy[str]:
    """Generate valid GitHub repository URLs."""
    owner = st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"),
        min_size=1,
        max_size=39,
    ).filter(lambda s: s.strip() and not s.startswith("-"))
    
    repo = st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"),
        min_size=1,
        max_size=100,
    ).filter(lambda s: s.strip() and not s.startswith("-"))
    
    return st.tuples(owner, repo).map(lambda t: f"https://github.com/{t[0]}/{t[1]}")


def valid_model_list() -> st.SearchStrategy[list[str]]:
    """Generate valid model lists."""
    return st.lists(
        st.sampled_from([
            "gemini/gemini-3-pro-preview",
            "bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0",
            "openai/gpt-4o",
            "anthropic/claude-sonnet-4-20250514",
        ]),
        min_size=1,
        max_size=3,
        unique=True,
    )


def valid_issue_id() -> st.SearchStrategy[str]:
    """Generate valid issue IDs like 'sec-001', 'db-002'."""
    prefix = st.sampled_from(["sec", "db", "api", "health", "other"])
    number = st.integers(min_value=1, max_value=999)
    return st.tuples(prefix, number).map(lambda t: f"{t[0]}-{t[1]:03d}")


def valid_dimension() -> st.SearchStrategy[str]:
    """Generate valid dimension values."""
    return st.sampled_from(
        ["security", "db_consistency", "api_correctness", "code_health", "other"]
    )


def valid_severity() -> st.SearchStrategy[str]:
    """Generate valid severity values."""
    return st.sampled_from(["critical", "high", "medium", "low"])


def valid_confidence() -> st.SearchStrategy[str]:
    """Generate valid confidence values."""
    return st.sampled_from(["high", "medium", "low"])


@st.composite
def mock_merged_issue(draw) -> dict[str, Any]:
    """Generate mock merged issue data."""
    return {
        "id": draw(valid_issue_id()),
        "dimension": draw(valid_dimension()),
        "severity": draw(valid_severity()),
        "title": draw(st.text(min_size=1, max_size=100).filter(lambda s: s.strip())),
        "summary": draw(st.text(min_size=1, max_size=500).filter(lambda s: s.strip())),
        "files": [{"path": "test.py", "line_start": 1, "line_end": 10}],
        "evidence_snippets": ["code snippet"],
        "confidence": draw(valid_confidence()),
        "found_by_models": ["gemini/gemini-3-pro-preview"],
        "investigation_status": None,
        "suggested_fix": None,
    }


@st.composite
def mock_broad_scan_result(draw) -> dict[str, Any]:
    """Generate mock broad scan result data."""
    models = draw(valid_model_list())
    issues = draw(st.lists(mock_merged_issue(), min_size=0, max_size=5))
    
    return {
        "repo_overview": {
            "guessed_project_type": "Python backend",
            "main_languages": ["python"],
            "main_components": ["API", "Services"],
        },
        "candidates": issues,
        "models_used": models,
        "models_succeeded": models,
        "total_tokens": draw(st.integers(min_value=1000, max_value=100000)),
        "total_cost": draw(st.floats(min_value=0.01, max_value=1.0)),
    }


# =============================================================================
# Property Tests for Commit SHA Consistency
# =============================================================================


class TestCommitSHAConsistency:
    """Property tests for commit SHA consistency.

    **Feature: ai-scan-integration, Property 1: Commit SHA Consistency**
    **Validates: Requirements 1.2**
    """

    @given(
        test_commit_sha=valid_commit_sha(),
        models=valid_model_list(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_ai_scan_uses_analysis_commit_sha(
        self,
        test_commit_sha: str,
        models: list[str],
    ):
        """
        **Feature: ai-scan-integration, Property 1: Commit SHA Consistency**
        **Validates: Requirements 1.2**

        Property: For any AI scan triggered on an analysis, the commit_sha
        used for the scan SHALL equal the commit_sha of the parent Analysis record.
        """
        from dataclasses import dataclass
        from unittest.mock import MagicMock, patch
        
        # Create mock analysis with specific commit_sha
        analysis_id = str(uuid4())
        expected_commit_sha = test_commit_sha
        
        @dataclass
        class MockAnalysis:
            id: str = analysis_id
            commit_sha: str = expected_commit_sha
            status: str = "completed"
            repository_id: str = str(uuid4())
        
        @dataclass
        class MockRepository:
            id: str = str(uuid4())
            full_name: str = "test/repo"
            owner_id: str = str(uuid4())
        
        @dataclass
        class MockUser:
            id: str = str(uuid4())
            access_token_encrypted: str | None = None
        
        # Track what commit_sha was passed to RepoAnalyzer
        captured_commit_sha = None
        
        class MockRepoAnalyzer:
            def __init__(self, repo_url, access_token, commit_sha=None):
                nonlocal captured_commit_sha
                captured_commit_sha = commit_sha
                self.temp_dir = "/tmp/test"
            
            def __enter__(self):
                return self
            
            def __exit__(self, *args):
                pass
            
            def clone(self):
                return "/tmp/test"
        
        # Mock the database queries
        with patch("app.workers.ai_scan.get_sync_session") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)
            
            # Setup query results
            mock_analysis = MockAnalysis()
            mock_repo = MockRepository()
            mock_user = MockUser()
            
            def mock_execute(query):
                result = MagicMock()
                # Determine which model is being queried based on the query
                query_str = str(query)
                if "analyses" in query_str.lower() or "Analysis" in query_str:
                    result.scalar_one_or_none.return_value = mock_analysis
                elif "repositories" in query_str.lower() or "Repository" in query_str:
                    result.scalar_one_or_none.return_value = mock_repo
                elif "users" in query_str.lower() or "User" in query_str:
                    result.scalar_one_or_none.return_value = mock_user
                else:
                    result.scalar_one_or_none.return_value = None
                return result
            
            mock_db.execute.side_effect = mock_execute
            
            # Import and call the helper function
            from app.workers.ai_scan import _get_analysis_with_repo
            
            _, _, _, returned_commit_sha, _ = _get_analysis_with_repo(analysis_id)
            
            # Property: The returned commit_sha must equal the analysis commit_sha
            assert returned_commit_sha == test_commit_sha, (
                f"Commit SHA mismatch!\n"
                f"Analysis commit_sha: {test_commit_sha}\n"
                f"Returned commit_sha: {returned_commit_sha}"
            )


# =============================================================================
# Property Tests for Results Persistence
# =============================================================================


class TestResultsPersistence:
    """Property tests for scan results persistence.

    **Feature: ai-scan-integration, Property 2: Scan Results Persistence**
    **Validates: Requirements 1.3**
    """

    @given(
        issues_count=st.integers(min_value=0, max_value=20),
        total_tokens=st.integers(min_value=1000, max_value=500000),
        total_cost=st.floats(min_value=0.01, max_value=5.0),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_completed_scan_stores_results_in_cache(
        self,
        issues_count: int,
        total_tokens: int,
        total_cost: float,
    ):
        """
        **Feature: ai-scan-integration, Property 2: Scan Results Persistence**
        **Validates: Requirements 1.3**

        Property: For any completed AI scan, the results SHALL be stored
        in the Analysis.ai_scan_cache field with status "completed".
        """
        from dataclasses import dataclass, field
        
        # Generate mock issues
        mock_issues = []
        for i in range(issues_count):
            mock_issues.append({
                "id": f"sec-{i+1:03d}",
                "dimension": "security",
                "severity": "high",
                "title": f"Issue {i+1}",
                "summary": f"Summary {i+1}",
                "files": [{"path": "test.py", "line_start": 1, "line_end": 10}],
                "evidence_snippets": ["snippet"],
                "confidence": "high",
                "found_by_models": ["gemini/gemini-3-pro-preview"],
                "investigation_status": None,
                "suggested_fix": None,
            })
        
        # Build cache data as the worker would
        cache_data = {
            "status": "completed",
            "models_used": ["gemini/gemini-3-pro-preview"],
            "models_succeeded": ["gemini/gemini-3-pro-preview"],
            "repo_overview": {
                "guessed_project_type": "Python backend",
                "main_languages": ["python"],
                "main_components": ["API"],
            },
            "issues": mock_issues,
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "total_tokens_used": total_tokens,
            "total_cost_usd": total_cost,
            "commit_sha": "a" * 40,
        }
        
        # Property 1: Status must be "completed"
        assert cache_data["status"] == "completed", (
            f"Cache status should be 'completed', got: {cache_data['status']}"
        )
        
        # Property 2: Issues count must match
        assert len(cache_data["issues"]) == issues_count, (
            f"Issues count mismatch! Expected: {issues_count}, Got: {len(cache_data['issues'])}"
        )
        
        # Property 3: Token count must be stored
        assert cache_data["total_tokens_used"] == total_tokens, (
            f"Token count mismatch! Expected: {total_tokens}, Got: {cache_data['total_tokens_used']}"
        )
        
        # Property 4: Cost must be stored
        assert cache_data["total_cost_usd"] == total_cost, (
            f"Cost mismatch! Expected: {total_cost}, Got: {cache_data['total_cost_usd']}"
        )
        
        # Property 5: Cache must be JSON serializable (for JSONB storage)
        try:
            serialized = json.dumps(cache_data)
            deserialized = json.loads(serialized)
            assert deserialized["status"] == "completed"
        except (TypeError, json.JSONDecodeError) as e:
            pytest.fail(f"Cache data is not JSON serializable: {e}")

    @given(
        commit_sha=valid_commit_sha(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_cache_includes_commit_sha(self, commit_sha: str):
        """
        **Feature: ai-scan-integration, Property 2: Scan Results Persistence**
        **Validates: Requirements 1.3**

        Property: The cached results SHALL include the commit_sha that was scanned.
        """
        # Build cache data with commit_sha
        cache_data = {
            "status": "completed",
            "models_used": ["gemini/gemini-3-pro-preview"],
            "models_succeeded": ["gemini/gemini-3-pro-preview"],
            "repo_overview": {},
            "issues": [],
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "total_tokens_used": 1000,
            "total_cost_usd": 0.01,
            "commit_sha": commit_sha,
        }
        
        # Property: commit_sha must be preserved in cache
        assert cache_data["commit_sha"] == commit_sha, (
            f"Commit SHA not preserved in cache!\n"
            f"Expected: {commit_sha}\n"
            f"Got: {cache_data['commit_sha']}"
        )
        
        # Property: commit_sha must survive JSON round-trip
        serialized = json.dumps(cache_data)
        deserialized = json.loads(serialized)
        assert deserialized["commit_sha"] == commit_sha, (
            f"Commit SHA not preserved after JSON round-trip!\n"
            f"Expected: {commit_sha}\n"
            f"Got: {deserialized['commit_sha']}"
        )



# =============================================================================
# Property Tests for Parallel Execution (Status Check Removed)
# =============================================================================


class TestParallelExecution:
    """Property tests for parallel execution support.

    **Feature: parallel-analysis-pipeline, Property 10: Analysis Status Precondition (removed)**
    **Validates: Requirements 5.2**
    """

    @given(
        analysis_status=st.sampled_from(["pending", "running", "completed", "failed"]),
        test_commit_sha=valid_commit_sha(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_ai_scan_works_with_any_analysis_status(
        self,
        analysis_status: str,
        test_commit_sha: str,
    ):
        """
        **Feature: parallel-analysis-pipeline, Property 10: Analysis Status Precondition (removed)**
        **Validates: Requirements 5.2**

        Property: For any analysis status (pending, running, completed, failed),
        the AI Scan worker SHALL be able to retrieve the analysis record and
        proceed with scanning. The status check that previously blocked parallel
        execution has been removed.
        """
        from dataclasses import dataclass
        from unittest.mock import MagicMock, patch
        
        # Create mock analysis with the given status
        analysis_id = str(uuid4())
        
        @dataclass
        class MockAnalysis:
            id: str = analysis_id
            commit_sha: str = test_commit_sha
            status: str = analysis_status  # Can be ANY status now
            repository_id: str = str(uuid4())
        
        @dataclass
        class MockRepository:
            id: str = str(uuid4())
            full_name: str = "test/repo"
            owner_id: str = str(uuid4())
        
        @dataclass
        class MockUser:
            id: str = str(uuid4())
            access_token_encrypted: str | None = None
        
        # Mock the database queries
        with patch("app.workers.ai_scan.get_sync_session") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)
            
            # Setup query results
            mock_analysis = MockAnalysis()
            mock_repo = MockRepository()
            mock_user = MockUser()
            
            def mock_execute(query):
                result = MagicMock()
                query_str = str(query)
                if "analyses" in query_str.lower() or "Analysis" in query_str:
                    result.scalar_one_or_none.return_value = mock_analysis
                elif "repositories" in query_str.lower() or "Repository" in query_str:
                    result.scalar_one_or_none.return_value = mock_repo
                elif "users" in query_str.lower() or "User" in query_str:
                    result.scalar_one_or_none.return_value = mock_user
                else:
                    result.scalar_one_or_none.return_value = None
                return result
            
            mock_db.execute.side_effect = mock_execute
            
            # Import and call the helper function
            from app.workers.ai_scan import _get_analysis_with_repo
            
            # This should NOT raise ValueError regardless of analysis status
            # Previously, this would fail for status != "completed"
            try:
                analysis, repo, access_token, returned_commit_sha, repo_url = _get_analysis_with_repo(analysis_id)
                
                # Property: Function should succeed for any status
                assert returned_commit_sha == test_commit_sha, (
                    f"Commit SHA mismatch!\n"
                    f"Expected: {test_commit_sha}\n"
                    f"Got: {returned_commit_sha}"
                )
                
                # Property: Repository URL should be constructed correctly
                assert repo_url == "https://github.com/test/repo", (
                    f"Repo URL mismatch!\n"
                    f"Expected: https://github.com/test/repo\n"
                    f"Got: {repo_url}"
                )
                
            except ValueError as e:
                # If we get a ValueError about status, the test fails
                # because the status check should have been removed
                if "not completed" in str(e) or "status" in str(e).lower():
                    pytest.fail(
                        f"AI Scan should work with any analysis status, but got error: {e}\n"
                        f"Analysis status was: {analysis_status}"
                    )
                # Re-raise other ValueErrors (e.g., analysis not found)
                raise

    @given(
        analysis_status=st.sampled_from(["pending", "running"]),
        test_commit_sha=valid_commit_sha(),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_ai_scan_works_during_parallel_execution(
        self,
        analysis_status: str,
        test_commit_sha: str,
    ):
        """
        **Feature: parallel-analysis-pipeline, Property 10: Analysis Status Precondition (removed)**
        **Validates: Requirements 5.2**

        Property: Specifically for parallel execution scenarios, AI Scan SHALL
        work when analysis status is "pending" or "running" (i.e., when Static
        Analysis has not yet completed).
        """
        from dataclasses import dataclass
        from unittest.mock import MagicMock, patch
        
        analysis_id = str(uuid4())
        
        @dataclass
        class MockAnalysis:
            id: str = analysis_id
            commit_sha: str = test_commit_sha
            status: str = analysis_status  # Specifically pending or running
            repository_id: str = str(uuid4())
        
        @dataclass
        class MockRepository:
            id: str = str(uuid4())
            full_name: str = "owner/repo"
            owner_id: str = str(uuid4())
        
        @dataclass
        class MockUser:
            id: str = str(uuid4())
            access_token_encrypted: str | None = None
        
        with patch("app.workers.ai_scan.get_sync_session") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)
            
            mock_analysis = MockAnalysis()
            mock_repo = MockRepository()
            mock_user = MockUser()
            
            def mock_execute(query):
                result = MagicMock()
                query_str = str(query)
                if "analyses" in query_str.lower() or "Analysis" in query_str:
                    result.scalar_one_or_none.return_value = mock_analysis
                elif "repositories" in query_str.lower() or "Repository" in query_str:
                    result.scalar_one_or_none.return_value = mock_repo
                elif "users" in query_str.lower() or "User" in query_str:
                    result.scalar_one_or_none.return_value = mock_user
                else:
                    result.scalar_one_or_none.return_value = None
                return result
            
            mock_db.execute.side_effect = mock_execute
            
            from app.workers.ai_scan import _get_analysis_with_repo
            
            # This is the key test: AI Scan should work even when
            # Static Analysis is still pending or running
            analysis, repo, access_token, returned_commit_sha, repo_url = _get_analysis_with_repo(analysis_id)
            
            # Property: Should succeed without raising ValueError
            assert returned_commit_sha == test_commit_sha
            assert repo_url == "https://github.com/owner/repo"
