"""Diagnosis Agent - Analyzes issues and determines fix strategy."""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.services.llm_gateway import get_llm_gateway

logger = logging.getLogger(__name__)


class FixPath(Enum):
    """Fix strategy paths."""
    PATH_A = "simple_refactor"  # Simple, high confidence
    PATH_B = "complex_refactor"  # Complex, needs careful review
    PATH_C = "architectural"  # Architectural change, needs human review
    PATH_D = "manual"  # Too complex for auto-fix


@dataclass
class DiagnosisResult:
    """Result of issue diagnosis."""
    issue_id: str
    fix_path: FixPath
    confidence: float
    complexity_score: int  # 1-10
    estimated_changes: int  # Number of files/lines
    context_needed: list[str]  # File paths needed for fix
    fix_description: str
    risk_factors: list[str]
    can_auto_fix: bool


class DiagnosisAgent:
    """Agent that analyzes issues and determines fix strategy."""
    
    # Confidence thresholds
    AUTO_FIX_THRESHOLD = 0.85
    ASSISTED_THRESHOLD = 0.70
    
    # Complexity thresholds
    MAX_AUTO_FIX_COMPLEXITY = 5
    
    def __init__(self):
        self.llm = get_llm_gateway()
    
    async def diagnose(
        self,
        issue: dict,
        file_content: str | None = None,
        related_files: list[dict] | None = None,
    ) -> DiagnosisResult:
        """
        Analyze an issue and determine the fix strategy.
        
        Args:
            issue: Issue dict with type, severity, title, description, file_path, etc.
            file_content: Content of the file with the issue
            related_files: List of related file contents for context
        
        Returns:
            DiagnosisResult with fix path and details
        """
        logger.info(f"Diagnosing issue: {issue.get('title', issue.get('id'))}")
        
        # Build context for LLM
        context = self._build_context(issue, file_content, related_files)
        
        # Get LLM analysis
        analysis = await self._analyze_with_llm(issue, context)
        
        # Determine fix path based on analysis
        fix_path = self._determine_fix_path(analysis)
        
        # Calculate if auto-fix is possible
        can_auto_fix = (
            analysis["confidence"] >= self.AUTO_FIX_THRESHOLD
            and analysis["complexity"] <= self.MAX_AUTO_FIX_COMPLEXITY
            and fix_path in (FixPath.PATH_A, FixPath.PATH_B)
        )
        
        return DiagnosisResult(
            issue_id=issue.get("id", "unknown"),
            fix_path=fix_path,
            confidence=analysis["confidence"],
            complexity_score=analysis["complexity"],
            estimated_changes=analysis["estimated_changes"],
            context_needed=analysis["context_files"],
            fix_description=analysis["fix_description"],
            risk_factors=analysis["risk_factors"],
            can_auto_fix=can_auto_fix,
        )
    
    def _build_context(
        self,
        issue: dict,
        file_content: str | None,
        related_files: list[dict] | None,
    ) -> str:
        """Build context string for LLM analysis."""
        context_parts = []
        
        # Issue details
        context_parts.append(f"## Issue Details")
        context_parts.append(f"Type: {issue.get('type', 'unknown')}")
        context_parts.append(f"Severity: {issue.get('severity', 'medium')}")
        context_parts.append(f"Title: {issue.get('title', 'No title')}")
        context_parts.append(f"Description: {issue.get('description', 'No description')}")
        
        if issue.get("file_path"):
            context_parts.append(f"File: {issue['file_path']}")
            if issue.get("line_start"):
                context_parts.append(f"Lines: {issue['line_start']}-{issue.get('line_end', issue['line_start'])}")
        
        # File content
        if file_content:
            context_parts.append(f"\n## File Content")
            context_parts.append(f"```\n{file_content[:5000]}\n```")
        
        # Related files
        if related_files:
            context_parts.append(f"\n## Related Files")
            for rf in related_files[:3]:  # Limit to 3 related files
                context_parts.append(f"\n### {rf.get('path', 'unknown')}")
                context_parts.append(f"```\n{rf.get('content', '')[:2000]}\n```")
        
        return "\n".join(context_parts)
    
    async def _analyze_with_llm(self, issue: dict, context: str) -> dict:
        """Use LLM to analyze the issue."""
        prompt = f"""Analyze this code issue and determine the best fix strategy.

{context}

Provide your analysis in the following format:
1. CONFIDENCE: A score from 0.0 to 1.0 indicating how confident you are that this issue can be fixed correctly
2. COMPLEXITY: A score from 1 to 10 (1=trivial, 10=requires major refactoring)
3. ESTIMATED_CHANGES: Number of files likely to change
4. CONTEXT_FILES: List of additional files needed to understand/fix this issue (comma-separated paths)
5. FIX_DESCRIPTION: Brief description of how to fix this issue
6. RISK_FACTORS: List any risks or considerations (comma-separated)
7. FIX_TYPE: One of: simple_refactor, complex_refactor, architectural, manual

Respond with just the values, one per line:
CONFIDENCE: 
COMPLEXITY: 
ESTIMATED_CHANGES: 
CONTEXT_FILES: 
FIX_DESCRIPTION: 
RISK_FACTORS: 
FIX_TYPE: 
"""
        
        try:
            response = await self.llm.complete(
                prompt=prompt,
                temperature=0.1,
                max_tokens=1000,
            )
            return self._parse_llm_response(response)
        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")
            # Return conservative defaults
            return {
                "confidence": 0.5,
                "complexity": 7,
                "estimated_changes": 1,
                "context_files": [],
                "fix_description": "Manual review required",
                "risk_factors": ["LLM analysis failed"],
                "fix_type": "manual",
            }
    
    def _parse_llm_response(self, response: str) -> dict:
        """Parse LLM response into structured data."""
        result = {
            "confidence": 0.5,
            "complexity": 5,
            "estimated_changes": 1,
            "context_files": [],
            "fix_description": "",
            "risk_factors": [],
            "fix_type": "manual",
        }
        
        for line in response.split("\n"):
            line = line.strip()
            if ":" not in line:
                continue
            
            key, value = line.split(":", 1)
            key = key.strip().upper()
            value = value.strip()
            
            if key == "CONFIDENCE":
                try:
                    result["confidence"] = min(1.0, max(0.0, float(value)))
                except ValueError:
                    pass
            elif key == "COMPLEXITY":
                try:
                    result["complexity"] = min(10, max(1, int(value)))
                except ValueError:
                    pass
            elif key == "ESTIMATED_CHANGES":
                try:
                    result["estimated_changes"] = max(1, int(value))
                except ValueError:
                    pass
            elif key == "CONTEXT_FILES":
                result["context_files"] = [f.strip() for f in value.split(",") if f.strip()]
            elif key == "FIX_DESCRIPTION":
                result["fix_description"] = value
            elif key == "RISK_FACTORS":
                result["risk_factors"] = [r.strip() for r in value.split(",") if r.strip()]
            elif key == "FIX_TYPE":
                result["fix_type"] = value.lower().replace(" ", "_")
        
        return result
    
    def _determine_fix_path(self, analysis: dict) -> FixPath:
        """Determine the fix path based on analysis results."""
        fix_type = analysis.get("fix_type", "manual")
        complexity = analysis.get("complexity", 10)
        confidence = analysis.get("confidence", 0)
        
        if fix_type == "simple_refactor" and complexity <= 3 and confidence >= 0.8:
            return FixPath.PATH_A
        elif fix_type in ("simple_refactor", "complex_refactor") and complexity <= 6:
            return FixPath.PATH_B
        elif fix_type == "architectural" or complexity > 6:
            return FixPath.PATH_C
        else:
            return FixPath.PATH_D
