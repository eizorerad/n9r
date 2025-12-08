"""Semantic AI Insights Service.

Generates AI-powered insights for semantic analysis using LiteLLM directly.
This is SEPARATE from BroadScanAgent/AI Scan - it's part of the semantic
analysis track (Track 2).

Requirements: 5.2, 5.3
"""

import json
import logging
from dataclasses import asdict
from uuid import UUID

from app.schemas.architecture_llm import (
    LLMReadyArchitectureData,
)
from app.services.scoring import get_scoring_service

logger = logging.getLogger(__name__)


# System prompt for generating architecture insights
SYSTEM_PROMPT = """You are a senior software architect analyzing codebase health.
Given architecture findings (dead code, hot spots), generate specific, actionable recommendations.

CRITICAL: You MUST return ONLY valid JSON. Do not include any markdown, explanations, or text outside the JSON object.

Each recommendation should:
1. Have a clear, specific title (what to do)
2. Include a detailed description (why it matters)
3. Specify priority (high/medium/low) based on impact
4. List affected files
5. Provide evidence from the findings
6. Suggest a concrete action

Focus on the most impactful issues first. Be specific - don't give generic advice.

REQUIRED OUTPUT FORMAT (valid JSON only):
{
  "recommendations": [
    {
      "insight_type": "dead_code",
      "title": "Remove unused payment processing functions",
      "description": "3 functions in payment_processor.py are never called and add 150 lines of unmaintained code",
      "priority": "high",
      "affected_files": ["src/payment_processor.py"],
      "evidence": "Call graph analysis shows process_legacy_payment(), validate_old_card(), and format_receipt_v1() have no callers",
      "suggested_action": "Delete these functions after confirming no dynamic calls exist. Consider adding deprecation warnings first if unsure."
    }
  ]
}

Return ONLY the JSON object above. No markdown code blocks, no explanations, just pure JSON."""


