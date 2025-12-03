"""VCI (Vibe-Code Index) Calculator service."""

import logging
import re
from dataclasses import dataclass, field

from app.services.llm_gateway import get_llm_gateway

logger = logging.getLogger(__name__)


@dataclass
class MetricsResult:
    """Result of metrics calculation."""
    complexity_score: float = 0.0  # 0-100, higher is better
    duplication_score: float = 0.0  # 0-100, higher is better
    maintainability_score: float = 0.0  # 0-100, higher is better
    architecture_score: float = 0.0  # 0-100, higher is better
    test_coverage_score: float = 0.0  # 0-100

    # Raw metrics
    raw_metrics: dict = field(default_factory=dict)

    # Issues found
    issues: list[dict] = field(default_factory=list)


@dataclass
class VCIResult:
    """Final VCI calculation result."""
    vci_score: int  # 0-100
    grade: str  # A, B, C, D, F
    metrics: MetricsResult
    summary: str
    recommendations: list[str]


class VCICalculator:
    """Calculates Vibe-Code Index from analysis results."""

    # VCI weights from PRD
    WEIGHTS = {
        "complexity": 0.25,
        "duplication": 0.25,
        "heuristics": 0.30,  # Hard heuristics + AI patterns
        "architecture": 0.20,
    }

    # Grade thresholds
    GRADE_THRESHOLDS = [
        (90, "A"),
        (80, "B"),
        (70, "C"),
        (60, "D"),
        (0, "F"),
    ]

    def __init__(self):
        self.llm_gateway = None  # Lazy loaded

    def calculate_vci(self, metrics: MetricsResult) -> VCIResult:
        """Calculate final VCI score from metrics."""
        # Calculate weighted score
        weighted_score = (
            metrics.complexity_score * self.WEIGHTS["complexity"] +
            metrics.duplication_score * self.WEIGHTS["duplication"] +
            metrics.maintainability_score * self.WEIGHTS["heuristics"] +
            metrics.architecture_score * self.WEIGHTS["architecture"]
        )

        vci_score = int(round(weighted_score))
        vci_score = max(0, min(100, vci_score))  # Clamp to 0-100

        # Determine grade
        grade = "F"
        for threshold, g in self.GRADE_THRESHOLDS:
            if vci_score >= threshold:
                grade = g
                break

        # Generate summary and recommendations
        summary = self._generate_summary(vci_score, grade, metrics)
        recommendations = self._generate_recommendations(metrics)

        return VCIResult(
            vci_score=vci_score,
            grade=grade,
            metrics=metrics,
            summary=summary,
            recommendations=recommendations,
        )

    def _generate_summary(
        self, vci_score: int, grade: str, metrics: MetricsResult
    ) -> str:
        """Generate human-readable summary."""
        summaries = {
            "A": "Excellent code health! The codebase is well-maintained with low technical debt.",
            "B": "Good code health. Some areas could be improved but overall solid.",
            "C": "Fair code health. There are notable areas that need attention.",
            "D": "Below average code health. Significant improvements recommended.",
            "F": "Poor code health. Immediate attention required to prevent technical debt accumulation.",
        }

        base_summary = summaries.get(grade, "")

        # Add specific insights
        insights = []
        if metrics.complexity_score < 60:
            insights.append("High complexity detected in several modules.")
        if metrics.duplication_score < 60:
            insights.append("Significant code duplication found.")
        if metrics.maintainability_score < 60:
            insights.append("Several maintainability issues identified.")
        if metrics.architecture_score < 60:
            insights.append("Architectural improvements recommended.")

        if insights:
            return f"{base_summary} {' '.join(insights)}"
        return base_summary

    def _generate_recommendations(self, metrics: MetricsResult) -> list[str]:
        """Generate actionable recommendations."""
        recommendations = []

        if metrics.complexity_score < 70:
            recommendations.append(
                "Consider breaking down complex functions into smaller, more focused units."
            )

        if metrics.duplication_score < 70:
            recommendations.append(
                "Extract duplicated code into reusable functions or modules."
            )

        if metrics.maintainability_score < 70:
            recommendations.append(
                "Add documentation and improve naming conventions for better readability."
            )

        if metrics.architecture_score < 70:
            recommendations.append(
                "Review module dependencies and consider applying SOLID principles."
            )

        if metrics.test_coverage_score < 50:
            recommendations.append(
                "Increase test coverage, especially for critical business logic."
            )

        if not recommendations:
            recommendations.append(
                "Keep up the good work! Consider adding more tests for edge cases."
            )

        return recommendations


