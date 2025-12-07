"""Fix Agent - Generates code fixes for issues with retry support."""

import logging
import re
from dataclasses import dataclass

from qdrant_client import QdrantClient

from app.core.config import settings
from app.services.agents.diagnosis import DiagnosisResult, FixPath
from app.services.llm_gateway import get_llm_gateway

logger = logging.getLogger(__name__)


@dataclass
class FixResult:
    """Result of code fix generation."""
    issue_id: str
    success: bool
    file_path: str
    original_content: str
    fixed_content: str
    diff: str
    explanation: str
    confidence: float
    changes_summary: list[str]
    iteration: int = 1  # Track which iteration generated this fix


class FixAgent:
    """Agent that generates code fixes for issues with retry support."""

    COLLECTION_NAME = "code_embeddings"

    def __init__(self):
        self.llm = get_llm_gateway()
        self.qdrant = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            timeout=settings.qdrant_timeout,
        )

    async def generate_fix(
        self,
        diagnosis: DiagnosisResult,
        issue: dict,
        file_content: str,
        repository_id: str,
        previous_error: str | None = None,
        iteration: int = 1,
    ) -> FixResult:
        """
        Generate a code fix based on the diagnosis.

        Args:
            diagnosis: DiagnosisResult from DiagnosisAgent
            issue: Original issue dict
            file_content: Content of the file to fix
            repository_id: Repository UUID for RAG context
            previous_error: Error from previous fix attempt (for retry)
            iteration: Current iteration number (1-based)

        Returns:
            FixResult with the generated fix
        """
        logger.info(f"Generating fix for issue {diagnosis.issue_id} (iteration {iteration})")

        # Get RAG context for related code
        rag_context = await self._get_rag_context(
            repository_id,
            issue,
            diagnosis.context_needed,
        )

        # Generate fix based on fix path
        if diagnosis.fix_path == FixPath.PATH_A:
            result = await self._generate_simple_fix(
                issue, file_content, rag_context, previous_error, iteration
            )
        elif diagnosis.fix_path == FixPath.PATH_B:
            result = await self._generate_complex_fix(
                issue, file_content, rag_context, diagnosis, previous_error, iteration
            )
        else:
            # PATH_C and PATH_D - provide suggestions only
            result = await self._generate_suggestions(
                issue, file_content, rag_context, diagnosis
            )

        return FixResult(
            issue_id=diagnosis.issue_id,
            success=result["success"],
            file_path=issue.get("file_path", "unknown"),
            original_content=file_content,
            fixed_content=result["fixed_content"],
            diff=self._generate_diff(file_content, result["fixed_content"]),
            explanation=result["explanation"],
            confidence=result["confidence"],
            changes_summary=result["changes"],
            iteration=iteration,
        )

    async def _get_rag_context(
        self,
        repository_id: str,
        issue: dict,
        context_files: list[str],
    ) -> str:
        """Retrieve relevant code context from Qdrant."""
        context_parts = []

        # Build query from issue
        query = f"{issue.get('type', '')} {issue.get('title', '')} {issue.get('description', '')}"

        try:
            # Generate embedding for query
            query_embedding = await self.llm.embed([query])

            # Search for relevant code
            results = self.qdrant.search(
                collection_name=self.COLLECTION_NAME,
                query_vector=query_embedding[0],
                query_filter={
                    "must": [
                        {"key": "repository_id", "match": {"value": repository_id}}
                    ]
                },
                limit=5,
            )

            for hit in results:
                payload = hit.payload
                context_parts.append(f"### {payload.get('file_path', 'unknown')}")
                if payload.get("name"):
                    context_parts.append(f"Function/Class: {payload['name']}")
                context_parts.append(f"```\n{payload.get('content', '')[:1500]}\n```\n")

        except Exception as e:
            logger.warning(f"RAG context retrieval failed: {e}")

        return "\n".join(context_parts) if context_parts else "No additional context available."

    def _build_error_context(self, previous_error: str | None, iteration: int) -> str:
        """Build error context string for retry attempts."""
        if not previous_error or iteration == 1:
            return ""

        return f"""
## ⚠️ PREVIOUS ATTEMPT FAILED (Iteration {iteration - 1})

Your previous fix attempt resulted in the following error. Please analyze it carefully and provide a corrected fix:

```
{previous_error[:3000]}
```

### Instructions for Retry:
1. Carefully analyze the error message above
2. Identify what went wrong with the previous fix
3. DO NOT repeat the same mistake
4. If it was a syntax error, ensure proper syntax
5. If tests failed, ensure the logic is correct
6. Consider edge cases that might have caused the failure
"""

    async def _generate_simple_fix(
        self,
        issue: dict,
        file_content: str,
        rag_context: str,
        previous_error: str | None = None,
        iteration: int = 1,
    ) -> dict:
        """Generate a simple, high-confidence fix."""
        error_context = self._build_error_context(previous_error, iteration)

        iteration_note = ""
        if iteration > 1:
            iteration_note = f"\n\n**This is retry attempt {iteration}. Please fix the errors from the previous attempt.**\n"

        prompt = f"""Fix the following code issue. Make minimal, targeted changes.
{iteration_note}
{error_context}

## Issue
Type: {issue.get('type', 'unknown')}
Title: {issue.get('title', 'No title')}
Description: {issue.get('description', '')}
File: {issue.get('file_path', 'unknown')}
Lines: {issue.get('line_start', '?')}-{issue.get('line_end', '?')}

## Current Code
```
{file_content}
```

## Related Code Context
{rag_context}

## Instructions
1. Fix ONLY the specific issue mentioned
2. Make minimal changes - do not refactor unrelated code
3. Preserve the existing code style
4. Add comments only if necessary for clarity
5. ENSURE the code is syntactically correct
6. Test your fix mentally before responding

Respond with:
FIXED_CODE:
```
[The complete fixed file content]
```

EXPLANATION:
[Brief explanation of the fix]

CHANGES:
- [Change 1]
- [Change 2]
"""

        try:
            response = await self.llm.complete(
                prompt=prompt,
                temperature=0.1 if iteration == 1 else 0.2,  # Slightly more creative on retries
                max_tokens=4000,
            )
            return self._parse_fix_response(response, file_content)
        except Exception as e:
            logger.error(f"Fix generation failed: {e}")
            return {
                "success": False,
                "fixed_content": file_content,
                "explanation": f"Fix generation failed: {e}",
                "changes": [],
                "confidence": 0.0,
            }

    async def _generate_complex_fix(
        self,
        issue: dict,
        file_content: str,
        rag_context: str,
        diagnosis: DiagnosisResult,
        previous_error: str | None = None,
        iteration: int = 1,
    ) -> dict:
        """Generate a more complex fix with additional considerations."""
        error_context = self._build_error_context(previous_error, iteration)

        iteration_note = ""
        if iteration > 1:
            iteration_note = f"\n\n**⚠️ RETRY ATTEMPT {iteration}: The previous fix failed. Please carefully review the error and provide a corrected solution.**\n"

        prompt = f"""Fix the following code issue. This is a complex fix that requires careful consideration.
{iteration_note}
{error_context}

## Issue
Type: {issue.get('type', 'unknown')}
Title: {issue.get('title', 'No title')}
Description: {issue.get('description', '')}
File: {issue.get('file_path', 'unknown')}
Lines: {issue.get('line_start', '?')}-{issue.get('line_end', '?')}

## Diagnosis
Fix Strategy: {diagnosis.fix_description}
Risk Factors: {', '.join(diagnosis.risk_factors)}
Complexity: {diagnosis.complexity_score}/10

## Current Code
```
{file_content}
```

## Related Code Context
{rag_context}

## Instructions
1. Fix the issue while considering the risk factors
2. Ensure the fix doesn't break existing functionality
3. Add appropriate error handling if needed
4. Add comments explaining complex changes
5. Follow existing code patterns from the context
6. VERIFY syntax is correct before responding
7. Consider all edge cases

Respond with:
FIXED_CODE:
```
[The complete fixed file content]
```

EXPLANATION:
[Detailed explanation of the fix and why this approach was chosen]

CHANGES:
- [Change 1]
- [Change 2]

CONSIDERATIONS:
[Any additional considerations for the reviewer]
"""

        try:
            response = await self.llm.complete(
                prompt=prompt,
                temperature=0.2 if iteration == 1 else 0.3,  # More creative on retries
                max_tokens=4000,
            )
            result = self._parse_fix_response(response, file_content)
            # Lower confidence for complex fixes, even more for retries
            max_confidence = 0.85 if iteration == 1 else 0.80
            result["confidence"] = min(result["confidence"], max_confidence)
            return result
        except Exception as e:
            logger.error(f"Complex fix generation failed: {e}")
            return {
                "success": False,
                "fixed_content": file_content,
                "explanation": f"Fix generation failed: {e}",
                "changes": [],
                "confidence": 0.0,
            }

    async def _generate_suggestions(
        self,
        issue: dict,
        file_content: str,
        rag_context: str,
        diagnosis: DiagnosisResult,
    ) -> dict:
        """Generate suggestions for manual fixes."""
        prompt = f"""Analyze this code issue and provide detailed suggestions for fixing it.
This issue is too complex for automatic fixing, so provide guidance for manual fix.

## Issue
Type: {issue.get('type', 'unknown')}
Title: {issue.get('title', 'No title')}
Description: {issue.get('description', '')}
File: {issue.get('file_path', 'unknown')}

## Diagnosis
Fix Strategy: {diagnosis.fix_description}
Risk Factors: {', '.join(diagnosis.risk_factors)}
Complexity: {diagnosis.complexity_score}/10

## Current Code
```
{file_content[:3000]}
```

## Related Code Context
{rag_context}

Provide detailed suggestions:
1. What needs to change and why
2. Step-by-step approach to fix
3. Files that might need changes
4. Testing considerations
"""

        try:
            response = await self.llm.complete(
                prompt=prompt,
                temperature=0.3,
                max_tokens=2000,
            )
            return {
                "success": False,
                "fixed_content": file_content,
                "explanation": response,
                "changes": ["Manual review required"],
                "confidence": 0.0,
            }
        except Exception:
            return {
                "success": False,
                "fixed_content": file_content,
                "explanation": "Unable to generate suggestions",
                "changes": [],
                "confidence": 0.0,
            }

    def _parse_fix_response(self, response: str, original_content: str) -> dict:
        """Parse the LLM fix response."""
        result = {
            "success": False,
            "fixed_content": original_content,
            "explanation": "",
            "changes": [],
            "confidence": 0.0,
        }

        # Extract fixed code
        code_match = re.search(r'FIXED_CODE:\s*```[\w]*\n(.*?)```', response, re.DOTALL)
        if code_match:
            result["fixed_content"] = code_match.group(1).strip()
            result["success"] = result["fixed_content"] != original_content

        # Extract explanation
        explanation_match = re.search(r'EXPLANATION:\s*(.*?)(?=CHANGES:|CONSIDERATIONS:|$)', response, re.DOTALL)
        if explanation_match:
            result["explanation"] = explanation_match.group(1).strip()

        # Extract changes
        changes_match = re.search(r'CHANGES:\s*(.*?)(?=CONSIDERATIONS:|$)', response, re.DOTALL)
        if changes_match:
            changes_text = changes_match.group(1)
            result["changes"] = [
                line.strip().lstrip('- ')
                for line in changes_text.split('\n')
                if line.strip() and line.strip() != '-'
            ]

        # Calculate confidence based on response quality
        if result["success"]:
            confidence = 0.7
            if result["explanation"]:
                confidence += 0.1
            if result["changes"]:
                confidence += 0.1
            if len(result["changes"]) >= 2:
                confidence += 0.05
            result["confidence"] = min(confidence, 0.95)

        return result

    def _generate_diff(self, original: str, fixed: str) -> str:
        """Generate a unified diff between original and fixed content."""
        import difflib

        original_lines = original.splitlines(keepends=True)
        fixed_lines = fixed.splitlines(keepends=True)

        diff = difflib.unified_diff(
            original_lines,
            fixed_lines,
            fromfile='original',
            tofile='fixed',
            lineterm='',
        )

        return ''.join(diff)
