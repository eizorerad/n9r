"""Repository analyzer service - real analysis implementation."""

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from app.services.ast_analyzer import get_ast_analyzer
from app.services.lizard_analyzer import LizardAnalyzer

logger = logging.getLogger(__name__)

# Hard Heuristics Constants
MAX_FUNCTION_LINES = 50
MAX_FILE_LINES = 300
MAX_CYCLOMATIC_COMPLEXITY = 10
MIN_COMMENT_RATIO = 0.05  # 5%
# Note: GENERIC_NAMES moved to ast_analyzer.py for AST-based detection
# Keeping regex pattern as fallback for non-Python/JS files
MAGIC_NUMBER_PATTERN = re.compile(r'\b(?!0|1|2|100|1000)\d{2,}\b')


@dataclass
class AnalysisMetrics:
    """Analysis metrics result."""
    total_files: int = 0
    total_lines: int = 0
    total_comments: int = 0
    python_files: int = 0
    python_lines: int = 0
    js_ts_files: int = 0
    js_ts_lines: int = 0

    # Complexity metrics
    avg_complexity: float = 0.0
    max_complexity: float = 0.0
    high_complexity_functions: int = 0

    # Hard Heuristics metrics
    long_functions: int = 0  # Functions > 50 lines
    long_files: int = 0  # Files > 300 lines
    generic_names: int = 0  # Generic variable names
    magic_numbers: int = 0  # Hardcoded numbers
    missing_docstrings: int = 0
    missing_type_hints: int = 0
    todo_comments: int = 0

    # Calculated scores
    complexity_score: float = 100.0
    maintainability_score: float = 100.0
    duplication_score: float = 100.0
    architecture_score: float = 100.0
    heuristics_score: float = 100.0


@dataclass
class AnalysisResult:
    """Complete analysis result."""
    vci_score: float
    tech_debt_level: str  # 'low', 'medium', 'high'
    metrics: dict
    ai_report: str
    issues: list