class HardHeuristicsAnalyzer:
    """Analyzes code using deterministic hard heuristics from PRD.
    
    Now uses AST-based analysis via Tree-sitter for Python/JS/TS
    to reduce false positives in generic name detection.
    """

    # Thresholds from PRD
    MAX_FUNCTION_LINES = 50
    MAX_FILE_LINES = 300
    MIN_COMMENT_RATIO = 0.05  # 5%
    MAX_CYCLOMATIC_COMPLEXITY = 10

    def __init__(self):
        self.issues: list[dict] = []
        # Lazy import to avoid circular dependencies
        self._ast_analyzer = None

    @property
    def ast_analyzer(self):
        """Get AST analyzer (lazy loaded)."""
        if self._ast_analyzer is None:
            from app.services.ast_analyzer import get_ast_analyzer
            self._ast_analyzer = get_ast_analyzer()
        return self._ast_analyzer

    def analyze_file(self, filepath: str, content: str) -> list[dict]:
        """Analyze a single file using hard heuristics with AST support."""
        issues = []
        lines = content.split("\n")

        # Check file length
        if len(lines) > self.MAX_FILE_LINES:
            issues.append({
                "type": "cognitive_complexity",
                "severity": "medium",
                "file": filepath,
                "message": f"File exceeds {self.MAX_FILE_LINES} lines ({len(lines)} lines)",
                "confidence": 0.95,
            })

        # Check comment ratio
        comment_lines = sum(1 for line in lines if self._is_comment(line, filepath))
        code_lines = sum(1 for line in lines if line.strip() and not self._is_comment(line, filepath))

        if code_lines > 0:
            comment_ratio = comment_lines / code_lines
            if comment_ratio < self.MIN_COMMENT_RATIO:
                issues.append({
                    "type": "missing_documentation",
                    "severity": "low",
                    "file": filepath,
                    "message": f"Low comment ratio ({comment_ratio:.1%}), consider adding documentation",
                    "confidence": 0.8,
                })

        # Use AST-based analysis for supported languages
        ext = filepath.split('.')[-1] if '.' in filepath else ''
        if ext in ('py', 'js', 'jsx', 'ts', 'tsx'):
            ast_result = self.ast_analyzer.analyze_file(filepath, content)

            # Report magic numbers from AST analysis
            if ast_result.magic_numbers:
                high_confidence = [m for m in ast_result.magic_numbers if m.confidence >= 0.6]
                if high_confidence:
                    values = [m.value for m in high_confidence[:5]]
                    issues.append({
                        "type": "magic_numbers",
                        "severity": "low",
                        "file": filepath,
                        "message": f"Found {len(high_confidence)} magic numbers: {values}...",
                        "confidence": 0.8,  # Higher confidence with AST
                    })

            # Report generic names from AST analysis
            if ast_result.generic_names:
                high_confidence = [n for n in ast_result.generic_names if n.confidence >= 0.7]
                if high_confidence:
                    names = [n.name for n in high_confidence[:5]]
                    issues.append({
                        "type": "semantic_poverty",
                        "severity": "low",
                        "file": filepath,
                        "message": f"Found generic variable names: {', '.join(names)}",
                        "confidence": 0.85,  # Higher confidence with AST
                    })
        else:
            # Fallback to regex for unsupported languages
            magic_numbers = self._find_magic_numbers(content)
            if magic_numbers:
                issues.append({
                    "type": "magic_numbers",
                    "severity": "low",
                    "file": filepath,
                    "message": f"Found {len(magic_numbers)} magic numbers: {magic_numbers[:5]}...",
                    "confidence": 0.6,  # Lower confidence with regex
                })

            generic_names = self._find_generic_names_regex(content)
            if generic_names:
                issues.append({
                    "type": "semantic_poverty",
                    "severity": "low",
                    "file": filepath,
                    "message": f"Found generic variable names: {', '.join(list(generic_names)[:5])}",
                    "confidence": 0.6,  # Lower confidence with regex
                })

        return issues

    def _is_comment(self, line: str, filepath: str) -> bool:
        """Check if a line is a comment."""
        stripped = line.strip()

        if filepath.endswith((".py",)):
            return stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''")
        elif filepath.endswith((".js", ".ts", ".jsx", ".tsx")):
            return stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*")

        return False

    def _find_magic_numbers(self, content: str) -> list[str]:
        """Find magic numbers in code (regex fallback)."""
        pattern = r"\b(?<!\.)\d{2,}\b"
        matches = re.findall(pattern, content)

        acceptable = {"100", "1000", "10000", "60", "24", "365", "200", "201", "204", "400", "401", "403", "404", "500"}
        return [m for m in matches if m not in acceptable][:10]

    def _find_generic_names_regex(self, content: str) -> set[str]:
        """Find generic variable names (regex fallback for unsupported languages)."""
        pattern = r"\b(data|info|temp|tmp|result|ret|val|obj|item|items|lst|arr)\s*="
        matches = re.findall(pattern, content, re.IGNORECASE)
        return set(matches)

    def analyze_function_complexity(
        self, radon_output: dict
    ) -> tuple[float, list[dict]]:
        """Analyze cyclomatic complexity from radon output."""
        issues = []
        total_score = 0
        function_count = 0

        for filepath, functions in radon_output.items():
            for func in functions:
                complexity = func.get("complexity", 0)
                function_count += 1

                # Score: inverse of complexity, capped
                func_score = max(0, 100 - (complexity - 1) * 10)
                total_score += func_score

                if complexity > self.MAX_CYCLOMATIC_COMPLEXITY:
                    issues.append({
                        "type": "high_complexity",
                        "severity": "high" if complexity > 20 else "medium",
                        "file": filepath,
                        "function": func.get("name", "unknown"),
                        "line": func.get("lineno", 0),
                        "message": f"Cyclomatic complexity {complexity} exceeds threshold",
                        "confidence": 0.95,
                    })

        avg_score = total_score / max(function_count, 1)
        return avg_score, issues

    def analyze_duplication(
        self, jscpd_output: dict
    ) -> tuple[float, list[dict]]:
        """Analyze code duplication from jscpd output."""
        issues = []

        statistics = jscpd_output.get("statistics", {})
        total = statistics.get("total", {})

        # Get duplication percentage
        duplicated_lines = total.get("duplicatedLines", 0)
        total_lines = total.get("lines", 1)
        duplication_percentage = (duplicated_lines / total_lines) * 100

        # Score: 100 - duplication percentage (0% duplication = 100 score)
        score = max(0, 100 - duplication_percentage * 2)  # 2x penalty

        # Report individual duplicates
        duplicates = jscpd_output.get("duplicates", [])
        for dup in duplicates[:10]:  # Top 10 duplicates
            first = dup.get("firstFile", {})
            second = dup.get("secondFile", {})
            lines = dup.get("lines", 0)

            if lines >= 10:  # Only report significant duplications
                issues.append({
                    "type": "code_duplication",
                    "severity": "high" if lines > 50 else "medium",
                    "file": first.get("name", "unknown"),
                    "line": first.get("start", 0),
                    "message": f"Duplicated {lines} lines with {second.get('name', 'unknown')}",
                    "confidence": 0.9,
                })

        return score, issues