class SemanticAIInsightsService:
    """Generates AI-powered insights for semantic analysis.

    IMPORTANT: This is SEPARATE from BroadScanAgent/AI Scan.
    - Uses LiteLLM directly via LLMGateway
    - Part of semantic analysis track (Track 2)
    - Stored in semantic_ai_insights table (NOT ai_scan_cache)

    Requirements: 5.2, 5.3
    """

    def __init__(self):
        """Initialize the service.

        Note: LLMGateway is imported lazily to avoid fork-safety issues
        with LiteLLM/aiohttp when used with Celery prefork pool.
        """
        self._llm = None

    def _get_llm(self):
        """Lazy load LLMGateway to avoid fork-safety issues."""
        if self._llm is None:
            from app.services.llm_gateway import get_llm_gateway
            self._llm = get_llm_gateway()
        return self._llm

    async def generate_insights(
        self,
        architecture_data: LLMReadyArchitectureData,
        repository_id: UUID,
        analysis_id: UUID,
    ) -> list[dict]:
        """Generate actionable insights from architecture findings.

        Uses LiteLLM directly via LLMGateway - does NOT use BroadScanAgent.

        Args:
            architecture_data: LLM-ready architecture analysis data
            repository_id: UUID of the repository
            analysis_id: UUID of the analysis

        Returns:
            List of insight dictionaries ready for database storage

        Requirements: 5.2, 5.3
        """
        logger.info(f"Generating semantic AI insights for analysis {analysis_id}")

        # Build prompt with architecture data
        prompt = self._build_insights_prompt(architecture_data)

        # Skip LLM call if no significant findings
        if (
            architecture_data.summary.dead_code_count == 0
            and architecture_data.summary.hot_spot_count == 0
        ):
            logger.info("No significant findings - skipping LLM call")
            return []

        max_retries = 2
        total_cost = 0.0

        for attempt in range(max_retries + 1):
            try:
                # Call LLM via gateway
                llm = self._get_llm()

                # Use temperature=1.0 for Gemini 3 models (recommended by LiteLLM)
                # Lower temperatures can cause degraded performance with Gemini 3
                model = llm.DEFAULT_MODELS["analysis"]
                is_gemini_3 = "gemini-3" in model or "gemini/gemini-3" in model
                temperature = 1.0 if is_gemini_3 else (0.2 if attempt == 0 else 0.5)

                response = await llm.chat(
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    model=llm.DEFAULT_MODELS["analysis"],
                    temperature=temperature,
                    max_tokens=2000,
                    response_format={"type": "json_object"},
                )

                total_cost += response.get("cost", 0)

                # Parse response
                content = response.get("content", "{}")
                insights = self._parse_insights(content, repository_id, analysis_id)

                if insights or attempt == max_retries:
                    logger.info(
                        f"Generated {len(insights)} insights for analysis {analysis_id}, "
                        f"cost: ${total_cost:.4f}"
                    )
                    return insights

                # No insights parsed, retry with different temperature
                logger.warning(
                    f"No insights parsed on attempt {attempt + 1}, retrying..."
                )

            except Exception as e:
                logger.error(
                    f"Failed to generate insights for analysis {analysis_id} "
                    f"(attempt {attempt + 1}): {e}"
                )
                if attempt == max_retries:
                    # Return empty list on final failure - don't block semantic cache
                    return []

        return []

    def _build_insights_prompt(self, data: LLMReadyArchitectureData) -> str:
        """Build prompt with architecture data for LLM.

        Uses ScoringService.select_llm_samples() to select the most impactful
        findings for LLM analysis. The selection algorithm:
        1. Takes top 50% from highest-scoring findings
        2. Fills remaining 50% with diversity sampling from different directories
        3. Falls back to next highest scores if diversity exhausted

        Args:
            data: LLM-ready architecture data

        Returns:
            Formatted prompt string

        Requirements: 4.1, 4.2, 4.3, 4.5
        """
        scoring_service = get_scoring_service()

        # Convert dataclasses to dicts for scoring and JSON serialization
        dead_code_dicts = [asdict(d) for d in data.dead_code]
        hot_spots_dicts = [asdict(h) for h in data.hot_spots]

        # Use score-based selection for dead code findings
        # The impact_score field is already calculated by CallGraphAnalyzer
        selected_dead_code = scoring_service.select_llm_samples(
            findings=dead_code_dicts,
            limit=15,
            score_key="impact_score",
            file_path_key="file_path",
        )

        # Use score-based selection for hot spot findings
        # The risk_score field is already calculated by GitAnalyzer
        selected_hot_spots = scoring_service.select_llm_samples(
            findings=hot_spots_dicts,
            limit=15,
            score_key="risk_score",
            file_path_key="file_path",
        )

        # Log selected findings and their scores for transparency
        if selected_dead_code:
            dead_code_scores = [
                f"{f.get('function_name', 'unknown')}:{f.get('impact_score', 0):.1f}"
                for f in selected_dead_code[:5]  # Log top 5
            ]
            logger.info(
                f"LLM dead code selection: {len(selected_dead_code)} findings "
                f"(top scores: {', '.join(dead_code_scores)})"
            )

        if selected_hot_spots:
            hot_spot_scores = [
                f"{f.get('file_path', 'unknown').split('/')[-1]}:{f.get('risk_score', 0):.1f}"
                for f in selected_hot_spots[:5]  # Log top 5
            ]
            logger.info(
                f"LLM hot spot selection: {len(selected_hot_spots)} findings "
                f"(top scores: {', '.join(hot_spot_scores)})"
            )

        return f"""Analyze this codebase and generate prioritized recommendations.

## Architecture Health Summary
- Health Score: {data.summary.health_score}/100
- Total Files: {data.summary.total_files}
- Total Functions: {data.summary.total_functions}
- Dead Code Count: {data.summary.dead_code_count}
- Hot Spot Count: {data.summary.hot_spot_count}
- Main Concerns: {data.summary.main_concerns}

## Dead Code Findings ({len(data.dead_code)} total, showing top {len(selected_dead_code)} by impact score)
{json.dumps(selected_dead_code, indent=2)}

## Hot Spot Findings ({len(data.hot_spots)} total, showing top {len(selected_hot_spots)} by risk score)
{json.dumps(selected_hot_spots, indent=2)}

Generate 3-5 prioritized recommendations based on these findings.
Focus on the most impactful issues that developers should address first.
"""

    def _parse_insights(
        self,
        content: str,
        repository_id: UUID,
        analysis_id: UUID,
    ) -> list[dict]:
        """Parse LLM response into insight dictionaries.

        Args:
            content: JSON string from LLM response
            repository_id: UUID of the repository
            analysis_id: UUID of the analysis

        Returns:
            List of insight dictionaries ready for database storage
        """
        # Log the raw content for debugging
        logger.debug(f"Raw LLM response (first 500 chars): {content[:500]}")

        try:
            # Try to repair common JSON issues before parsing
            repaired_content = self._repair_json(content)
            logger.debug(f"Repaired content (first 500 chars): {repaired_content[:500]}")

            parsed = json.loads(repaired_content)
            # Handle null, non-dict, or missing recommendations key
            if not isinstance(parsed, dict):
                logger.warning(f"Parsed content is not a dict: {type(parsed)}")
                return []

            recommendations = parsed.get("recommendations", [])
            if not recommendations:
                logger.warning("No 'recommendations' key found in parsed JSON")
                return []

            insights = []
            for i, rec in enumerate(recommendations):
                # Validate required fields
                if not rec.get("title") or not rec.get("description"):
                    logger.warning(f"Skipping recommendation {i}: missing title or description")
                    continue

                insight = {
                    "repository_id": repository_id,
                    "analysis_id": analysis_id,
                    "insight_type": self._normalize_insight_type(rec.get("insight_type", "architecture")),
                    "title": rec.get("title", ""),
                    "description": rec.get("description", ""),
                    "priority": self._normalize_priority(rec.get("priority", "medium")),
                    "affected_files": rec.get("affected_files", []),
                    "evidence": rec.get("evidence"),
                    "suggested_action": rec.get("suggested_action"),
                }
                insights.append(insight)

            logger.info(f"Successfully parsed {len(insights)} insights from LLM response")
            return insights

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response as JSON: {e}")
            logger.debug(f"Failed content: {content}")
            # Try to extract partial insights from malformed JSON
            return self._extract_partial_insights(content, repository_id, analysis_id)

    def _repair_json(self, content: str) -> str:
        """Attempt to repair common JSON issues from LLM responses.

        Args:
            content: Potentially malformed JSON string

        Returns:
            Repaired JSON string
        """
        import re

        # Strip markdown code blocks if present
        if content.startswith("```"):
            lines = content.split("\n")
            # Remove first line (```json) and last line (```)
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines)

        # Strip any leading/trailing whitespace
        content = content.strip()

        # Remove trailing commas before ] or }
        content = re.sub(r',\s*([}\]])', r'\1', content)

        # Fix unterminated strings by finding unclosed quotes
        # Build a new string character by character, tracking quote state
        result = []
        in_string = False
        escaped = False

        for i, char in enumerate(content):
            if escaped:
                escaped = False
                result.append(char)
                continue

            if char == '\\':
                escaped = True
                result.append(char)
                continue

            if char == '"':
                in_string = not in_string
                result.append(char)
                continue

            # If we're in a string and hit a newline, check if it's valid
            if in_string and char == '\n':
                # Look ahead to see if this looks like the start of a new JSON key
                remaining = content[i+1:].lstrip()
                if remaining.startswith('"') and ':' in remaining[:50]:
                    # This looks like we forgot to close the string
                    # Close it and add a comma before the newline
                    result.append('",')
                    in_string = False
                    result.append(char)
                    continue

            result.append(char)

        # If we ended inside a string, close it
        if in_string:
            result.append('"')

        content = ''.join(result)

        # Try to close unclosed brackets/braces
        open_braces = content.count('{') - content.count('}')
        open_brackets = content.count('[') - content.count(']')

        if open_braces > 0:
            content += '}' * open_braces
        if open_brackets > 0:
            content += ']' * open_brackets

        return content

    def _extract_partial_insights(
        self,
        content: str,
        repository_id: UUID,
        analysis_id: UUID,
    ) -> list[dict]:
        """Extract partial insights from malformed JSON using regex.

        Args:
            content: Malformed JSON string
            repository_id: UUID of the repository
            analysis_id: UUID of the analysis

        Returns:
            List of partially extracted insights
        """
        import re

        insights = []

        # Strategy 1: Try to find complete recommendation objects
        # Look for patterns like {"insight_type": ..., "title": ..., ...}
        # Use a more flexible pattern that handles multiline strings
        pattern = r'\{[^{}]*?"title"\s*:\s*"([^"]*?)"[^{}]*?"description"\s*:\s*"([^"]*?)"[^{}]*?\}'

        for match in re.finditer(pattern, content, re.DOTALL):
            try:
                title = match.group(1).strip()
                description = match.group(2).strip()

                if not title or not description:
                    continue

                # Try to extract other fields
                full_match = match.group(0)

                priority_match = re.search(r'"priority"\s*:\s*"([^"]+)"', full_match)
                priority = priority_match.group(1) if priority_match else "medium"

                insight_type_match = re.search(r'"insight_type"\s*:\s*"([^"]+)"', full_match)
                insight_type = insight_type_match.group(1) if insight_type_match else "architecture"

                # Try to extract affected_files array
                affected_files = []
                files_match = re.search(r'"affected_files"\s*:\s*\[(.*?)\]', full_match, re.DOTALL)
                if files_match:
                    files_str = files_match.group(1)
                    # Extract quoted strings
                    file_matches = re.findall(r'"([^"]+)"', files_str)
                    affected_files = file_matches

                # Try to extract evidence
                evidence_match = re.search(r'"evidence"\s*:\s*"([^"]*?)"', full_match, re.DOTALL)
                evidence = evidence_match.group(1) if evidence_match else None

                # Try to extract suggested_action
                action_match = re.search(r'"suggested_action"\s*:\s*"([^"]*?)"', full_match, re.DOTALL)
                suggested_action = action_match.group(1) if action_match else None

                insight = {
                    "repository_id": repository_id,
                    "analysis_id": analysis_id,
                    "insight_type": self._normalize_insight_type(insight_type),
                    "title": title,
                    "description": description,
                    "priority": self._normalize_priority(priority),
                    "affected_files": affected_files,
                    "evidence": evidence,
                    "suggested_action": suggested_action,
                }
                insights.append(insight)
                logger.info(f"Extracted partial insight: {title}")
            except Exception as e:
                logger.debug(f"Failed to extract insight from match: {e}")
                continue

        # Strategy 2: If no insights found, try a simpler pattern
        if not insights:
            logger.info("Trying simpler extraction pattern...")
            # Just look for title and description pairs
            simple_pattern = r'"title"\s*:\s*"([^"]+)".*?"description"\s*:\s*"([^"]+)"'
            for match in re.finditer(simple_pattern, content, re.DOTALL):
                try:
                    title = match.group(1).strip()
                    description = match.group(2).strip()

                    if title and description:
                        insight = {
                            "repository_id": repository_id,
                            "analysis_id": analysis_id,
                            "insight_type": "architecture",
                            "title": title,
                            "description": description,
                            "priority": "medium",
                            "affected_files": [],
                            "evidence": None,
                            "suggested_action": None,
                        }
                        insights.append(insight)
                        logger.info(f"Extracted simple insight: {title}")
                except Exception as e:
                    logger.debug(f"Failed to extract simple insight: {e}")
                    continue

        if insights:
            logger.info(f"Recovered {len(insights)} insights from malformed JSON")
        else:
            logger.error("Failed to extract any insights from malformed JSON")
            logger.debug(f"Content preview: {content[:1000]}")

        return insights

    def _normalize_priority(self, priority: str) -> str:
        """Normalize priority string to valid enum value.

        Args:
            priority: Priority string from LLM

        Returns:
            Normalized priority: 'high', 'medium', or 'low'
        """
        priority_lower = priority.lower().strip()
        if priority_lower in ("high", "critical", "urgent"):
            return "high"
        elif priority_lower in ("low", "minor", "trivial"):
            return "low"
        return "medium"

    def _normalize_insight_type(self, insight_type: str) -> str:
        """Normalize insight_type to valid enum value.

        The database constraint only allows: 'dead_code', 'hot_spot', 'architecture'.
        Map any other LLM-generated types to the closest valid value.

        Args:
            insight_type: Insight type string from LLM

        Returns:
            Normalized insight_type: 'dead_code', 'hot_spot', or 'architecture'
        """
        type_lower = insight_type.lower().strip().replace("-", "_").replace(" ", "_")

        # Direct matches
        if type_lower in ("dead_code", "deadcode", "unused_code", "unreachable_code"):
            return "dead_code"
        elif type_lower in ("hot_spot", "hotspot", "churn", "high_churn", "code_churn"):
            return "hot_spot"
        elif type_lower in ("architecture", "architectural", "design", "structure"):
            return "architecture"

        # Map other common LLM-generated types to architecture (catch-all)
        # These are valid concerns but don't fit dead_code or hot_spot
        logger.debug(f"Mapping unknown insight_type '{insight_type}' to 'architecture'")
        return "architecture"


def get_semantic_ai_insights_service() -> SemanticAIInsightsService:
    """Get SemanticAIInsightsService instance."""
    return SemanticAIInsightsService()