class RepoAnalyzer:
    """Analyzes repositories for code quality metrics."""

    def __init__(
        self, 
        repo_url: str, 
        access_token: str | None = None, 
        commit_sha: str | None = None,
        heartbeat_callback: Callable[[], None] | None = None,
    ):
        """Initialize the repository analyzer.
        
        Args:
            repo_url: URL of the repository to analyze
            access_token: Optional access token for private repositories
            commit_sha: Optional specific commit SHA to analyze
            heartbeat_callback: Optional callback function to call during long operations
                               to indicate the worker is still alive. The callback should
                               implement its own throttling to avoid excessive calls.
        """
        self.repo_url = repo_url
        self.access_token = access_token
        self.commit_sha = commit_sha  # Specific commit to analyze
        self.temp_dir: Path | None = None
        self.heartbeat_callback = heartbeat_callback
    
    def _send_heartbeat(self) -> None:
        """Send a heartbeat if callback is configured.
        
        This method should be called during long operations to indicate
        the worker is still alive. The callback handles throttling internally.
        """
        if self.heartbeat_callback:
            try:
                self.heartbeat_callback()
            except Exception as e:
                # Heartbeat failures should not crash the analysis
                logger.debug(f"Heartbeat callback failed: {e}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()

    def cleanup(self):
        """Remove temporary directory."""
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            logger.info(f"Cleaned up temp dir: {self.temp_dir}")

    def clone(self) -> Path:
        """Clone repository to temporary directory.

        Uses SANDBOX_ROOT_DIR from settings for consistency with Sandbox,
        though RepoAnalyzer doesn't require path translation (no sibling containers).

        If commit_sha is specified, clones full history and checks out that commit.
        Otherwise, does a shallow clone of HEAD for speed.
        """
        from app.services.sandbox import get_sandbox_base_dir

        base_dir = get_sandbox_base_dir()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="n9r_analysis_", dir=base_dir))

        # Build clone URL with token if provided
        clone_url = self.repo_url
        if self.access_token and "github.com" in self.repo_url:
            # Insert token for private repos
            clone_url = self.repo_url.replace(
                "https://github.com",
                f"https://x-access-token:{self.access_token}@github.com"
            )

        logger.info(f"Cloning repository to {self.temp_dir}")

        try:
            # If specific commit requested, need full clone (or at least enough depth)
            # Otherwise shallow clone for speed
            if self.commit_sha and self.commit_sha != "HEAD":
                # Clone with enough history to reach the commit
                # Using --depth 100 as a balance between speed and history
                result = subprocess.run(
                    ["git", "clone", "--depth", "100", clone_url, str(self.temp_dir)],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                
                # Send heartbeat after clone completes (can take a while for large repos)
                self._send_heartbeat()

                if result.returncode != 0:
                    logger.error(f"Git clone failed: {result.stderr}")
                    raise RuntimeError(f"Failed to clone repository: {result.stderr}")

                # Try to checkout the specific commit
                checkout_result = subprocess.run(
                    ["git", "checkout", self.commit_sha],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    cwd=str(self.temp_dir),
                )

                if checkout_result.returncode != 0:
                    # If commit not in shallow history, fetch more
                    logger.warning(f"Commit {self.commit_sha} not in shallow clone, fetching full history...")
                    subprocess.run(
                        ["git", "fetch", "--unshallow"],
                        capture_output=True,
                        text=True,
                        timeout=600,
                        cwd=str(self.temp_dir),
                    )
                    
                    # Send heartbeat after unshallow fetch (can be very slow)
                    self._send_heartbeat()

                    # Try checkout again
                    checkout_result = subprocess.run(
                        ["git", "checkout", self.commit_sha],
                        capture_output=True,
                        text=True,
                        timeout=60,
                        cwd=str(self.temp_dir),
                    )

                    if checkout_result.returncode != 0:
                        logger.error(f"Git checkout failed: {checkout_result.stderr}")
                        raise RuntimeError(f"Failed to checkout commit {self.commit_sha}: {checkout_result.stderr}")

                logger.info(f"Successfully cloned and checked out commit {self.commit_sha[:7]}")
            else:
                # Shallow clone for HEAD (fast)
                result = subprocess.run(
                    ["git", "clone", "--depth", "1", clone_url, str(self.temp_dir)],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                
                # Send heartbeat after clone completes
                self._send_heartbeat()

                if result.returncode != 0:
                    logger.error(f"Git clone failed: {result.stderr}")
                    raise RuntimeError(f"Failed to clone repository: {result.stderr}")

                logger.info("Successfully cloned repository (HEAD)")

            return self.temp_dir

        except subprocess.TimeoutExpired:
            logger.error("Git clone timed out")
            raise RuntimeError("Repository clone timed out")

    def count_lines(self) -> AnalysisMetrics:
        """Count lines of code by language."""
        metrics = AnalysisMetrics()

        if not self.temp_dir:
            return metrics

        # File extensions to analyze
        python_exts = {".py"}
        js_ts_exts = {".js", ".jsx", ".ts", ".tsx"}
        all_code_exts = python_exts | js_ts_exts | {".java", ".go", ".rs", ".rb", ".php"}

        for root, dirs, files in os.walk(self.temp_dir):
            # Skip hidden dirs and node_modules
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'node_modules' and d != 'vendor' and d != '__pycache__']

            for file in files:
                filepath = Path(root) / file
                ext = filepath.suffix.lower()

                if ext not in all_code_exts:
                    continue

                try:
                    with open(filepath, encoding='utf-8', errors='ignore') as f:
                        lines = len(f.readlines())

                    metrics.total_files += 1
                    metrics.total_lines += lines

                    if lines > 300:
                        metrics.long_files += 1

                    if ext in python_exts:
                        metrics.python_files += 1
                        metrics.python_lines += lines
                    elif ext in js_ts_exts:
                        metrics.js_ts_files += 1
                        metrics.js_ts_lines += lines

                except Exception as e:
                    logger.debug(f"Error reading {filepath}: {e}")

        logger.info(f"Counted {metrics.total_files} files, {metrics.total_lines} lines")
        return metrics

    def _detect_languages(self) -> set[str]:
        """Detect which programming languages are present in the repository.

        Scans the repository for file extensions and returns a set of detected
        language names. Used to determine which analyzers to run.

        Returns:
            Set of language names (e.g., {'python', 'javascript', 'typescript'})
        """
        if not self.temp_dir:
            return set()

        # Extension to language mapping
        extension_map = {
            '.py': 'python',
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
        }

        detected_languages: set[str] = set()

        for _root, dirs, files in os.walk(self.temp_dir):
            # Skip hidden dirs and common non-source directories
            dirs[:] = [
                d for d in dirs
                if not d.startswith('.')
                and d not in ('node_modules', 'vendor', '__pycache__', 'dist', 'build', '.venv', 'venv')
            ]

            for file in files:
                ext = Path(file).suffix.lower()
                if ext in extension_map:
                    detected_languages.add(extension_map[ext])

        logger.info(f"Detected languages: {detected_languages}")
        return detected_languages

    def analyze_with_lizard(self) -> tuple[dict, bool]:
        """Analyze non-Python files using lizard for complexity metrics.

        Calls LizardAnalyzer for JavaScript, TypeScript, and other supported
        languages. Returns metrics in a format compatible with the existing
        complexity data structure.

        Returns:
            Tuple of (results dict, success bool). Success is True if lizard
            ran successfully and returned data, False if lizard failed
            (not installed, timeout, or critical error).
        """
        if not self.temp_dir:
            return {}, False

        try:
            analyzer = LizardAnalyzer(timeout=120)

            # Check if lizard is available
            if not analyzer.is_available():
                logger.error("lizard not installed - multi-language analysis failed. Continuing with radon results if available.")
                return {}, False

            # Run lizard analysis (excluding Python - radon handles that)
            result = analyzer.analyze(self.temp_dir, exclude_python=True)
            
            # Send heartbeat after lizard analysis completes
            self._send_heartbeat()

            # Check if we got any meaningful results
            if result.functions_analyzed == 0 and not result.languages_analyzed:
                # No non-Python files found - this is not a failure, just no data
                logger.info("No non-Python files found for lizard analysis")
                return {}, True  # Success but empty - no files to analyze

            # Convert LizardAnalysisResult to dict format compatible with existing structure
            return {
                "functions_analyzed": result.functions_analyzed,
                "avg_complexity": result.avg_complexity,
                "max_complexity": result.max_complexity,
                "high_complexity_count": result.high_complexity_count,
                "complexity_distribution": result.complexity_distribution,
                "top_complex_functions": result.top_complex_functions,
                "total_nloc": result.total_nloc,
                "languages_analyzed": result.languages_analyzed,
                "by_language": result.by_language,
            }, True

        except subprocess.TimeoutExpired:
            logger.error("lizard analysis timed out after 120s. Continuing with radon results if available.")
            return {}, False
        except FileNotFoundError:
            logger.error("lizard not found - multi-language analysis failed. Continuing with radon results if available.")
            return {}, False
        except Exception as e:
            logger.error(f"Critical error in lizard analysis: {e}. Continuing with radon results if available.")
            return {}, False

    def _merge_complexity_results(
        self,
        python_data: dict,
        lizard_data: dict,
        python_metrics: Optional['AnalysisMetrics'] = None
    ) -> dict:
        """Merge complexity results from radon (Python) and lizard (other languages).

        Combines metrics from both analyzers into a unified result:
        - Sums complexity_distribution counts for each grade (A-F)
        - Calculates weighted average complexity based on function count
        - Combines and sorts top_complex_functions by complexity
        - Builds by_language breakdown

        Args:
            python_data: Complexity data from radon (Python analysis)
            lizard_data: Complexity data from lizard (JS/TS/other analysis)
            python_metrics: Optional AnalysisMetrics for Python file/line counts

        Returns:
            Merged complexity data dict with all metrics combined
        """
        # Start with empty result structure
        merged = {
            "functions_analyzed": 0,
            "avg_complexity": 0.0,
            "max_complexity": 0,
            "high_complexity_count": 0,
            "complexity_distribution": {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "F": 0},
            "top_complex_functions": [],
            "halstead": python_data.get("halstead", {}),
            "maintainability_index": python_data.get("maintainability_index", {}),
            "raw_metrics": python_data.get("raw_metrics", {}),
            "by_language": {},
        }

        # Get function counts for weighted average
        python_func_count = python_data.get("functions_analyzed", 0)
        lizard_func_count = lizard_data.get("functions_analyzed", 0)
        total_func_count = python_func_count + lizard_func_count

        # Sum complexity distributions
        python_dist = python_data.get("complexity_distribution", {})
        lizard_dist = lizard_data.get("complexity_distribution", {})

        for grade in ["A", "B", "C", "D", "E", "F"]:
            merged["complexity_distribution"][grade] = (
                python_dist.get(grade, 0) + lizard_dist.get(grade, 0)
            )

        # Calculate weighted average complexity
        python_avg = python_data.get("avg_complexity", 0.0)
        lizard_avg = lizard_data.get("avg_complexity", 0.0)

        if total_func_count > 0:
            merged["avg_complexity"] = (
                (python_avg * python_func_count + lizard_avg * lizard_func_count)
                / total_func_count
            )

        # Sum function counts
        merged["functions_analyzed"] = total_func_count

        # Take max of max complexities
        merged["max_complexity"] = max(
            python_data.get("max_complexity", 0),
            lizard_data.get("max_complexity", 0)
        )

        # Sum high complexity counts
        merged["high_complexity_count"] = (
            python_data.get("high_complexity_count", 0) +
            lizard_data.get("high_complexity_count", 0)
        )

        # Combine and sort top_complex_functions
        all_functions = []
        all_functions.extend(python_data.get("top_complex_functions", []))
        all_functions.extend(lizard_data.get("top_complex_functions", []))

        # Sort by complexity descending and take top 10
        all_functions.sort(key=lambda f: f.get("complexity", 0), reverse=True)
        merged["top_complex_functions"] = all_functions[:10]

        # Build by_language breakdown
        by_language = {}

        # Add Python stats if we have Python data
        if python_func_count > 0 and python_metrics:
            by_language["python"] = {
                "files": python_metrics.python_files,
                "lines": python_metrics.python_lines,
                "functions": python_func_count,
                "avg_complexity": round(python_avg, 2),
            }

        # Add lizard language stats
        lizard_by_lang = lizard_data.get("by_language", {})
        for lang, stats in lizard_by_lang.items():
            if stats.get("files", 0) > 0:
                by_language[lang] = stats

        merged["by_language"] = by_language

        logger.info(
            f"Merged complexity: {total_func_count} functions, "
            f"avg CC: {merged['avg_complexity']:.2f}, "
            f"languages: {list(by_language.keys())}"
        )

        return merged

    def _get_fallback_complexity_data(self) -> dict:
        """Return fallback complexity data when both analyzers fail.

        Provides a valid complexity data structure with zero values,
        allowing the analysis to complete with basic file/line counts
        even when complexity analysis is unavailable.

        Returns:
            Dict with zero complexity metrics and empty distributions.
        """
        logger.warning("Using fallback complexity data - all complexity metrics will be zero")
        return {
            "functions_analyzed": 0,
            "avg_complexity": 0.0,
            "max_complexity": 0,
            "high_complexity_count": 0,
            "complexity_distribution": {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "F": 0},
            "top_complex_functions": [],
            "halstead": {
                "total_volume": 0,
                "avg_difficulty": 0,
                "avg_effort": 0,
                "bugs_estimate": 0,
            },
            "maintainability_index": {
                "avg_mi": 0,
                "files_below_65": 0,
                "files_by_grade": {"A": 0, "B": 0, "C": 0},
            },
            "raw_metrics": {
                "loc": 0,
                "lloc": 0,
                "sloc": 0,
                "comments": 0,
                "multi": 0,
                "blank": 0,
            },
            "by_language": {},
            "_warning": "Both analyzers failed - complexity metrics unavailable",
        }

    def analyze_python_complexity(self) -> tuple[dict, bool]:
        """Analyze Python code complexity using radon (CC, Halstead, MI).

        Returns:
            Tuple of (results dict, success bool). Success is True if at least
            the cyclomatic complexity analysis succeeded, False if radon failed
            completely (not installed, timeout, or critical error).
        """
        if not self.temp_dir:
            return {}, False

        results: dict[str, Any] = {
            "functions_analyzed": 0,
            "avg_complexity": 0.0,
            "max_complexity": 0.0,
            "high_complexity_count": 0,
            # Extended metrics
            "complexity_distribution": {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "F": 0},
            "top_complex_functions": [],  # Top 10 most complex
            "halstead": {
                "total_volume": 0,
                "avg_difficulty": 0,
                "avg_effort": 0,
                "bugs_estimate": 0,
            },
            "maintainability_index": {
                "avg_mi": 0,
                "files_below_65": 0,  # MI < 65 = hard to maintain
                "files_by_grade": {"A": 0, "B": 0, "C": 0},
            },
            "raw_metrics": {
                "loc": 0,  # Lines of code
                "lloc": 0,  # Logical lines of code
                "sloc": 0,  # Source lines of code
                "comments": 0,
                "multi": 0,  # Multi-line strings
                "blank": 0,
            },
        }

        cc_success = False

        try:
            # 1. Run radon cc (cyclomatic complexity) with grades
            cc_result = subprocess.run(
                ["radon", "cc", "-a", "-j", str(self.temp_dir)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            
            # Send heartbeat after radon cc completes
            self._send_heartbeat()

            if cc_result.returncode == 0 and cc_result.stdout:
                data = json.loads(cc_result.stdout)

                total_complexity = 0
                function_count = 0
                all_functions = []

                for filepath, functions in data.items():
                    rel_path = filepath.replace(str(self.temp_dir) + "/", "")
                    for func in functions:
                        if isinstance(func, dict) and 'complexity' in func:
                            cc = func['complexity']
                            rank = func.get('rank', 'A')
                            name = func.get('name', 'unknown')
                            lineno = func.get('lineno', 0)

                            total_complexity += cc
                            function_count += 1

                            # Track distribution
                            if rank in results["complexity_distribution"]:
                                results["complexity_distribution"][rank] += 1

                            if cc > results["max_complexity"]:
                                results["max_complexity"] = cc

                            if cc > 10:
                                results["high_complexity_count"] += 1

                            # Store for top complex functions
                            all_functions.append({
                                "name": name,
                                "file": rel_path,
                                "line": lineno,
                                "complexity": cc,
                                "rank": rank,
                            })

                if function_count > 0:
                    results["avg_complexity"] = total_complexity / function_count
                    results["functions_analyzed"] = function_count

                # Get top 10 most complex
                all_functions.sort(key=lambda x: x["complexity"], reverse=True)
                results["top_complex_functions"] = all_functions[:10]

                cc_success = True
                logger.info(f"Analyzed {function_count} Python functions, avg CC: {results['avg_complexity']:.2f}")
            else:
                logger.warning(f"radon cc returned non-zero or empty output: returncode={cc_result.returncode}, stderr={cc_result.stderr}")

        except FileNotFoundError:
            logger.error("radon not installed - Python complexity analysis failed. Continuing with lizard results if available.")
            return results, False
        except subprocess.TimeoutExpired:
            logger.error("Python complexity analysis timed out after 120s. Continuing with lizard results if available.")
            return results, False
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse radon cc JSON output: {e}. Continuing with lizard results if available.")
            return results, False
        except Exception as e:
            logger.error(f"Critical error in radon cc analysis: {e}. Continuing with lizard results if available.")

        # 2. Run radon hal (Halstead metrics)
        try:
            hal_result = subprocess.run(
                ["radon", "hal", "-j", str(self.temp_dir)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            
            # Send heartbeat after radon hal completes
            self._send_heartbeat()

            logger.info(f"Halstead radon returncode={hal_result.returncode}, stdout_len={len(hal_result.stdout or '')}")

            if hal_result.returncode == 0 and hal_result.stdout:
                hal_data = json.loads(hal_result.stdout)

                total_volume = 0
                total_difficulty = 0
                total_effort = 0
                total_bugs = 0
                file_count = 0

                for _filepath, metrics in hal_data.items():
                    if isinstance(metrics, dict) and 'total' in metrics:
                        totals = metrics['total']
                        total_volume += totals.get('volume', 0) or 0
                        total_difficulty += totals.get('difficulty', 0) or 0
                        total_effort += totals.get('effort', 0) or 0
                        total_bugs += totals.get('bugs', 0) or 0
                        file_count += 1

                if file_count > 0:
                    results["halstead"] = {
                        "total_volume": round(total_volume, 2),
                        "avg_difficulty": round(total_difficulty / file_count, 2),
                        "avg_effort": round(total_effort / file_count, 2),
                        "bugs_estimate": round(total_bugs, 2),
                    }

                logger.info(f"Halstead: volume={total_volume:.0f}, difficulty={total_difficulty/max(1,file_count):.1f}, files={file_count}")
            else:
                logger.warning(f"Halstead failed: stderr={hal_result.stderr}")

        except Exception as e:
            logger.warning(f"Halstead analysis error: {e}")

        # 3. Run radon mi (Maintainability Index)
        try:
            mi_result = subprocess.run(
                ["radon", "mi", "-j", str(self.temp_dir)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            
            # Send heartbeat after radon mi completes
            self._send_heartbeat()

            logger.info(f"MI radon returncode={mi_result.returncode}, stdout_len={len(mi_result.stdout or '')}")

            if mi_result.returncode == 0 and mi_result.stdout:
                mi_data = json.loads(mi_result.stdout)

                total_mi = 0
                file_count = 0
                files_below_65 = 0

                for _filepath, mi_info in mi_data.items():
                    if isinstance(mi_info, dict):
                        mi_score = mi_info.get('mi', 0) or 0
                        rank = mi_info.get('rank', 'C')
                    else:
                        mi_score = mi_info if isinstance(mi_info, (int, float)) else 0
                        rank = 'A' if mi_score > 20 else 'B' if mi_score > 10 else 'C'

                    total_mi += mi_score
                    file_count += 1

                    if mi_score < 65:
                        files_below_65 += 1

                    if rank in results["maintainability_index"]["files_by_grade"]:
                        results["maintainability_index"]["files_by_grade"][rank] += 1

                if file_count > 0:
                    results["maintainability_index"]["avg_mi"] = round(total_mi / file_count, 2)
                    results["maintainability_index"]["files_below_65"] = files_below_65

                logger.info(f"MI: avg={total_mi/max(1,file_count):.1f}, low_mi_files={files_below_65}, files={file_count}")
            else:
                logger.warning(f"MI failed: stderr={mi_result.stderr}")

        except Exception as e:
            logger.warning(f"MI analysis error: {e}")

        # 4. Run radon raw (raw metrics)
        try:
            raw_result = subprocess.run(
                ["radon", "raw", "-j", str(self.temp_dir)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            
            # Send heartbeat after radon raw completes
            self._send_heartbeat()

            logger.info(f"Raw radon returncode={raw_result.returncode}, stdout_len={len(raw_result.stdout or '')}")

            if raw_result.returncode == 0 and raw_result.stdout:
                raw_data = json.loads(raw_result.stdout)

                for _filepath, metrics in raw_data.items():
                    if isinstance(metrics, dict):
                        results["raw_metrics"]["loc"] += metrics.get('loc', 0) or 0
                        results["raw_metrics"]["lloc"] += metrics.get('lloc', 0) or 0
                        results["raw_metrics"]["sloc"] += metrics.get('sloc', 0) or 0
                        results["raw_metrics"]["comments"] += metrics.get('comments', 0) or 0
                        results["raw_metrics"]["multi"] += metrics.get('multi', 0) or 0
                        results["raw_metrics"]["blank"] += metrics.get('blank', 0) or 0

                logger.info(f"Raw: sloc={results['raw_metrics']['sloc']}, comments={results['raw_metrics']['comments']}")
            else:
                logger.warning(f"Raw failed: stderr={raw_result.stderr}")

        except Exception as e:
            logger.warning(f"Raw metrics analysis error: {e}")

        return results, cc_success

    def calculate_vci_score(self, metrics: AnalysisMetrics, complexity_data: dict) -> float:
        """
        Calculate Vibe-Code Index (VCI) score.

        VCI = weighted average of:
        - Complexity score (25%)
        - Duplication score (25%)
        - Maintainability score (30%)
        - Architecture score (20%)

        Score range: 0-100 (higher is better)
        """
        # Complexity score (based on cyclomatic complexity)
        avg_cc = complexity_data.get("avg_complexity", 5.0)
        # CC 1-5 = excellent, 5-10 = good, 10-20 = concerning, 20+ = bad
        if avg_cc <= 5:
            complexity_score = 100 - (avg_cc * 2)
        elif avg_cc <= 10:
            complexity_score = 90 - ((avg_cc - 5) * 4)
        elif avg_cc <= 20:
            complexity_score = 70 - ((avg_cc - 10) * 3)
        else:
            complexity_score = max(0, 40 - (avg_cc - 20))

        # Long files/functions penalty
        long_file_penalty = min(30, metrics.long_files * 2)
        complexity_score = max(0, complexity_score - long_file_penalty)

        # Maintainability score
        # Based on file sizes and code organization
        if metrics.total_files > 0:
            avg_lines_per_file = metrics.total_lines / metrics.total_files
            if avg_lines_per_file <= 100:
                maintainability_score = 100
            elif avg_lines_per_file <= 200:
                maintainability_score = 90
            elif avg_lines_per_file <= 300:
                maintainability_score = 75
            else:
                maintainability_score = max(40, 100 - avg_lines_per_file / 10)
        else:
            maintainability_score = 50

        # Duplication score (placeholder - would need jscpd or similar)
        duplication_score = 85  # Assume moderate duplication

        # Architecture score (placeholder - would need deeper analysis)
        architecture_score = 75

        # Calculate weighted VCI
        vci = (
            complexity_score * 0.25 +
            duplication_score * 0.25 +
            maintainability_score * 0.30 +
            architecture_score * 0.20
        )

        # Store in metrics
        metrics.complexity_score = round(complexity_score, 1)
        metrics.maintainability_score = round(maintainability_score, 1)
        metrics.duplication_score = round(duplication_score, 1)
        metrics.architecture_score = round(architecture_score, 1)

        return round(vci, 2)

    def generate_report(self, vci_score: float, metrics: AnalysisMetrics, complexity_data: dict) -> str:
        """Generate AI-style analysis report."""
        health = "excellent" if vci_score >= 85 else "good" if vci_score >= 70 else "needs improvement" if vci_score >= 50 else "poor"

        report = f"""## Code Health Analysis

**Overall Health:** {health.title()} (VCI Score: {vci_score})

### Codebase Overview
- **Total Files:** {metrics.total_files}
- **Total Lines of Code:** {metrics.total_lines:,}
- **Python Files:** {metrics.python_files} ({metrics.python_lines:,} lines)
- **JavaScript/TypeScript Files:** {metrics.js_ts_files} ({metrics.js_ts_lines:,} lines)

### Complexity Analysis
- **Average Cyclomatic Complexity:** {complexity_data.get('avg_complexity', 'N/A'):.1f}
- **Max Complexity:** {complexity_data.get('max_complexity', 'N/A'):.0f}
- **High Complexity Functions:** {complexity_data.get('high_complexity_count', 0)}

### Code Quality Metrics
- **Complexity Score:** {metrics.complexity_score}/100
- **Maintainability Score:** {metrics.maintainability_score}/100
- **Duplication Score:** {metrics.duplication_score}/100
- **Architecture Score:** {metrics.architecture_score}/100

### Findings
"""
        # Add findings
        findings = []

        if complexity_data.get('high_complexity_count', 0) > 5:
            findings.append(f"⚠️ Found {complexity_data['high_complexity_count']} functions with high complexity (CC > 10)")

        if metrics.long_files > 3:
            findings.append(f"⚠️ Found {metrics.long_files} files exceeding 300 lines")

        if metrics.complexity_score < 60:
            findings.append("🔴 Code complexity is concerning - consider refactoring complex functions")

        if not findings:
            findings.append("✅ No major issues detected")

        report += "\n".join(f"- {f}" for f in findings)

        return report

    def run_hard_heuristics(self, metrics: AnalysisMetrics) -> dict:
        """Run hard heuristics analysis using AST-based detection.

        Uses Tree-sitter for Python/JS/TS to reduce false positives by:
        - Ignoring function parameters (e.g., def process(data): is OK)
        - Ignoring loop variables (e.g., for i in range(): is OK)
        - Ignoring comprehension variables
        - Only flagging actual variable assignments with generic names
        """
        if not self.temp_dir:
            return {}

        results = {
            "generic_names": [],
            "magic_numbers": [],
            "missing_docstrings": [],
            "todo_fixme": [],
            "long_functions": [],
        }

        # Get AST analyzer (uses Tree-sitter when available)
        ast_analyzer = get_ast_analyzer()

        python_exts = {".py"}
        js_ts_exts = {".js", ".jsx", ".ts", ".tsx"}
        ast_supported_exts = python_exts | js_ts_exts
        all_code_exts = ast_supported_exts | {".java", ".go", ".rs", ".rb", ".php"}

        # Track files processed for periodic heartbeat
        files_processed = 0
        heartbeat_interval = 50  # Send heartbeat every 50 files

        for root, dirs, files in os.walk(self.temp_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('node_modules', 'vendor', '__pycache__', 'dist', 'build')]

            for file in files:
                filepath = Path(root) / file
                ext = filepath.suffix.lower()

                if ext not in all_code_exts:
                    continue

                # Send periodic heartbeat during file iteration
                files_processed += 1
                if files_processed % heartbeat_interval == 0:
                    self._send_heartbeat()

                try:
                    with open(filepath, encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        lines = content.split('\n')

                    rel_path = str(filepath.relative_to(self.temp_dir))

                    # Use AST-based analysis for supported languages
                    if ext in ast_supported_exts:
                        ast_result = ast_analyzer.analyze_file(rel_path, content)

                        # Collect generic names (high confidence only)
                        for naming_issue in ast_result.generic_names:
                            if naming_issue.confidence >= 0.7:  # Filter low-confidence
                                metrics.generic_names += 1
                                if len(results["generic_names"]) < 10:
                                    results["generic_names"].append(
                                        f"{rel_path}:{naming_issue.line} ({naming_issue.name})"
                                    )

                        # Collect magic numbers (high confidence only)
                        for magic_issue in ast_result.magic_numbers:
                            if magic_issue.confidence >= 0.6:
                                metrics.magic_numbers += 1
                                if len(results["magic_numbers"]) < 10:
                                    results["magic_numbers"].append(
                                        f"{rel_path}:{magic_issue.line} ({magic_issue.value})"
                                    )
                    else:
                        # Fallback to regex for unsupported languages
                        for i, line in enumerate(lines):
                            if not line.strip().startswith('#') and not line.strip().startswith('//'):
                                matches = MAGIC_NUMBER_PATTERN.findall(line)
                                metrics.magic_numbers += len(matches)
                                if matches and len(results["magic_numbers"]) < 10:
                                    results["magic_numbers"].append(f"{rel_path}:{i+1}")

                    # Check for TODO/FIXME comments (regex is fine here)
                    for i, line in enumerate(lines):
                        if 'TODO' in line.upper() or 'FIXME' in line.upper():
                            metrics.todo_comments += 1
                            if len(results["todo_fixme"]) < 10:
                                results["todo_fixme"].append(f"{rel_path}:{i+1}")

                    # Python-specific checks
                    if ext == ".py":
                        # Check for missing docstrings (simple heuristic)
                        if 'def ' in content or 'class ' in content:
                            if '"""' not in content and "'''" not in content:
                                metrics.missing_docstrings += 1

                        # Check for missing type hints
                        func_pattern = re.compile(r'def \w+\([^)]*\):')
                        typed_pattern = re.compile(r'def \w+\([^)]*\)\s*->')
                        funcs = func_pattern.findall(content)
                        typed_funcs = typed_pattern.findall(content)
                        metrics.missing_type_hints += len(funcs) - len(typed_funcs)

                    # Count comments
                    for line in lines:
                        stripped = line.strip()
                        if stripped.startswith('#') or stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
                            metrics.total_comments += 1

                except Exception as e:
                    logger.debug(f"Error in heuristics for {filepath}: {e}")

        # Send final heartbeat after heuristics analysis
        self._send_heartbeat()

        # Calculate heuristics score (adjusted weights for AST-based detection)
        # Calculate size-normalized heuristics score
        # Normalize penalties to repo size (per 1000 lines or per 10 files)
        total_files = max(1, metrics.total_files)
        total_kloc = max(1, metrics.total_lines / 1000)

        # Size-normalized penalties (issues per unit)
        penalties = 0

        # Generic names: per 10 files, cap at 15
        generic_per_10_files = (metrics.generic_names / total_files) * 10
        penalties += min(15, generic_per_10_files * 2)

        # Magic numbers: per KLOC, cap at 15
        magic_per_kloc = metrics.magic_numbers / total_kloc
        penalties += min(15, magic_per_kloc * 0.5)

        # Missing docstrings: per 10 files, cap at 10
        docstring_per_10_files = (metrics.missing_docstrings / total_files) * 10
        penalties += min(10, docstring_per_10_files * 1.5)

        # Missing type hints: per KLOC, cap at 10
        type_hints_per_kloc = metrics.missing_type_hints / total_kloc
        penalties += min(10, type_hints_per_kloc * 0.05)

        # TODO comments: per KLOC, cap at 10
        todos_per_kloc = metrics.todo_comments / total_kloc
        penalties += min(10, todos_per_kloc * 0.5)

        # Long files penalty: percentage of files that are long, cap at 10
        long_file_ratio = metrics.long_files / total_files
        penalties += min(10, long_file_ratio * 30)

        metrics.heuristics_score = max(0, round(100 - penalties, 1))

        logger.info(
            f"Hard heuristics (size-normalized): generic={metrics.generic_names}, "
            f"magic={metrics.magic_numbers}, todos={metrics.todo_comments}, "
            f"long_files={metrics.long_files}, total_files={total_files}"
        )

        return results

    def detect_issues(self, metrics: AnalysisMetrics, complexity_data: dict, heuristics_data: dict) -> list:
        """Detect code issues for the issues list."""
        issues = []

        # High complexity functions
        if complexity_data.get('high_complexity_count', 0) > 0:
            count = complexity_data['high_complexity_count']
            issues.append({
                "type": "complexity",
                "severity": "low" if count < 3 else "medium" if count < 10 else "high",
                "title": "High Cyclomatic Complexity",
                "description": f"Found {count} functions with complexity > 10. Consider breaking them into smaller functions.",
                "confidence": 0.9,
            })

        # Long files
        if metrics.long_files > 0:
            issues.append({
                "type": "maintainability",
                "severity": "low" if metrics.long_files < 3 else "medium",
                "title": "Long Files Detected",
                "description": f"Found {metrics.long_files} files with more than 300 lines. Consider splitting into modules.",
                "confidence": 0.95,
            })

        # Generic variable names
        if metrics.generic_names > 10:
            issues.append({
                "type": "naming",
                "severity": "low",
                "title": "Generic Variable Names",
                "description": f"Found {metrics.generic_names} uses of generic names (data, temp, result, etc). Use descriptive names.",
                "confidence": 0.7,
            })

        # Magic numbers
        if metrics.magic_numbers > 20:
            issues.append({
                "type": "maintainability",
                "severity": "low",
                "title": "Magic Numbers Detected",
                "description": f"Found {metrics.magic_numbers} hardcoded numbers. Consider using named constants.",
                "confidence": 0.6,
            })

        # Missing docstrings
        if metrics.missing_docstrings > 5:
            issues.append({
                "type": "documentation",
                "severity": "low",
                "title": "Missing Documentation",
                "description": f"Found {metrics.missing_docstrings} modules without docstrings. Add documentation for better maintainability.",
                "confidence": 0.75,
            })

        # TODO/FIXME comments
        if metrics.todo_comments > 10:
            issues.append({
                "type": "tech_debt",
                "severity": "medium" if metrics.todo_comments > 30 else "low",
                "title": "Unresolved TODO/FIXME Comments",
                "description": f"Found {metrics.todo_comments} TODO/FIXME comments indicating pending work.",
                "confidence": 0.95,
            })

        # Low comment ratio
        if metrics.total_lines > 100:
            comment_ratio = metrics.total_comments / metrics.total_lines
            if comment_ratio < MIN_COMMENT_RATIO:
                issues.append({
                    "type": "documentation",
                    "severity": "low",
                    "title": "Low Comment Ratio",
                    "description": f"Code has {comment_ratio*100:.1f}% comments. Consider adding more documentation.",
                    "confidence": 0.6,
                })

        return issues

    def _calculate_architecture_score(self, metrics: AnalysisMetrics) -> float:
        """Calculate architecture score based on file organization and structure.

        Factors considered:
        - Language consistency (single dominant language)
        - Presence of tests
        - Presence of documentation (README)
        - Organized structure (src/, lib/, app/ directories)
        - Reasonable file count distribution

        Returns:
            Architecture score 0-100
        """
        if not self.temp_dir:
            return 70.0  # Default when no repo available

        score = 70.0  # Base score

        # Check language consistency (+10 for dominant language)
        if metrics.total_files > 0:
            python_ratio = metrics.python_files / metrics.total_files
            js_ts_ratio = metrics.js_ts_files / metrics.total_files
            if python_ratio > 0.7 or js_ts_ratio > 0.7:
                score += 10

        # Check for tests (+5)
        has_tests = False
        for root, dirs, files in os.walk(self.temp_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'node_modules']
            for f in files:
                if 'test' in f.lower() or '__tests__' in root:
                    has_tests = True
                    break
            if has_tests:
                break
        if has_tests:
            score += 5

        # Check for README (+5)
        has_readme = any(
            f.lower().startswith('readme')
            for f in os.listdir(self.temp_dir)
            if os.path.isfile(os.path.join(self.temp_dir, f))
        )
        if has_readme:
            score += 5

        # Check for organized structure (+5 for src/, lib/, or app/ directory)
        has_organized_structure = any(
            d in ('src', 'lib', 'app', 'pkg', 'internal')
            for d in os.listdir(self.temp_dir)
            if os.path.isdir(os.path.join(self.temp_dir, d))
        )
        if has_organized_structure:
            score += 5

        # Penalty for too many files at root level (-5)
        root_files = [
            f for f in os.listdir(self.temp_dir)
            if os.path.isfile(os.path.join(self.temp_dir, f))
            and not f.startswith('.')
            and f not in ('README.md', 'LICENSE', 'package.json', 'pyproject.toml', 'Makefile', 'Dockerfile')
        ]
        if len(root_files) > 10:
            score -= 5

        # Penalty for very deep nesting (avg depth > 5) - indicates over-engineering
        # This is a simplified check
        if metrics.total_files > 0 and metrics.long_files > metrics.total_files * 0.3:
            score -= 5  # Too many long files suggests poor modularization

        return max(40.0, min(100.0, score))

    def calculate_vci_score_enhanced(self, metrics: AnalysisMetrics, complexity_data: dict) -> float:
        """
        Calculate enhanced Vibe-Code Index (VCI) score.

        VCI = weighted average of (aligned with PRD):
        - Complexity score (25%) - cyclomatic complexity + long files penalty
        - Duplication score (25%) - code patterns (placeholder until jscpd integration)
        - Heuristics score (30%) - hard heuristics (generic names, magic numbers, docs, etc.)
        - Architecture score (20%) - file organization and structure
        """
        # Complexity score (based on cyclomatic complexity)
        avg_cc = complexity_data.get("avg_complexity", 5.0)
        if avg_cc <= 5:
            complexity_score = 100 - (avg_cc * 2)
        elif avg_cc <= 10:
            complexity_score = 90 - ((avg_cc - 5) * 4)
        elif avg_cc <= 20:
            complexity_score = 70 - ((avg_cc - 10) * 3)
        else:
            complexity_score = max(0, 40 - (avg_cc - 20))

        # Long files penalty (applied to complexity)
        long_file_penalty = min(20, metrics.long_files * 2)
        complexity_score = max(0, complexity_score - long_file_penalty)

        # Duplication score (placeholder - measures code patterns until jscpd integration)
        # TODO: Integrate jscpd for real clone detection
        duplication_score = 80  # Base score
        if metrics.total_files > 50:
            duplication_score -= 5
        if metrics.magic_numbers > 50:
            duplication_score -= 10
        duplication_score = max(50, duplication_score)

        # Architecture score (based on file organization and structure)
        architecture_score = self._calculate_architecture_score(metrics)

        # Store scores for metrics API
        metrics.complexity_score = round(complexity_score, 1)
        metrics.duplication_score = round(duplication_score, 1)
        metrics.architecture_score = round(architecture_score, 1)
        # Note: heuristics_score is set in run_hard_heuristics()

        # Calculate weighted VCI (PRD formula: 25/25/30/20)
        vci = (
            complexity_score * 0.25 +
            duplication_score * 0.25 +
            metrics.heuristics_score * 0.30 +
            architecture_score * 0.20
        )

        return round(vci, 2)

    def analyze(self) -> AnalysisResult:
        """Run complete analysis with multi-language support and hard heuristics.

        Orchestrates analysis across multiple languages:
        1. Detects languages present in the repository
        2. Runs radon for Python files (CC, Halstead, MI)
        3. Runs lizard for non-Python files (JS, TS, Java, Go, etc.)
        4. Merges results into unified metrics with by_language breakdown

        Implements graceful degradation:
        - If radon fails, continues with lizard results only
        - If lizard fails, continues with radon results only
        - If both fail, returns basic file/line counts with zero complexity

        Sends heartbeat updates during long operations to indicate the worker is alive.
        """
        # Clone repository (heartbeat sent inside clone())
        self.clone()

        # Count lines
        metrics = self.count_lines()
        
        # Send heartbeat after line counting
        self._send_heartbeat()

        # Detect languages present in repo
        detected_languages = self._detect_languages()
        logger.info(f"Detected languages in repo: {detected_languages}")

        # Track analyzer success for graceful degradation
        radon_success = False
        lizard_success = False
        languages_analyzed: list[str] = []

        # Run Python analysis (radon) if Python files exist
        # (heartbeat sent inside analyze_python_complexity())
        python_complexity_data = {}
        if 'python' in detected_languages:
            logger.info("Running radon analysis for Python files")
            python_complexity_data, radon_success = self.analyze_python_complexity()
            if radon_success:
                languages_analyzed.append('python')
            else:
                logger.warning("radon analysis failed - Python complexity metrics will be unavailable")

        # Run lizard for non-Python languages
        # (heartbeat sent inside analyze_with_lizard())
        lizard_complexity_data = {}
        non_python_languages = detected_languages - {'python'}
        if non_python_languages:
            logger.info(f"Running lizard analysis for: {non_python_languages}")
            lizard_complexity_data, lizard_success = self.analyze_with_lizard()
            if lizard_success and lizard_complexity_data.get("languages_analyzed"):
                languages_analyzed.extend(lizard_complexity_data.get("languages_analyzed", []))
            elif not lizard_success:
                logger.warning("lizard analysis failed - non-Python complexity metrics will be unavailable")

        # Handle graceful degradation when both analyzers fail
        if not radon_success and not lizard_success and detected_languages:
            logger.error(
                "Both radon and lizard analyzers failed. "
                "Returning basic file/line counts with zero complexity metrics."
            )
            # Return fallback complexity data with zero values
            complexity_data = self._get_fallback_complexity_data()
        else:
            # Merge results from both analyzers (partial results are OK)
            complexity_data = self._merge_complexity_results(
                python_complexity_data,
                lizard_complexity_data,
                python_metrics=metrics  # Pass metrics for Python file/line counts
            )

            # Add warning about partial results if one analyzer failed
            if detected_languages:
                if 'python' in detected_languages and not radon_success:
                    complexity_data["_warning"] = "Python analysis failed - showing partial results"
                elif non_python_languages and not lizard_success:
                    complexity_data["_warning"] = "Non-Python analysis failed - showing partial results"

        # Send heartbeat before heuristics analysis
        self._send_heartbeat()

        # Run hard heuristics (heartbeat sent periodically inside run_hard_heuristics())
        heuristics_data = self.run_hard_heuristics(metrics)

        # Calculate enhanced VCI
        vci_score = self.calculate_vci_score_enhanced(metrics, complexity_data)

        # Determine tech debt level
        if vci_score >= 75:
            tech_debt_level = "low"
        elif vci_score >= 55:
            tech_debt_level = "medium"
        else:
            tech_debt_level = "high"

        # Generate report
        ai_report = self.generate_report(vci_score, metrics, complexity_data)

        # Detect issues (with heuristics data)
        issues = self.detect_issues(metrics, complexity_data, heuristics_data)

        # Determine complexity source for transparency
        if radon_success and lizard_success:
            complexity_source = "radon+lizard"
        elif radon_success:
            complexity_source = "radon"
        elif lizard_success:
            complexity_source = "lizard"
        else:
            complexity_source = "fallback"

        # Send final heartbeat before returning
        self._send_heartbeat()

        return AnalysisResult(
            vci_score=vci_score,
            tech_debt_level=tech_debt_level,
            metrics={
                # VCI Score Components
                "complexity_score": metrics.complexity_score,
                "duplication_score": metrics.duplication_score,
                "maintainability_score": metrics.maintainability_score,
                "architecture_score": metrics.architecture_score,
                "heuristics_score": metrics.heuristics_score,
                # Complexity source for transparency
                "complexity_source": complexity_source,
                # Basic counts
                "total_files": metrics.total_files,
                "total_lines": metrics.total_lines,
                "total_comments": metrics.total_comments,
                "python_files": metrics.python_files,
                "python_lines": metrics.python_lines,
                "js_ts_files": metrics.js_ts_files,
                "js_ts_lines": metrics.js_ts_lines,
                # Cyclomatic Complexity (merged from radon + lizard)
                "avg_complexity": complexity_data.get("avg_complexity", 0),
                "max_complexity": complexity_data.get("max_complexity", 0),
                "high_complexity_functions": complexity_data.get("high_complexity_count", 0),
                "complexity_distribution": complexity_data.get("complexity_distribution", {}),
                "top_complex_functions": complexity_data.get("top_complex_functions", []),
                # Halstead Metrics (Python only via radon)
                "halstead": complexity_data.get("halstead", {}),
                # Maintainability Index (Python only via radon)
                "maintainability_index": complexity_data.get("maintainability_index", {}),
                # Raw Metrics (from radon)
                "raw_metrics": complexity_data.get("raw_metrics", {}),
                # Per-language breakdown (NEW)
                "by_language": complexity_data.get("by_language", {}),
                # Hard Heuristics
                "generic_names": metrics.generic_names,
                "magic_numbers": metrics.magic_numbers,
                "todo_comments": metrics.todo_comments,
                "missing_docstrings": metrics.missing_docstrings,
                "missing_type_hints": metrics.missing_type_hints,
            },
            ai_report=ai_report,
            issues=issues,
        )
