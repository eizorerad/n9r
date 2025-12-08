"""Git Analyzer for Code Churn Analysis.

Analyzes git history to identify high-risk files based on code churn metrics.
Produces HotSpotFinding objects with natural language risk factors.

Requirements: 2.1, 2.2, 2.3, 2.4
"""

import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.schemas.architecture_llm import HotSpotFinding

logger = logging.getLogger(__name__)


@dataclass
class FileChurn:
    """Churn metrics for a single file.

    Attributes:
        file_path: Path to the file relative to repo root
        changes_30d: Number of commits in last 30 days
        changes_90d: Number of commits in last 90 days
        lines_added_90d: Total lines added in last 90 days
        lines_removed_90d: Total lines removed in last 90 days
        unique_authors: Number of unique authors in last 90 days
        last_modified: Timestamp of most recent change
    """

    file_path: str
    changes_30d: int = 0
    changes_90d: int = 0
    lines_added_90d: int = 0
    lines_removed_90d: int = 0
    unique_authors: int = 0
    last_modified: datetime | None = None


class GitAnalyzer:
    """Analyzes git history for code churn metrics.

    Parses git log output to calculate per-file churn metrics including
    commit counts, line changes, and unique authors.

    Requirements: 2.1, 2.2
    """

    def __init__(self) -> None:
        pass

    def analyze(self, repo_path: Path, days: int = 90) -> dict[str, FileChurn]:
        """Analyze git history for code churn.

        Parses git log for the specified number of days and calculates
        per-file churn metrics.

        Args:
            repo_path: Path to the repository root
            days: Number of days to analyze (default 90)

        Returns:
            Dictionary mapping file paths to FileChurn objects
        """
        churn_data: dict[str, FileChurn] = {}

        # Check if repo_path is a git repository
        if not (repo_path / ".git").exists():
            logger.warning(f"Not a git repository: {repo_path}")
            return churn_data

        try:
            # Get git log with numstat format for the last N days
            since_date = datetime.now(timezone.utc) - timedelta(days=days)
            since_str = since_date.strftime("%Y-%m-%d")

            # Parse 90-day data
            churn_data = self._parse_git_log(repo_path, since_str, days)

            # Also calculate 30-day metrics
            since_30d = datetime.now(timezone.utc) - timedelta(days=30)
            since_30d_str = since_30d.strftime("%Y-%m-%d")
            churn_30d = self._parse_git_log(repo_path, since_30d_str, 30)

            # Merge 30-day counts into main data
            for file_path, churn in churn_30d.items():
                if file_path in churn_data:
                    churn_data[file_path].changes_30d = churn.changes_90d

            logger.info(f"Analyzed git history: {len(churn_data)} files with changes")

        except subprocess.CalledProcessError as e:
            logger.error(f"Git command failed: {e}")
        except Exception as e:
            logger.error(f"Failed to analyze git history: {e}")

        return churn_data

    def _parse_git_log(
        self, repo_path: Path, since_date: str, days: int
    ) -> dict[str, FileChurn]:
        """Parse git log output with numstat format.

        Args:
            repo_path: Path to the repository root
            since_date: Date string in YYYY-MM-DD format
            days: Number of days being analyzed (for field naming)

        Returns:
            Dictionary mapping file paths to FileChurn objects
        """
        churn_data: dict[str, FileChurn] = {}

        # Run git log with numstat format
        # Format: commit_hash\nauthor\ndate\n\nlines_added\tlines_removed\tfile_path\n...
        cmd = [
            "git",
            "log",
            f"--since={since_date}",
            "--numstat",
            "--format=%H%n%an%n%aI",
            "--no-merges",
        ]

        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )

        # Parse the output
        lines = result.stdout.strip().split("\n")
        current_author: str | None = None
        current_date: datetime | None = None
        file_authors: dict[str, set[str]] = {}

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Skip empty lines
            if not line:
                i += 1
                continue

            # Check if this is a commit hash (40 hex chars)
            if len(line) == 40 and all(c in "0123456789abcdef" for c in line):
                # Next line is author, then date
                if i + 2 < len(lines):
                    current_author = lines[i + 1].strip()
                    try:
                        date_str = lines[i + 2].strip()
                        current_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    except ValueError:
                        current_date = None
                    i += 3
                    continue
                else:
                    i += 1
                    continue

            # Check if this is a numstat line (lines_added\tlines_removed\tfile_path)
            parts = line.split("\t")
            if len(parts) == 3:
                added_str, removed_str, file_path = parts

                # Skip binary files (shown as - - filename)
                if added_str == "-" or removed_str == "-":
                    i += 1
                    continue

                try:
                    lines_added = int(added_str)
                    lines_removed = int(removed_str)
                except ValueError:
                    i += 1
                    continue

                # Initialize or update file churn
                if file_path not in churn_data:
                    churn_data[file_path] = FileChurn(file_path=file_path)
                    file_authors[file_path] = set()

                churn = churn_data[file_path]
                churn.changes_90d += 1
                churn.lines_added_90d += lines_added
                churn.lines_removed_90d += lines_removed

                # Track authors
                if current_author:
                    file_authors[file_path].add(current_author)

                # Update last modified
                if current_date:
                    if churn.last_modified is None or current_date > churn.last_modified:
                        churn.last_modified = current_date

            i += 1

        # Set unique author counts
        for file_path, authors in file_authors.items():
            if file_path in churn_data:
                churn_data[file_path].unique_authors = len(authors)

        return churn_data

    def to_hot_spot_findings(
        self,
        churn_data: dict[str, FileChurn],
        coverage_data: dict[str, float] | None = None,
        threshold: int = 10,
    ) -> list[HotSpotFinding]:
        """Convert high-churn files to HotSpotFinding objects.

        Filters files with changes_90d > threshold and generates
        natural language risk factors and suggested actions.

        Args:
            churn_data: Dictionary of file paths to FileChurn objects
            coverage_data: Optional dictionary of file paths to coverage rates (0.0-1.0)
            threshold: Minimum changes in 90 days to be considered a hot spot (default 10)

        Returns:
            List of HotSpotFinding objects for high-churn files

        Requirements: 2.3, 2.4
        """
        findings: list[HotSpotFinding] = []

        for file_path, churn in churn_data.items():
            # Filter by threshold
            if churn.changes_90d <= threshold:
                continue

            # Get coverage rate if available
            coverage_rate: float | None = None
            if coverage_data and file_path in coverage_data:
                coverage_rate = coverage_data[file_path]

            # Generate risk factors
            risk_factors = self._generate_risk_factors(churn, coverage_rate)

            # Generate suggested action
            suggested_action = self._generate_suggested_action(churn, coverage_rate)

            finding = HotSpotFinding(
                file_path=file_path,
                churn_count=churn.changes_90d,
                coverage_rate=coverage_rate,
                unique_authors=churn.unique_authors,
                risk_factors=risk_factors,
                suggested_action=suggested_action,
            )
            findings.append(finding)

        # Sort by churn count descending
        findings.sort(key=lambda f: f.churn_count, reverse=True)

        return findings

    def _generate_risk_factors(
        self, churn: FileChurn, coverage_rate: float | None
    ) -> list[str]:
        """Generate natural language risk factors for a file.

        Args:
            churn: FileChurn metrics for the file
            coverage_rate: Optional coverage rate (0.0-1.0)

        Returns:
            List of human-readable risk factor strings

        Requirements: 2.4
        """
        risk_factors: list[str] = []

        # High churn factor
        if churn.changes_90d > 30:
            risk_factors.append(
                f"Very high churn: {churn.changes_90d} changes in 90 days"
            )
        elif churn.changes_90d > 10:
            risk_factors.append(
                f"High churn: {churn.changes_90d} changes in 90 days"
            )

        # Multiple authors factor
        if churn.unique_authors > 5:
            risk_factors.append(
                f"Many contributors: {churn.unique_authors} unique authors"
            )
        elif churn.unique_authors > 2:
            risk_factors.append(
                f"Multiple contributors: {churn.unique_authors} unique authors"
            )

        # High line churn factor
        total_lines_changed = churn.lines_added_90d + churn.lines_removed_90d
        if total_lines_changed > 500:
            risk_factors.append(
                f"Significant code changes: {total_lines_changed} lines modified"
            )

        # Low coverage factor
        if coverage_rate is not None:
            if coverage_rate < 0.2:
                risk_factors.append(
                    f"Very low test coverage: {coverage_rate * 100:.0f}%"
                )
            elif coverage_rate < 0.5:
                risk_factors.append(
                    f"Low test coverage: {coverage_rate * 100:.0f}%"
                )
        else:
            risk_factors.append("Coverage data unavailable")

        return risk_factors

    def _generate_suggested_action(
        self, churn: FileChurn, coverage_rate: float | None
    ) -> str:
        """Generate a suggested action for a hot spot file.

        Args:
            churn: FileChurn metrics for the file
            coverage_rate: Optional coverage rate (0.0-1.0)

        Returns:
            Human-readable suggested action string
        """
        actions: list[str] = []

        # Coverage-based suggestion
        if coverage_rate is not None and coverage_rate < 0.5:
            actions.append("Add tests before next modification")
        elif coverage_rate is None:
            actions.append("Consider adding test coverage")

        # Churn-based suggestion
        if churn.changes_90d > 30:
            actions.append("Review for potential refactoring opportunities")
        elif churn.unique_authors > 3:
            actions.append("Ensure code review coverage for changes")

        if actions:
            return ". ".join(actions) + "."
        else:
            return "Monitor for continued high change frequency."
