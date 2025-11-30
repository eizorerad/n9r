"""Lizard-based polyglot code complexity analyzer.

This module provides multi-language complexity analysis using the lizard tool,
supporting JavaScript, TypeScript, Java, Go, C/C++, Ruby, PHP, and more.
"""

import csv
import io
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class LizardFunctionMetrics:
    """Metrics for a single function analyzed by lizard."""
    name: str
    file: str
    line: int
    complexity: int
    nloc: int  # Lines of code
    parameters: int
    rank: str  # A-F grade


@dataclass
class LizardAnalysisResult:
    """Complete analysis result from lizard."""
    functions_analyzed: int = 0
    avg_complexity: float = 0.0
    max_complexity: int = 0
    high_complexity_count: int = 0
    complexity_distribution: dict[str, int] = field(default_factory=lambda: {
        "A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "F": 0
    })
    top_complex_functions: list[dict[str, Any]] = field(default_factory=list)
    total_nloc: int = 0
    languages_analyzed: list[str] = field(default_factory=list)
    by_language: dict[str, dict[str, Any]] = field(default_factory=dict)


class LizardAnalyzer:
    """Polyglot complexity analyzer using lizard.

    Supports 20+ languages including JavaScript, TypeScript, Java, Go, C/C++,
    Ruby, PHP, and more. Used alongside radon for comprehensive multi-language
    analysis in monorepos.
    """

    SUPPORTED_EXTENSIONS: dict[str, str] = {
        '.js': 'javascript',
        '.jsx': 'javascript',
        '.ts': 'typescript',
        '.tsx': 'typescript',
        '.java': 'java',
        '.go': 'go',
        '.c': 'c',
        '.cpp': 'cpp',
        '.cc': 'cpp',
        '.cxx': 'cpp',
        '.h': 'c',
        '.hpp': 'cpp',
        '.rb': 'ruby',
        '.php': 'php',
        '.swift': 'swift',
        '.kt': 'kotlin',
        '.scala': 'scala',
        '.rs': 'rust',
        '.lua': 'lua',
        '.m': 'objectivec',
        '.mm': 'objectivec',
    }

    # Directories to exclude from analysis
    EXCLUDE_DIRS = [
        "node_modules/*",
        "dist/*",
        "build/*",
        ".git/*",
        "__pycache__/*",
        "vendor/*",
        ".venv/*",
        "venv/*",
        "coverage/*",
        ".next/*",
    ]

    def __init__(self, timeout: int = 120):
        """Initialize the analyzer.

        Args:
            timeout: Maximum seconds to wait for lizard subprocess.
        """
        self.timeout = timeout

    def analyze(
        self,
        repo_path: Path,
        exclude_python: bool = True
    ) -> LizardAnalysisResult:
        """Run lizard analysis on repository.

        Args:
            repo_path: Path to the repository to analyze.
            exclude_python: If True, skip .py files (use radon for Python).

        Returns:
            LizardAnalysisResult with complexity metrics.
        """
        result = LizardAnalysisResult()

        try:
            raw_data = self._run_lizard(repo_path, exclude_python)

            if not raw_data:
                logger.warning("Lizard returned no data")
                return result

            # Process the lizard output
            all_functions: list[LizardFunctionMetrics] = []
            total_complexity = 0
            language_stats: dict[str, dict[str, int]] = {}

            for file_data in raw_data:
                filename = file_data.get("filename", "")

                # Get relative path
                try:
                    rel_path = str(Path(filename).relative_to(repo_path))
                except ValueError:
                    rel_path = filename

                # Determine language from extension
                ext = Path(filename).suffix.lower()
                language = self.SUPPORTED_EXTENSIONS.get(ext, "unknown")

                # Skip Python if requested
                if exclude_python and ext == ".py":
                    continue

                # Initialize language stats if needed
                if language not in language_stats:
                    language_stats[language] = {
                        "files": 0,
                        "lines": 0,
                        "functions": 0,
                        "total_complexity": 0,
                    }

                language_stats[language]["files"] += 1
                file_nloc = 0

                # Process functions in this file
                for func in file_data.get("function_list", []):
                    cc = func.get("cyclomatic_complexity", 1)
                    nloc = func.get("nloc", 0)
                    name = func.get("name", "unknown")
                    line = func.get("start_line", 0)
                    params = func.get("parameter_count", 0)

                    rank = self._calculate_rank(cc)

                    func_metrics = LizardFunctionMetrics(
                        name=name,
                        file=rel_path,
                        line=line,
                        complexity=cc,
                        nloc=nloc,
                        parameters=params,
                        rank=rank,
                    )
                    all_functions.append(func_metrics)

                    # Update totals
                    total_complexity += cc
                    file_nloc += nloc
                    result.total_nloc += nloc

                    # Update distribution
                    if rank in result.complexity_distribution:
                        result.complexity_distribution[rank] += 1

                    # Track max complexity
                    if cc > result.max_complexity:
                        result.max_complexity = cc

                    # Count high complexity functions (CC > 10)
                    if cc > 10:
                        result.high_complexity_count += 1

                    # Update language stats
                    language_stats[language]["functions"] += 1
                    language_stats[language]["total_complexity"] += cc

                language_stats[language]["lines"] += file_nloc

            # Calculate averages and finalize results
            result.functions_analyzed = len(all_functions)

            if result.functions_analyzed > 0:
                result.avg_complexity = total_complexity / result.functions_analyzed

            # Sort and get top 10 most complex functions
            all_functions.sort(key=lambda f: f.complexity, reverse=True)
            result.top_complex_functions = [
                {
                    "name": f.name,
                    "file": f.file,
                    "line": f.line,
                    "complexity": f.complexity,
                    "rank": f.rank,
                }
                for f in all_functions[:10]
            ]

            # Build by_language breakdown
            result.languages_analyzed = list(language_stats.keys())
            for lang, stats in language_stats.items():
                if stats["files"] > 0:
                    avg_cc = (
                        stats["total_complexity"] / stats["functions"]
                        if stats["functions"] > 0
                        else 0.0
                    )
                    result.by_language[lang] = {
                        "files": stats["files"],
                        "lines": stats["lines"],
                        "functions": stats["functions"],
                        "avg_complexity": round(avg_cc, 2),
                    }

            logger.info(
                f"Lizard analyzed {result.functions_analyzed} functions "
                f"across {len(result.languages_analyzed)} languages, "
                f"avg CC: {result.avg_complexity:.2f}"
            )

        except FileNotFoundError:
            logger.warning("lizard not installed, skipping multi-language analysis")
        except subprocess.TimeoutExpired:
            logger.warning(f"Lizard analysis timed out after {self.timeout}s")
        except Exception as e:
            logger.error(f"Error in lizard analysis: {e}")

        return result

    def _run_lizard(
        self,
        repo_path: Path,
        exclude_python: bool = True
    ) -> list[dict[str, Any]]:
        """Execute lizard CLI and parse CSV output.

        Args:
            repo_path: Path to analyze.
            exclude_python: If True, exclude .py files from analysis.

        Returns:
            List of file data dictionaries with function_list for each file.

        Raises:
            FileNotFoundError: If lizard is not installed.
            subprocess.TimeoutExpired: If analysis exceeds timeout.
        """
        cmd = ["lizard", "--csv"]

        # Add exclude patterns
        for pattern in self.EXCLUDE_DIRS:
            cmd.extend(["--exclude", pattern])

        # Exclude Python files if requested (radon handles Python)
        if exclude_python:
            cmd.extend(["--exclude", "*.py"])

        # Add the path to analyze
        cmd.append(str(repo_path))

        logger.debug(f"Running lizard command: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )

        if result.returncode != 0:
            logger.warning(f"Lizard returned non-zero exit code: {result.returncode}")
            logger.debug(f"Lizard stderr: {result.stderr}")

        if not result.stdout:
            return []

        return self._parse_csv_output(result.stdout)

    def _parse_csv_output(self, csv_output: str) -> list[dict[str, Any]]:
        """Parse lizard CSV output into file-based structure.

        CSV format (columns):
        0: NLOC (lines of code)
        1: CCN (cyclomatic complexity)
        2: Token count
        3: Parameter count
        4: Length (lines)
        5: Long name (function@line-endline@file)
        6: Filename
        7: Function name
        8: Short name
        9: Start line
        10: End line

        Args:
            csv_output: Raw CSV output from lizard.

        Returns:
            List of file dictionaries with function_list for each file.
        """
        files_dict: dict[str, dict[str, Any]] = {}

        try:
            reader = csv.reader(io.StringIO(csv_output))
            for row in reader:
                if len(row) < 10:
                    continue

                try:
                    nloc = int(row[0])
                    ccn = int(row[1])
                    params = int(row[3])
                    filename = row[6]
                    func_name = row[7]
                    start_line = int(row[9])
                except (ValueError, IndexError) as e:
                    logger.debug(f"Skipping malformed CSV row: {e}")
                    continue

                # Initialize file entry if needed
                if filename not in files_dict:
                    files_dict[filename] = {
                        "filename": filename,
                        "function_list": [],
                    }

                # Add function to file
                files_dict[filename]["function_list"].append({
                    "name": func_name,
                    "nloc": nloc,
                    "cyclomatic_complexity": ccn,
                    "parameter_count": params,
                    "start_line": start_line,
                })

        except Exception as e:
            logger.error(f"Failed to parse lizard CSV output: {e}")
            return []

        return list(files_dict.values())

    @staticmethod
    def _calculate_rank(complexity: int) -> str:
        """Convert cyclomatic complexity to A-F grade.

        Grade mapping:
        - A: 1-5 (Simple, low risk)
        - B: 6-10 (Low complexity)
        - C: 11-20 (Moderate complexity)
        - D: 21-30 (High complexity)
        - E: 31-40 (Very high complexity)
        - F: 41+ (Untestable)

        Args:
            complexity: Cyclomatic complexity value.

        Returns:
            Grade letter A-F.
        """
        if complexity <= 5:
            return "A"
        elif complexity <= 10:
            return "B"
        elif complexity <= 20:
            return "C"
        elif complexity <= 30:
            return "D"
        elif complexity <= 40:
            return "E"
        else:
            return "F"

    def is_available(self) -> bool:
        """Check if lizard is installed and available.

        Returns:
            True if lizard can be executed, False otherwise.
        """
        try:
            result = subprocess.run(
                ["lizard", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
