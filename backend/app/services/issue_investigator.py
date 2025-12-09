"""Issue Investigator for AI Scan.

Tool-calling agent that validates high-severity issues by investigating
the codebase with read_file, search, and cli_run tools.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.issue_merger import MergedIssue
from app.services.llm_gateway import LLMError, LLMGateway
from app.services.sandbox import Sandbox

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Maximum iterations for tool-calling loop to prevent infinite loops
MAX_INVESTIGATION_ITERATIONS = 10

# Maximum file content to return from read_file
MAX_FILE_CONTENT_CHARS = 50000

# Maximum search results to return
MAX_SEARCH_RESULTS = 20

# Maximum CLI output to return
MAX_CLI_OUTPUT_CHARS = 10000


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class InvestigationResult:
    """Result of investigating a single issue.

    Contains the investigation outcome including status classification,
    technical notes gathered during investigation, and suggested fixes.

    Attributes:
        status: Classification of the issue after investigation
            - confirmed: Issue is definitely real and verified
            - likely_real: Issue appears real but couldn't be 100% verified
            - uncertain: Unable to determine if issue is real
            - invalid: Issue is a false positive
        technical_notes: List of observations made during investigation
        suggested_fix: Suggested code fix or remediation approach
        commands_executed: List of CLI commands that were run
        files_examined: List of files that were read during investigation
        iterations_used: Number of tool-calling iterations used
    """
    status: str  # confirmed | likely_real | uncertain | invalid
    technical_notes: list[str] = field(default_factory=list)
    suggested_fix: str | None = None
    commands_executed: list[str] = field(default_factory=list)
    files_examined: list[str] = field(default_factory=list)
    iterations_used: int = 0


@dataclass
class ToolCall:
    """Represents a tool call request from the LLM.

    Attributes:
        name: Name of the tool to call (read_file, search, cli_run)
        arguments: Dictionary of arguments for the tool
    """
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    """Result from executing a tool.

    Attributes:
        tool_name: Name of the tool that was executed
        success: Whether the tool execution succeeded
        output: Output from the tool (content, search results, or CLI output)
        error: Error message if execution failed
    """
    tool_name: str
    success: bool
    output: str
    error: str | None = None


# =============================================================================
# Tool Definitions
# =============================================================================

TOOL_DEFINITIONS = [
    {
        "name": "read_file",
        "description": "Read the content of a file from the repository. Use this to examine source code, configuration files, or any other text files.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file relative to repository root (e.g., 'src/main.py', 'config/settings.json')"
                },
                "start_line": {
                    "type": "integer",
                    "description": "Optional starting line number (1-indexed). If omitted, reads from beginning."
                },
                "end_line": {
                    "type": "integer",
                    "description": "Optional ending line number (1-indexed, inclusive). If omitted, reads to end."
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "search",
        "description": "Search for text patterns across the repository. Use this to find usages, definitions, or patterns in the codebase.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (supports basic regex patterns)"
                },
                "file_pattern": {
                    "type": "string",
                    "description": "Optional glob pattern to filter files (e.g., '*.py', 'src/**/*.ts')"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "cli_run",
        "description": "Execute a command in a sandboxed environment. Use this for running analysis tools, checking dependencies, or other safe operations. Network access is disabled for security.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute (e.g., 'grep -r \"pattern\" .', 'cat package.json | jq .dependencies')"
                }
            },
            "required": ["command"]
        }
    },
    {
        "name": "finish_investigation",
        "description": "Complete the investigation and provide final assessment. Call this when you have gathered enough information to make a determination.",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["confirmed", "likely_real", "uncertain", "invalid"],
                    "description": "Final status: 'confirmed' (verified real issue), 'likely_real' (probably real), 'uncertain' (can't determine), 'invalid' (false positive)"
                },
                "technical_notes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of technical observations and findings from the investigation"
                },
                "suggested_fix": {
                    "type": "string",
                    "description": "Suggested code fix or remediation approach. Include specific code changes if possible."
                }
            },
            "required": ["status", "technical_notes"]
        }
    }
]


# =============================================================================
# Investigation System Prompt
# =============================================================================

INVESTIGATION_SYSTEM_PROMPT = """You are an expert code security analyst investigating a potential issue in a software repository.

