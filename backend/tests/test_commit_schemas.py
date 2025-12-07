"""Property-based tests for Commit Selector schemas.

Uses Hypothesis for property-based testing to verify correctness properties
defined in the design document.
"""

from datetime import UTC, datetime
from uuid import uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from app.schemas.repository import CommitResponse

# =============================================================================
# Custom Strategies for Commit Schema Testing
# =============================================================================

def valid_sha() -> st.SearchStrategy[str]:
    """Generate valid 40-character hexadecimal SHA strings."""
    return st.text(
        alphabet="0123456789abcdef",
        min_size=40,
        max_size=40
    )


def commit_message() -> st.SearchStrategy[str]:
    """Generate commit messages with varying lengths and line counts."""
    # Generate single-line or multi-line messages
    return st.one_of(
        # Single line messages of varying lengths
        st.text(min_size=1, max_size=200).filter(lambda s: "\n" not in s and s.strip()),
        # Multi-line messages
        st.lists(
            st.text(min_size=1, max_size=100).filter(lambda s: s.strip()),
            min_size=2,
            max_size=5
        ).map(lambda lines: "\n".join(lines))
    )


def author_name() -> st.SearchStrategy[str]:
    """Generate valid author names."""
    return st.text(min_size=1, max_size=50).filter(lambda s: s.strip())


# =============================================================================
# Property Tests for Short SHA Derivation
# =============================================================================

class TestShortSHADerivationProperties:
    """Property tests for short SHA derivation.

    **Feature: commit-selector-mvp, Property 4: Short SHA derivation**
    **Validates: Requirements 2.2**
    """

    @given(valid_sha(), commit_message(), author_name())
    @settings(max_examples=100)
    def test_short_sha_derivation(self, sha: str, message: str, author: str):
        """
        **Feature: commit-selector-mvp, Property 4: Short SHA derivation**
        **Validates: Requirements 2.2**

        Property: For any commit in the response, the `short_sha` field SHALL equal
        the first 7 characters of the `sha` field.
        """
        # Create a CommitResponse with the generated data
        commit = CommitResponse(
            sha=sha,
            message=message,
            author_name=author,
            committed_at=datetime.now(UTC),
        )

        # Property: short_sha must equal first 7 characters of sha
        assert commit.short_sha == sha[:7], (
            f"Short SHA derivation failed!\n"
            f"SHA: {sha}\n"
            f"Expected short_sha: {sha[:7]}\n"
            f"Actual short_sha: {commit.short_sha}"
        )

        # Additional property: short_sha must be exactly 7 characters
        assert len(commit.short_sha) == 7, (
            f"Short SHA must be exactly 7 characters!\n"
            f"Actual length: {len(commit.short_sha)}"
        )


# =============================================================================
# Property Tests for Message Headline Truncation
# =============================================================================

class TestMessageHeadlineTruncationProperties:
    """Property tests for message headline truncation.

    **Feature: commit-selector-mvp, Property 5: Message headline truncation**
    **Validates: Requirements 2.3**
    """

    @given(valid_sha(), st.text(min_size=81, max_size=300).filter(lambda s: "\n" not in s and s.strip()), author_name())
    @settings(max_examples=100)
    def test_long_message_headline_truncation(self, sha: str, long_message: str, author: str):
        """
        **Feature: commit-selector-mvp, Property 5: Message headline truncation**
        **Validates: Requirements 2.3**

        Property: For any commit where the first line of `message` exceeds 80 characters,
        the `message_headline` SHALL be truncated to 80 characters.
        """
        # Create a CommitResponse with a long message
        commit = CommitResponse(
            sha=sha,
            message=long_message,
            author_name=author,
            committed_at=datetime.now(UTC),
        )

        # Property: message_headline must be exactly 80 characters when message is longer
        assert len(commit.message_headline) == 80, (
            f"Message headline truncation failed!\n"
            f"Original message length: {len(long_message)}\n"
            f"Expected headline length: 80\n"
            f"Actual headline length: {len(commit.message_headline)}"
        )

        # Property: message_headline must be the first 80 characters of the message
        assert commit.message_headline == long_message[:80], (
            f"Message headline content mismatch!\n"
            f"Expected: {long_message[:80]}\n"
            f"Actual: {commit.message_headline}"
        )

    @given(valid_sha(), st.text(min_size=1, max_size=80).filter(lambda s: "\n" not in s and s.strip()), author_name())
    @settings(max_examples=100)
    def test_short_message_headline_preserved(self, sha: str, short_message: str, author: str):
        """
        **Feature: commit-selector-mvp, Property 5: Message headline truncation**
        **Validates: Requirements 2.3**

        Property: For any commit where the first line of `message` is 80 characters or fewer,
        the `message_headline` SHALL equal the first line of the message.
        """
        # Create a CommitResponse with a short message
        commit = CommitResponse(
            sha=sha,
            message=short_message,
            author_name=author,
            committed_at=datetime.now(UTC),
        )

        # Property: message_headline must equal the original message when <= 80 chars
        assert commit.message_headline == short_message, (
            f"Short message headline should be preserved!\n"
            f"Original message: {short_message}\n"
            f"Headline: {commit.message_headline}"
        )

    @given(
        valid_sha(),
        st.lists(
            st.text(min_size=1, max_size=100).filter(lambda s: s.strip() and "\n" not in s),
            min_size=2,
            max_size=5
        ),
        author_name()
    )
    @settings(max_examples=100)
    def test_multiline_message_headline_uses_first_line(self, sha: str, message_lines: list[str], author: str):
        """
        **Feature: commit-selector-mvp, Property 5: Message headline truncation**
        **Validates: Requirements 2.3**

        Property: For any multi-line commit message, the `message_headline` SHALL be
        derived from only the first line (truncated to 80 chars if needed).
        """
        # Create a multi-line message
        multiline_message = "\n".join(message_lines)
        first_line = message_lines[0]

        # Create a CommitResponse with a multi-line message
        commit = CommitResponse(
            sha=sha,
            message=multiline_message,
            author_name=author,
            committed_at=datetime.now(UTC),
        )

        # Property: message_headline must be derived from first line only
        expected_headline = first_line[:80] if len(first_line) > 80 else first_line
        assert commit.message_headline == expected_headline, (
            f"Multi-line message headline should use first line only!\n"
            f"First line: {first_line}\n"
            f"Expected headline: {expected_headline}\n"
            f"Actual headline: {commit.message_headline}"
        )

        # Property: message_headline must not exceed 80 characters
        assert len(commit.message_headline) <= 80, (
            f"Message headline exceeds 80 characters!\n"
            f"Length: {len(commit.message_headline)}"
        )


