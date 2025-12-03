"""Test Agent - Generates tests for code fixes."""

import logging
import re
from dataclasses import dataclass

from app.services.agents.fix import FixResult
from app.services.llm_gateway import get_llm_gateway

logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """Result of test generation."""
    issue_id: str
    success: bool
    test_file_path: str
    test_content: str
    test_framework: str
    test_count: int
    explanation: str


class TestAgent:
    """Agent that generates tests for code fixes."""

    # Test framework detection patterns
    FRAMEWORK_PATTERNS = {
        "pytest": ["pytest", "import pytest", "from pytest"],
        "jest": ["jest", "describe(", "it(", "test(", "@jest"],
        "mocha": ["mocha", "describe(", "it("],
        "unittest": ["unittest", "TestCase", "self.assert"],
        "vitest": ["vitest", "describe(", "it(", "expect("],
    }

    def __init__(self):
        self.llm = get_llm_gateway()

    async def generate_test(
        self,
        fix_result: FixResult,
        issue: dict,
        existing_tests: str | None = None,
    ) -> TestResult:
        """
        Generate a regression test for the fix.
        
        Args:
            fix_result: FixResult from FixAgent
            issue: Original issue dict
            existing_tests: Content of existing test file if any
        
        Returns:
            TestResult with generated test
        """
        logger.info(f"Generating test for fix {fix_result.issue_id}")

        # Detect test framework
        framework = self._detect_framework(fix_result.file_path, existing_tests)

        # Generate test based on framework
        result = await self._generate_test_code(
            fix_result,
            issue,
            framework,
            existing_tests,
        )

        # Determine test file path
        test_file_path = self._get_test_file_path(fix_result.file_path, framework)

        return TestResult(
            issue_id=fix_result.issue_id,
            success=result["success"],
            test_file_path=test_file_path,
            test_content=result["test_content"],
            test_framework=framework,
            test_count=result["test_count"],
            explanation=result["explanation"],
        )

    def _detect_framework(
        self,
        file_path: str,
        existing_tests: str | None,
    ) -> str:
        """Detect the test framework to use."""
        # Check file extension for language
        if file_path.endswith(('.py',)):
            if existing_tests:
                if 'pytest' in existing_tests or '@pytest' in existing_tests:
                    return 'pytest'
                if 'unittest' in existing_tests or 'TestCase' in existing_tests:
                    return 'unittest'
            return 'pytest'  # Default for Python

        elif file_path.endswith(('.ts', '.tsx', '.js', '.jsx')):
            if existing_tests:
                if 'vitest' in existing_tests:
                    return 'vitest'
                if 'jest' in existing_tests or '@jest' in existing_tests:
                    return 'jest'
            return 'jest'  # Default for JS/TS

        return 'pytest'  # Fallback

    def _get_test_file_path(self, file_path: str, framework: str) -> str:
        """Generate test file path from source file path."""
        import os

        dirname = os.path.dirname(file_path)
        filename = os.path.basename(file_path)
        name, ext = os.path.splitext(filename)

        if framework in ('pytest', 'unittest'):
            # Python: test_filename.py
            return os.path.join(dirname, f"test_{name}{ext}")
        else:
            # JS/TS: filename.test.ts or filename.spec.ts
            return os.path.join(dirname, f"{name}.test{ext}")

    async def _generate_test_code(
        self,
        fix_result: FixResult,
        issue: dict,
        framework: str,
        existing_tests: str | None,
    ) -> dict:
        """Generate test code using LLM."""
        framework_instructions = self._get_framework_instructions(framework)

        prompt = f"""Generate a regression test for the following code fix.

## Issue Fixed
Type: {issue.get('type', 'unknown')}
Title: {issue.get('title', 'No title')}
Description: {issue.get('description', '')}

## Fix Applied
File: {fix_result.file_path}
Changes: {', '.join(fix_result.changes_summary)}

## Fixed Code
```
{fix_result.fixed_content[:3000]}
```

## Diff
```diff
{fix_result.diff[:2000]}
```

## Test Framework
{framework_instructions}

{"## Existing Tests" + chr(10) + "```" + chr(10) + existing_tests[:2000] + chr(10) + "```" if existing_tests else ""}

## Instructions
1. Generate a test that verifies the fix works correctly
2. Test the specific behavior that was fixed
3. Include edge cases if appropriate
4. Follow the existing test patterns if provided
5. Make the test independent and idempotent

Respond with:
TEST_CODE:
```
[Complete test file content]
```

TEST_COUNT: [number of test cases]

EXPLANATION:
[What the tests verify]
"""

        try:
            response = await self.llm.complete(
                prompt=prompt,
                temperature=0.2,
                max_tokens=3000,
            )
            return self._parse_test_response(response)
        except Exception as e:
            logger.error(f"Test generation failed: {e}")
            return {
                "success": False,
                "test_content": "",
                "test_count": 0,
                "explanation": f"Test generation failed: {e}",
            }

    def _get_framework_instructions(self, framework: str) -> str:
        """Get framework-specific instructions."""
        instructions = {
            "pytest": """Use pytest framework:
- Use `def test_*` function names
- Use pytest fixtures if needed
- Use `assert` statements
- Import the module being tested""",

            "unittest": """Use unittest framework:
- Create a class inheriting from unittest.TestCase
- Use `def test_*` methods
- Use self.assert* methods
- Import the module being tested""",

            "jest": """Use Jest framework:
- Use describe() blocks to group tests
- Use it() or test() for test cases
- Use expect() for assertions
- Import the module being tested""",

            "vitest": """Use Vitest framework:
- Use describe() blocks to group tests
- Use it() or test() for test cases
- Use expect() for assertions
- Import from 'vitest' and the module being tested""",
        }
        return instructions.get(framework, instructions["pytest"])

    def _parse_test_response(self, response: str) -> dict:
        """Parse the LLM test response."""
        result = {
            "success": False,
            "test_content": "",
            "test_count": 0,
            "explanation": "",
        }

        # Extract test code
        code_match = re.search(r'TEST_CODE:\s*```[\w]*\n(.*?)```', response, re.DOTALL)
        if code_match:
            result["test_content"] = code_match.group(1).strip()
            result["success"] = bool(result["test_content"])

        # Extract test count
        count_match = re.search(r'TEST_COUNT:\s*(\d+)', response)
        if count_match:
            result["test_count"] = int(count_match.group(1))
        else:
            # Count test functions
            content = result["test_content"]
            result["test_count"] = len(re.findall(r'def test_|it\(|test\(', content))

        # Extract explanation
        explanation_match = re.search(r'EXPLANATION:\s*(.*?)$', response, re.DOTALL)
        if explanation_match:
            result["explanation"] = explanation_match.group(1).strip()

        return result