## Your Task

You have been given a candidate issue identified by an AI code scanner. Your job is to:
1. Investigate the issue by examining the relevant code
2. Determine if the issue is real or a false positive
3. Provide technical notes explaining your findings
4. Suggest a fix if the issue is confirmed

## Available Tools

You have access to the following tools:

1. **read_file(path, start_line?, end_line?)**: Read file content from the repository
2. **search(query, file_pattern?)**: Search for patterns across the codebase
3. **cli_run(command)**: Execute shell commands in a sandboxed environment (no network access)
4. **finish_investigation(status, technical_notes, suggested_fix?)**: Complete the investigation

## Investigation Guidelines

1. Start by reading the files mentioned in the issue
2. Search for related patterns or usages if needed
3. Consider the context - is this a test file, example code, or production code?
4. Look for mitigating factors that might make the issue less severe
5. Check if the issue is already handled elsewhere in the code

## Status Classifications

- **confirmed**: You have verified the issue is real and exploitable/problematic
- **likely_real**: The issue appears real based on evidence, but you couldn't fully verify
- **uncertain**: You couldn't gather enough information to make a determination
- **invalid**: The issue is a false positive (e.g., handled elsewhere, test code, not actually vulnerable)

## Output Format

After investigating, call the finish_investigation tool with your findings.

Be thorough but efficient - don't make unnecessary tool calls. Focus on gathering the evidence needed to make a determination."""


# =============================================================================
# IssueInvestigator Class
# =============================================================================