class AIPatternDetector:
    """Detects code patterns using LLM analysis."""

    ANALYSIS_PROMPT = """Analyze the following code for potential issues and anti-patterns.

Focus on:
1. Design pattern violations
2. SOLID principle violations
3. Over-abstraction or under-abstraction
4. Inconsistent coding style
5. Potential bugs or edge cases
6. Security concerns
7. Performance issues

Code to analyze:
```
{code}
```

Respond with a JSON array of issues found. Each issue should have:
- type: string (e.g., "design_pattern", "solid_violation", "security", "performance")
- severity: "high" | "medium" | "low"
- message: string describing the issue
- suggestion: string with how to fix it
- confidence: float 0-1

Only include issues you're confident about. Return empty array if no issues found.
"""

    def __init__(self):
        self.llm_gateway = None

    async def analyze_code(self, code: str, filepath: str) -> list[dict]:
        """Analyze code using LLM."""
        if not self.llm_gateway:
            self.llm_gateway = get_llm_gateway()

        try:
            # Truncate code if too long
            max_chars = 8000
            if len(code) > max_chars:
                code = code[:max_chars] + "\n... (truncated)"

            prompt = self.ANALYSIS_PROMPT.format(code=code)

            response = await self.llm_gateway.complete(
                prompt=prompt,
                temperature=0.1,
                max_tokens=2000,
                system_prompt="You are an expert code reviewer. Respond only with valid JSON.",
            )

            # Parse JSON response
            import json

            # Try to extract JSON from response
            try:
                issues = json.loads(response)
            except json.JSONDecodeError:
                # Try to find JSON array in response
                start = response.find("[")
                end = response.rfind("]") + 1
                if start >= 0 and end > start:
                    issues = json.loads(response[start:end])
                else:
                    return []

            # Add filepath to each issue
            for issue in issues:
                issue["file"] = filepath
                issue["source"] = "ai"

            return issues

        except Exception as e:
            logger.error(f"AI analysis failed for {filepath}: {e}")
            return []


def calculate_architecture_score(
    file_structure: list[str],
    dependencies: dict | None = None,
) -> tuple[float, list[dict]]:
    """Calculate architecture score based on file structure."""
    issues = []
    score = 80  # Start with good score

    # Check for common good patterns
    good_patterns = [
        "src/",
        "lib/",
        "tests/",
        "test/",
        "__tests__/",
        "docs/",
    ]

    has_tests = any(
        "test" in f.lower() or "__tests__" in f
        for f in file_structure
    )
    has_src = any(
        f.startswith("src/") or f.startswith("lib/")
        for f in file_structure
    )

    if not has_tests:
        score -= 15
        issues.append({
            "type": "missing_tests",
            "severity": "medium",
            "message": "No test files found in repository",
            "confidence": 0.8,
        })

    if not has_src:
        score -= 5
        issues.append({
            "type": "structure",
            "severity": "low",
            "message": "Consider organizing code in src/ or lib/ directory",
            "confidence": 0.6,
        })

    # Check for config files (good practice)
    has_config = any(
        f.endswith((".json", ".yaml", ".yml", ".toml", ".ini"))
        and "config" in f.lower()
        for f in file_structure
    )

    if has_config:
        score += 5

    # Check for README
    has_readme = any(
        "readme" in f.lower()
        for f in file_structure
    )

    if not has_readme:
        score -= 5
        issues.append({
            "type": "missing_documentation",
            "severity": "low",
            "message": "No README file found",
            "confidence": 0.9,
        })

    return max(0, min(100, score)), issues