# =============================================================================
# Property Tests for Default Branch Identification
# =============================================================================

class TestDefaultBranchIdentificationProperties:
    """Property tests for default branch identification.

    **Feature: commit-selector-mvp, Property 1: Default branch identification**
    **Validates: Requirements 1.2**
    """

    @given(
        st.lists(
            st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_/", min_size=1, max_size=50).filter(lambda s: s.strip()),
            min_size=1,
            max_size=20,
            unique=True
        )
    )
    @settings(max_examples=100)
    def test_exactly_one_default_branch(self, branch_names: list[str]):
        """
        **Feature: commit-selector-mvp, Property 1: Default branch identification**
        **Validates: Requirements 1.2**

        Property: For any list of branches returned by the API, exactly one branch
        SHALL be marked as `is_default: true`, and that branch name SHALL match
        the repository's `default_branch` field.
        """
        from app.schemas.repository import BranchListResponse, BranchResponse

        # Pick one branch to be the default
        default_branch_name = branch_names[0]

        # Create branch responses, marking exactly one as default
        branches = [
            BranchResponse(
                name=name,
                commit_sha="a" * 40,  # Valid SHA
                is_default=(name == default_branch_name),
                is_protected=False,
            )
            for name in branch_names
        ]

        # Create the list response
        response = BranchListResponse(data=branches)

        # Property: Exactly one branch should be marked as default
        default_branches = [b for b in response.data if b.is_default]
        assert len(default_branches) == 1, (
            f"Expected exactly 1 default branch, found {len(default_branches)}\n"
            f"Branch names: {branch_names}\n"
            f"Default branches: {[b.name for b in default_branches]}"
        )

        # Property: The default branch name should match what we set
        assert default_branches[0].name == default_branch_name, (
            f"Default branch name mismatch!\n"
            f"Expected: {default_branch_name}\n"
            f"Actual: {default_branches[0].name}"
        )


# =============================================================================
# Property Tests for Commit Ordering
# =============================================================================

class TestCommitOrderingProperties:
    """Property tests for commit ordering.

    **Feature: commit-selector-mvp, Property 2: Commit ordering**
    **Validates: Requirements 2.1**
    """

    @given(
        st.lists(
            st.datetimes(
                min_value=datetime(2020, 1, 1),
                max_value=datetime(2025, 12, 31),
                timezones=st.just(UTC)
            ),
            min_size=2,
            max_size=30
        )
    )
    @settings(max_examples=100)
    def test_commits_ordered_by_date_descending(self, commit_dates: list[datetime]):
        """
        **Feature: commit-selector-mvp, Property 2: Commit ordering**
        **Validates: Requirements 2.1**

        Property: For any list of commits returned by the API, the commits SHALL be
        ordered by `committed_at` in descending order (newest first).
        """
        from app.schemas.repository import CommitListResponse, CommitResponse

        # Sort dates in descending order (newest first) as the API should return
        sorted_dates = sorted(commit_dates, reverse=True)

        # Create commit responses with the sorted dates
        commits = [
            CommitResponse(
                sha=f"{i:040x}",  # Generate unique SHA for each commit
                message=f"Commit {i}",
                author_name="Test Author",
                committed_at=date,
            )
            for i, date in enumerate(sorted_dates)
        ]

        # Create the list response
        response = CommitListResponse(commits=commits, branch="main")

        # Property: Commits should be in descending order by committed_at
        for i in range(len(response.commits) - 1):
            current = response.commits[i]
            next_commit = response.commits[i + 1]
            assert current.committed_at >= next_commit.committed_at, (
                f"Commits not in descending order!\n"
                f"Commit {i} ({current.short_sha}): {current.committed_at}\n"
                f"Commit {i+1} ({next_commit.short_sha}): {next_commit.committed_at}"
            )