class IssueInvestigator:
    """Tool-calling agent for issue investigation.

    Uses an LLM with tool-calling capabilities to investigate issues
    by reading files, searching code, and running commands in a sandbox.

    Attributes:
        llm: LLMGateway instance for making LLM calls
        repo_path: Path to the cloned repository
        sandbox: Optional Sandbox instance for CLI commands
        model: LLM model to use for investigation
    """

    def __init__(
        self,
        llm_gateway: LLMGateway,
        repo_path: Path,
        sandbox: Sandbox | None = None,
        model: str = "bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0",
    ):
        """Initialize the IssueInvestigator.

        Args:
            llm_gateway: LLMGateway instance for making LLM calls
            repo_path: Path to the cloned repository
            sandbox: Optional Sandbox for executing CLI commands
            model: LLM model to use for investigation
        """
        self.llm = llm_gateway
        self.repo_path = Path(repo_path)
        self.sandbox = sandbox
        self.model = model

    def _build_issue_prompt(self, issue: MergedIssue) -> str:
        """Build the investigation prompt for an issue.

        Args:
            issue: MergedIssue to investigate

        Returns:
            Formatted prompt string
        """
        files_str = "\n".join(
            f"  - {f.get('path', 'unknown')} (lines {f.get('line_start', '?')}-{f.get('line_end', '?')})"
            for f in issue.files
        ) if issue.files else "  (no specific files mentioned)"

        evidence_str = "\n".join(
            f"```\n{snippet}\n```"
            for snippet in issue.evidence_snippets[:3]  # Limit to 3 snippets
        ) if issue.evidence_snippets else "(no evidence snippets provided)"

        return f"""## Issue to Investigate

**ID**: {issue.id}
**Dimension**: {issue.dimension}
**Severity**: {issue.severity}
**Confidence**: {issue.confidence}
**Found by**: {', '.join(issue.found_by_models)}

### Summary
{issue.summary}

### Affected Files
{files_str}

### Evidence Snippets
{evidence_str}

---

Please investigate this issue using the available tools and determine if it's a real problem or a false positive."""


    async def _execute_read_file(
        self,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> ToolResult:
        """Execute read_file tool.

        Args:
            path: File path relative to repo root
            start_line: Optional starting line (1-indexed)
            end_line: Optional ending line (1-indexed, inclusive)

        Returns:
            ToolResult with file content or error
        """
        try:
            file_path = self.repo_path / path

            # Security check - ensure path is within repo
            try:
                file_path.resolve().relative_to(self.repo_path.resolve())
            except ValueError:
                return ToolResult(
                    tool_name="read_file",
                    success=False,
                    output="",
                    error=f"Path traversal attempt blocked: {path}"
                )

            if not file_path.exists():
                return ToolResult(
                    tool_name="read_file",
                    success=False,
                    output="",
                    error=f"File not found: {path}"
                )

            if not file_path.is_file():
                return ToolResult(
                    tool_name="read_file",
                    success=False,
                    output="",
                    error=f"Not a file: {path}"
                )

            # Read file content
            content = file_path.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines(keepends=True)

            # Apply line range if specified
            if start_line is not None or end_line is not None:
                start_idx = (start_line - 1) if start_line else 0
                end_idx = end_line if end_line else len(lines)
                lines = lines[start_idx:end_idx]
                content = "".join(lines)

            # Truncate if too large
            if len(content) > MAX_FILE_CONTENT_CHARS:
                content = content[:MAX_FILE_CONTENT_CHARS] + "\n\n[... truncated ...]"

            return ToolResult(
                tool_name="read_file",
                success=True,
                output=content,
            )

        except Exception as e:
            logger.error(f"Error reading file {path}: {e}")
            return ToolResult(
                tool_name="read_file",
                success=False,
                output="",
                error=str(e)
            )

    async def _execute_search(
        self,
        query: str,
        file_pattern: str | None = None,
    ) -> ToolResult:
        """Execute search tool using grep.

        Args:
            query: Search pattern (basic regex)
            file_pattern: Optional glob pattern for files

        Returns:
            ToolResult with search results or error
        """
        try:
            import subprocess

            # Build grep command
            cmd = ["grep", "-rn", "--include=*"]

            if file_pattern:
                cmd = ["grep", "-rn", f"--include={file_pattern}"]

            cmd.extend([query, str(self.repo_path)])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(self.repo_path),
            )

            output = result.stdout

            # Limit results
            lines = output.splitlines()
            if len(lines) > MAX_SEARCH_RESULTS:
                output = "\n".join(lines[:MAX_SEARCH_RESULTS])
                output += f"\n\n[... {len(lines) - MAX_SEARCH_RESULTS} more results truncated ...]"

            if not output.strip():
                output = "(no matches found)"

            return ToolResult(
                tool_name="search",
                success=True,
                output=output,
            )

        except subprocess.TimeoutExpired:
            return ToolResult(
                tool_name="search",
                success=False,
                output="",
                error="Search timed out after 30 seconds"
            )
        except Exception as e:
            logger.error(f"Error searching for '{query}': {e}")
            return ToolResult(
                tool_name="search",
                success=False,
                output="",
                error=str(e)
            )

    async def _execute_cli_run(self, command: str) -> ToolResult:
        """Execute cli_run tool in sandbox.

        Args:
            command: Shell command to execute

        Returns:
            ToolResult with command output or error
        """
        if not self.sandbox:
            return ToolResult(
                tool_name="cli_run",
                success=False,
                output="",
                error="Sandbox not available for CLI commands"
            )

        try:
            exit_code, output = await self.sandbox.exec(command, timeout=60)

            # Truncate if too large
            if len(output) > MAX_CLI_OUTPUT_CHARS:
                output = output[:MAX_CLI_OUTPUT_CHARS] + "\n\n[... truncated ...]"

            return ToolResult(
                tool_name="cli_run",
                success=exit_code == 0,
                output=output,
                error=f"Command exited with code {exit_code}" if exit_code != 0 else None
            )

        except Exception as e:
            logger.error(f"Error executing command '{command}': {e}")
            return ToolResult(
                tool_name="cli_run",
                success=False,
                output="",
                error=str(e)
            )

    async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
        """Execute a tool call and return the result.

        Args:
            tool_call: ToolCall to execute

        Returns:
            ToolResult from the tool execution
        """
        if tool_call.name == "read_file":
            return await self._execute_read_file(
                path=tool_call.arguments.get("path", ""),
                start_line=tool_call.arguments.get("start_line"),
                end_line=tool_call.arguments.get("end_line"),
            )
        elif tool_call.name == "search":
            return await self._execute_search(
                query=tool_call.arguments.get("query", ""),
                file_pattern=tool_call.arguments.get("file_pattern"),
            )
        elif tool_call.name == "cli_run":
            return await self._execute_cli_run(
                command=tool_call.arguments.get("command", "")
            )
        else:
            return ToolResult(
                tool_name=tool_call.name,
                success=False,
                output="",
                error=f"Unknown tool: {tool_call.name}"
            )


    def _parse_tool_calls(self, content: str) -> list[ToolCall]:
        """Parse tool calls from LLM response content.

        Looks for JSON tool call blocks in the response.

        Args:
            content: LLM response content

        Returns:
            List of ToolCall objects
        """
        tool_calls: list[ToolCall] = []

        # Try to find JSON blocks with tool calls
        # Pattern: {"tool": "name", "arguments": {...}}
        json_pattern = r'\{[^{}]*"(?:tool|name)"[^{}]*\}'

        for match in re.finditer(json_pattern, content, re.DOTALL):
            try:
                data = json.loads(match.group())
                tool_name = data.get("tool") or data.get("name")
                arguments = data.get("arguments", data.get("params", {}))

                if tool_name and isinstance(arguments, dict):
                    tool_calls.append(ToolCall(name=tool_name, arguments=arguments))
            except json.JSONDecodeError:
                continue

        return tool_calls

    def _parse_finish_call(self, content: str) -> InvestigationResult | None:
        """Parse finish_investigation call from LLM response.

        Args:
            content: LLM response content

        Returns:
            InvestigationResult if finish call found, None otherwise
        """
        # Look for finish_investigation JSON
        pattern = r'\{[^{}]*"status"[^{}]*"(?:confirmed|likely_real|uncertain|invalid)"[^{}]*\}'

        for match in re.finditer(pattern, content, re.DOTALL):
            try:
                # Try to parse a larger JSON block
                start = match.start()
                # Find the full JSON object
                brace_count = 0
                end = start
                for i, char in enumerate(content[start:], start):
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end = i + 1
                            break

                json_str = content[start:end]
                data = json.loads(json_str)

                status = data.get("status")
                if status in ("confirmed", "likely_real", "uncertain", "invalid"):
                    return InvestigationResult(
                        status=status,
                        technical_notes=data.get("technical_notes", []),
                        suggested_fix=data.get("suggested_fix"),
                    )
            except (json.JSONDecodeError, IndexError):
                continue

        return None

    async def investigate(self, issue: MergedIssue) -> InvestigationResult:
        """Investigate a single issue using available tools.

        Runs a tool-calling loop where the LLM can read files, search code,
        and run commands to investigate the issue. Continues until the LLM
        calls finish_investigation or max iterations is reached.

        Args:
            issue: MergedIssue to investigate

        Returns:
            InvestigationResult with findings
        """
        logger.info(f"Starting investigation of issue {issue.id}")

        # Build initial messages
        messages = [
            {"role": "system", "content": INVESTIGATION_SYSTEM_PROMPT},
            {"role": "user", "content": self._build_issue_prompt(issue)},
        ]

        # Track investigation state
        files_examined: list[str] = []
        commands_executed: list[str] = []
        iterations = 0

        while iterations < MAX_INVESTIGATION_ITERATIONS:
            iterations += 1
            logger.debug(f"Investigation iteration {iterations}")

            try:
                # Call LLM
                response = await self.llm.chat(
                    messages=messages,
                    model=self.model,
                    temperature=0.1,
                    max_tokens=4096,
                    fallback=False,
                )

                content = response.get("content") or ""

                # Check for finish_investigation call
                finish_result = self._parse_finish_call(content)
                if finish_result:
                    finish_result.files_examined = files_examined
                    finish_result.commands_executed = commands_executed
                    finish_result.iterations_used = iterations
                    logger.info(
                        f"Investigation of {issue.id} completed: {finish_result.status} "
                        f"({iterations} iterations)"
                    )
                    return finish_result

                # Parse tool calls
                tool_calls = self._parse_tool_calls(content)

                if not tool_calls:
                    # No tool calls and no finish - add assistant message and prompt for action
                    messages.append({"role": "assistant", "content": content})
                    messages.append({
                        "role": "user",
                        "content": "Please use one of the available tools to investigate, or call finish_investigation with your findings."
                    })
                    continue

                # Execute tool calls and collect results
                tool_results: list[str] = []
                for tool_call in tool_calls:
                    if tool_call.name == "finish_investigation":
                        # Handle finish call from tool_calls
                        args = tool_call.arguments
                        status = args.get("status", "uncertain")
                        if status not in ("confirmed", "likely_real", "uncertain", "invalid"):
                            status = "uncertain"

                        return InvestigationResult(
                            status=status,
                            technical_notes=args.get("technical_notes", []),
                            suggested_fix=args.get("suggested_fix"),
                            files_examined=files_examined,
                            commands_executed=commands_executed,
                            iterations_used=iterations,
                        )

                    # Execute the tool
                    result = await self._execute_tool(tool_call)

                    # Track what was examined
                    if tool_call.name == "read_file":
                        path = tool_call.arguments.get("path", "")
                        if path and path not in files_examined:
                            files_examined.append(path)
                    elif tool_call.name == "cli_run":
                        cmd = tool_call.arguments.get("command", "")
                        if cmd:
                            commands_executed.append(cmd)

                    # Format result for LLM
                    if result.success:
                        tool_results.append(
                            f"**{tool_call.name}** result:\n```\n{result.output}\n```"
                        )
                    else:
                        tool_results.append(
                            f"**{tool_call.name}** error: {result.error}"
                        )

                # Add assistant message and tool results
                messages.append({"role": "assistant", "content": content})
                messages.append({
                    "role": "user",
                    "content": "\n\n".join(tool_results) + "\n\nContinue investigating or call finish_investigation with your findings."
                })

            except LLMError as e:
                logger.error(f"LLM error during investigation: {e}")
                return InvestigationResult(
                    status="uncertain",
                    technical_notes=[f"Investigation failed due to LLM error: {str(e)}"],
                    files_examined=files_examined,
                    commands_executed=commands_executed,
                    iterations_used=iterations,
                )
            except Exception as e:
                logger.error(f"Unexpected error during investigation: {e}")
                return InvestigationResult(
                    status="uncertain",
                    technical_notes=[f"Investigation failed: {str(e)}"],
                    files_examined=files_examined,
                    commands_executed=commands_executed,
                    iterations_used=iterations,
                )

        # Max iterations reached
        logger.warning(f"Investigation of {issue.id} reached max iterations")
        return InvestigationResult(
            status="uncertain",
            technical_notes=["Investigation reached maximum iterations without conclusion"],
            files_examined=files_examined,
            commands_executed=commands_executed,
            iterations_used=iterations,
        )


# =============================================================================
# Convenience Functions
# =============================================================================


def get_issue_investigator(
    llm_gateway: LLMGateway | None = None,
    repo_path: Path | str | None = None,
    sandbox: Sandbox | None = None,
    model: str = "bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0",
) -> IssueInvestigator:
    """Create an IssueInvestigator instance.

    Args:
        llm_gateway: Optional LLMGateway instance. Creates one if not provided.
        repo_path: Path to the repository to investigate
        sandbox: Optional Sandbox for CLI commands
        model: LLM model to use for investigation

    Returns:
        Configured IssueInvestigator instance
    """
    from app.services.llm_gateway import get_llm_gateway

    if llm_gateway is None:
        llm_gateway = get_llm_gateway()

    if repo_path is None:
        raise ValueError("repo_path is required")

    return IssueInvestigator(
        llm_gateway=llm_gateway,
        repo_path=Path(repo_path),
        sandbox=sandbox,
        model=model,
    )