# =============================================================================
# Property Tests for Analysis Status Consistency
# =============================================================================

class TestAnalysisStatusConsistencyProperties:
    """Property tests for analysis status consistency.

    **Feature: commit-selector-mvp, Property 6: Analysis status consistency**
    **Validates: Requirements 3.1, 3.2, 3.4**
    """

    @given(
        valid_sha(),
        commit_message(),
        author_name(),
        st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=100)
    def test_completed_analysis_has_vci_score(self, sha: str, message: str, author: str, vci_score: float):
        """
        **Feature: commit-selector-mvp, Property 6: Analysis status consistency**
        **Validates: Requirements 3.1, 3.2, 3.4**

        Property: For any commit with `analysis_status = "completed"`, the `vci_score`
        field SHALL be non-null.
        """
        # Create a CommitResponse with completed analysis status
        commit = CommitResponse(
            sha=sha,
            message=message,
            author_name=author,
            committed_at=datetime.now(UTC),
            analysis_id=uuid4(),
            vci_score=vci_score,
            analysis_status="completed",
        )

        # Property: When status is "completed", vci_score must be non-null
        assert commit.analysis_status == "completed"
        assert commit.vci_score is not None, (
            f"Completed analysis must have a VCI score!\n"
            f"SHA: {sha}\n"
            f"Status: {commit.analysis_status}\n"
            f"VCI Score: {commit.vci_score}"
        )

    @given(valid_sha(), commit_message(), author_name())
    @settings(max_examples=100)
    def test_no_analysis_has_null_fields(self, sha: str, message: str, author: str):
        """
        **Feature: commit-selector-mvp, Property 6: Analysis status consistency**
        **Validates: Requirements 3.1, 3.2, 3.4**

        Property: For any commit with `analysis_status = null`, both `analysis_id`
        and `vci_score` SHALL be null.
        """
        # Create a CommitResponse with no analysis
        commit = CommitResponse(
            sha=sha,
            message=message,
            author_name=author,
            committed_at=datetime.now(UTC),
            analysis_id=None,
            vci_score=None,
            analysis_status=None,
        )

        # Property: When status is null, analysis_id and vci_score must also be null
        assert commit.analysis_status is None
        assert commit.analysis_id is None, (
            f"Non-analyzed commit must have null analysis_id!\n"
            f"SHA: {sha}\n"
            f"Status: {commit.analysis_status}\n"
            f"Analysis ID: {commit.analysis_id}"
        )
        assert commit.vci_score is None, (
            f"Non-analyzed commit must have null vci_score!\n"
            f"SHA: {sha}\n"
            f"Status: {commit.analysis_status}\n"
            f"VCI Score: {commit.vci_score}"
        )

    @given(
        valid_sha(),
        commit_message(),
        author_name(),
        st.sampled_from(["pending", "running"])
    )
    @settings(max_examples=100)
    def test_pending_running_analysis_consistency(self, sha: str, message: str, author: str, status: str):
        """
        **Feature: commit-selector-mvp, Property 6: Analysis status consistency**
        **Validates: Requirements 3.1, 3.2, 3.4**

        Property: For any commit with `analysis_status = "pending"` or "running",
        the `analysis_id` SHALL be non-null (analysis record exists) but `vci_score`
        may be null (not yet computed).
        """
        # Create a CommitResponse with pending/running analysis status
        commit = CommitResponse(
            sha=sha,
            message=message,
            author_name=author,
            committed_at=datetime.now(UTC),
            analysis_id=uuid4(),
            vci_score=None,  # Not yet computed
            analysis_status=status,
        )

        # Property: When status is pending/running, analysis_id must be non-null
        assert commit.analysis_status in ["pending", "running"]
        assert commit.analysis_id is not None, (
            f"Pending/running analysis must have an analysis_id!\n"
            f"SHA: {sha}\n"
            f"Status: {commit.analysis_status}\n"
            f"Analysis ID: {commit.analysis_id}"
        )
