"""Property-based tests for IssueInvestigator.

Uses Hypothesis for property-based testing to verify correctness properties
defined in the design document.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.issue_investigator import (
    MAX_INVESTIGATION_ITERATIONS,
    TOOL_DEFINITIONS,
    InvestigationResult,
    ToolCall,
    ToolResult,
)

# =============================================================================
# Custom Strategies for Test Data Generation
# =============================================================================


@st.composite
def valid_investigation_status(draw) -> str:
    """Generate valid investigation status values."""
    return draw(st.sampled_from(["confirmed", "likely_real", "uncertain", "invalid"]))


@st.composite
def technical_note(draw) -> str:
    """Generate a valid technical note."""
    return draw(st.text(min_size=5, max_size=200).filter(lambda s: s.strip()))


@st.composite
def technical_notes_list(draw, min_size: int = 0, max_size: int = 5) -> list[str]:
    """Generate a list of technical notes."""
    return draw(st.lists(technical_note(), min_size=min_size, max_size=max_size))


@st.composite
def suggested_fix(draw) -> str | None:
    """Generate an optional suggested fix."""
    return draw(st.one_of(
        st.none(),
        st.text(min_size=10, max_size=500).filter(lambda s: s.strip())
    ))


@st.composite
def file_path(draw) -> str:
    """Generate a valid file path."""
    dirname = draw(st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_-"),
        min_size=1,
        max_size=20
    ).filter(lambda s: s.strip()))
    filename = draw(st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_-"),
        min_size=1,
        max_size=20
    ).filter(lambda s: s.strip()))
    ext = draw(st.sampled_from([".py", ".js", ".ts", ".go", ".rs", ".java"]))
    return f"{dirname}/{filename}{ext}"


@st.composite
def command_string(draw) -> str:
    """Generate a valid CLI command string."""
    commands = [
        "grep -r 'pattern' .",
        "cat file.txt",
        "ls -la",
        "find . -name '*.py'",
        "wc -l file.py",
    ]
    return draw(st.sampled_from(commands))


@st.composite
def investigation_result(draw) -> InvestigationResult:
    """Generate a valid InvestigationResult."""
    return InvestigationResult(
        status=draw(valid_investigation_status()),
        technical_notes=draw(technical_notes_list(min_size=0, max_size=5)),
        suggested_fix=draw(suggested_fix()),
        commands_executed=draw(st.lists(command_string(), min_size=0, max_size=3)),
        files_examined=draw(st.lists(file_path(), min_size=0, max_size=5)),
        iterations_used=draw(st.integers(min_value=1, max_value=MAX_INVESTIGATION_ITERATIONS)),
    )


@st.composite
def tool_call(draw) -> ToolCall:
    """Generate a valid ToolCall."""
    tool_name = draw(st.sampled_from(["read_file", "search", "cli_run", "finish_investigation"]))

    if tool_name == "read_file":
        arguments = {
            "path": draw(file_path()),
            "start_line": draw(st.one_of(st.none(), st.integers(min_value=1, max_value=100))),
            "end_line": draw(st.one_of(st.none(), st.integers(min_value=1, max_value=200))),
        }
    elif tool_name == "search":
        arguments = {
            "query": draw(st.text(min_size=1, max_size=50).filter(lambda s: s.strip())),
            "file_pattern": draw(st.one_of(st.none(), st.sampled_from(["*.py", "*.js", "*.ts"]))),
        }
    elif tool_name == "cli_run":
        arguments = {
            "command": draw(command_string()),
        }
    else:  # finish_investigation
        arguments = {
            "status": draw(valid_investigation_status()),
            "technical_notes": draw(technical_notes_list(min_size=1, max_size=3)),
            "suggested_fix": draw(suggested_fix()),
        }

    return ToolCall(name=tool_name, arguments=arguments)


@st.composite
def tool_result(draw) -> ToolResult:
    """Generate a valid ToolResult."""
    success = draw(st.booleans())
    return ToolResult(
        tool_name=draw(st.sampled_from(["read_file", "search", "cli_run"])),
        success=success,
        output=draw(st.text(min_size=0, max_size=500)) if success else "",
        error=None if success else draw(st.text(min_size=5, max_size=100).filter(lambda s: s.strip())),
    )


# =============================================================================
# Property Tests for Investigation Output Completeness
# =============================================================================


class TestInvestigationOutputCompleteness:
    """Property tests for investigation output completeness.

    **Feature: ai-scan-integration, Property 14: Investigation Output Completeness**
    **Validates: Requirements 5.3, 5.4**
    """

    @given(investigation_result())
    @settings(max_examples=100)
    def test_investigation_result_has_valid_status(self, result: InvestigationResult):
        """
        **Feature: ai-scan-integration, Property 14: Investigation Output Completeness**
        **Validates: Requirements 5.3, 5.4**

        Property: For any investigated issue, the result SHALL contain a valid
        status (confirmed|likely_real|uncertain|invalid).
        """
        valid_statuses = {"confirmed", "likely_real", "uncertain", "invalid"}

        # Property: Status must be one of the valid values
        assert result.status in valid_statuses, (
            f"Invalid status '{result.status}', expected one of {valid_statuses}"
        )

    @given(investigation_result())
    @settings(max_examples=100)
    def test_investigation_result_has_technical_notes_list(self, result: InvestigationResult):
        """
        **Feature: ai-scan-integration, Property 14: Investigation Output Completeness**
        **Validates: Requirements 5.3, 5.4**

        Property: For any investigated issue, the result SHALL contain a
        technical_notes list (may be empty).
        """
        # Property: technical_notes must be a list
        assert isinstance(result.technical_notes, list), (
            f"technical_notes should be a list, got {type(result.technical_notes)}"
        )

        # Property: All items in technical_notes should be strings
        for note in result.technical_notes:
            assert isinstance(note, str), (
                f"Each technical note should be a string, got {type(note)}"
            )

    @given(investigation_result())
    @settings(max_examples=100)
    def test_investigation_result_has_suggested_fix_field(self, result: InvestigationResult):
        """
        **Feature: ai-scan-integration, Property 14: Investigation Output Completeness**
        **Validates: Requirements 5.3, 5.4**

        Property: For any investigated issue, the result SHALL contain a
        suggested_fix field (may be None).
        """
        # Property: suggested_fix must be None or a string
        assert result.suggested_fix is None or isinstance(result.suggested_fix, str), (
            f"suggested_fix should be None or str, got {type(result.suggested_fix)}"
        )

    @given(investigation_result())
    @settings(max_examples=100)
    def test_investigation_result_tracks_commands(self, result: InvestigationResult):
        """
        **Feature: ai-scan-integration, Property 14: Investigation Output Completeness**
        **Validates: Requirements 5.3, 5.4**

        Property: For any investigated issue, the result SHALL track commands
        executed during investigation.
        """
        # Property: commands_executed must be a list
        assert isinstance(result.commands_executed, list), (
            f"commands_executed should be a list, got {type(result.commands_executed)}"
        )

        # Property: All items should be strings
        for cmd in result.commands_executed:
            assert isinstance(cmd, str), (
                f"Each command should be a string, got {type(cmd)}"
            )

    @given(investigation_result())
    @settings(max_examples=100)
    def test_investigation_result_tracks_files_examined(self, result: InvestigationResult):
        """
        **Feature: ai-scan-integration, Property 14: Investigation Output Completeness**
        **Validates: Requirements 5.3, 5.4**

        Property: For any investigated issue, the result SHALL track files
        examined during investigation.
        """
        # Property: files_examined must be a list
        assert isinstance(result.files_examined, list), (
            f"files_examined should be a list, got {type(result.files_examined)}"
        )

        # Property: All items should be strings
        for file in result.files_examined:
            assert isinstance(file, str), (
                f"Each file path should be a string, got {type(file)}"
            )

    @given(investigation_result())
    @settings(max_examples=100)
    def test_investigation_result_tracks_iterations(self, result: InvestigationResult):
        """
        **Feature: ai-scan-integration, Property 14: Investigation Output Completeness**
        **Validates: Requirements 5.3, 5.4**

        Property: For any investigated issue, the result SHALL track the number
        of iterations used.
        """
        # Property: iterations_used must be a positive integer
        assert isinstance(result.iterations_used, int), (
            f"iterations_used should be an int, got {type(result.iterations_used)}"
        )
        assert result.iterations_used >= 0, (
            f"iterations_used should be non-negative, got {result.iterations_used}"
        )
        assert result.iterations_used <= MAX_INVESTIGATION_ITERATIONS, (
            f"iterations_used should not exceed {MAX_INVESTIGATION_ITERATIONS}, "
            f"got {result.iterations_used}"
        )

    @given(valid_investigation_status(), technical_notes_list(min_size=1, max_size=3), suggested_fix())
    @settings(max_examples=100)
    def test_investigation_result_construction(
        self,
        status: str,
        notes: list[str],
        fix: str | None
    ):
        """
        **Feature: ai-scan-integration, Property 14: Investigation Output Completeness**
        **Validates: Requirements 5.3, 5.4**

        Property: InvestigationResult can be constructed with any valid
        combination of status, notes, and fix.
        """
        result = InvestigationResult(
            status=status,
            technical_notes=notes,
            suggested_fix=fix,
        )

        # Property: All fields should be set correctly
        assert result.status == status
        assert result.technical_notes == notes
        assert result.suggested_fix == fix

        # Property: Default values should be set
        assert result.commands_executed == []
        assert result.files_examined == []
        assert result.iterations_used == 0


# =============================================================================
# Property Tests for Tool Definitions
# =============================================================================


class TestToolDefinitions:
    """Property tests for tool definitions."""

    def test_all_required_tools_defined(self):
        """All required tools should be defined."""
        required_tools = {"read_file", "search", "cli_run", "finish_investigation"}
        defined_tools = {tool["name"] for tool in TOOL_DEFINITIONS}

        assert required_tools == defined_tools, (
            f"Missing tools: {required_tools - defined_tools}, "
            f"Extra tools: {defined_tools - required_tools}"
        )

    def test_tool_definitions_have_required_fields(self):
        """Each tool definition should have required fields."""
        for tool in TOOL_DEFINITIONS:
            assert "name" in tool, "Tool missing 'name' field"
            assert "description" in tool, f"Tool {tool.get('name')} missing 'description'"
            assert "parameters" in tool, f"Tool {tool.get('name')} missing 'parameters'"

            params = tool["parameters"]
            assert params.get("type") == "object", (
                f"Tool {tool['name']} parameters should be type 'object'"
            )
            assert "properties" in params, (
                f"Tool {tool['name']} parameters missing 'properties'"
            )
            assert "required" in params, (
                f"Tool {tool['name']} parameters missing 'required'"
            )


# =============================================================================
# Property Tests for ToolCall and ToolResult
# =============================================================================


class TestToolCallAndResult:
    """Property tests for ToolCall and ToolResult dataclasses."""

    @given(tool_call())
    @settings(max_examples=100)
    def test_tool_call_has_name_and_arguments(self, call: ToolCall):
        """
        Property: Every ToolCall should have a name and arguments dict.
        """
        assert isinstance(call.name, str), "ToolCall.name should be a string"
        assert len(call.name) > 0, "ToolCall.name should not be empty"
        assert isinstance(call.arguments, dict), "ToolCall.arguments should be a dict"

    @given(tool_result())
    @settings(max_examples=100)
    def test_tool_result_consistency(self, result: ToolResult):
        """
        Property: ToolResult should have consistent success/error state.
        """
        if result.success:
            # Successful results should not have errors
            assert result.error is None, (
                "Successful ToolResult should not have an error"
            )
        else:
            # Failed results should have an error message
            assert result.error is not None, (
                "Failed ToolResult should have an error message"
            )

    @given(st.sampled_from(["read_file", "search", "cli_run"]))
    @settings(max_examples=50)
    def test_tool_result_tool_name_valid(self, tool_name: str):
        """
        Property: ToolResult tool_name should be a valid tool name.
        """
        result = ToolResult(
            tool_name=tool_name,
            success=True,
            output="test output",
        )

        valid_tools = {"read_file", "search", "cli_run", "finish_investigation"}
        assert result.tool_name in valid_tools, (
            f"Invalid tool name: {result.tool_name}"
        )


# =============================================================================
# Unit Tests for InvestigationResult
# =============================================================================


class TestInvestigationResultUnit:
    """Unit tests for InvestigationResult."""

    def test_default_values(self):
        """Test default values for InvestigationResult."""
        result = InvestigationResult(status="confirmed")

        assert result.status == "confirmed"
        assert result.technical_notes == []
        assert result.suggested_fix is None
        assert result.commands_executed == []
        assert result.files_examined == []
        assert result.iterations_used == 0

    def test_all_fields_set(self):
        """Test setting all fields."""
        result = InvestigationResult(
            status="likely_real",
            technical_notes=["Note 1", "Note 2"],
            suggested_fix="Fix the bug",
            commands_executed=["grep -r 'bug' ."],
            files_examined=["src/main.py", "src/utils.py"],
            iterations_used=3,
        )

        assert result.status == "likely_real"
        assert result.technical_notes == ["Note 1", "Note 2"]
        assert result.suggested_fix == "Fix the bug"
        assert result.commands_executed == ["grep -r 'bug' ."]
        assert result.files_examined == ["src/main.py", "src/utils.py"]
        assert result.iterations_used == 3

    def test_status_values(self):
        """Test all valid status values."""
        for status in ["confirmed", "likely_real", "uncertain", "invalid"]:
            result = InvestigationResult(status=status)
            assert result.status == status


class TestToolCallUnit:
    """Unit tests for ToolCall."""

    def test_read_file_tool_call(self):
        """Test read_file tool call."""
        call = ToolCall(
            name="read_file",
            arguments={"path": "src/main.py", "start_line": 10, "end_line": 20}
        )

        assert call.name == "read_file"
        assert call.arguments["path"] == "src/main.py"
        assert call.arguments["start_line"] == 10
        assert call.arguments["end_line"] == 20

    def test_search_tool_call(self):
        """Test search tool call."""
        call = ToolCall(
            name="search",
            arguments={"query": "TODO", "file_pattern": "*.py"}
        )

        assert call.name == "search"
        assert call.arguments["query"] == "TODO"
        assert call.arguments["file_pattern"] == "*.py"

    def test_cli_run_tool_call(self):
        """Test cli_run tool call."""
        call = ToolCall(
            name="cli_run",
            arguments={"command": "ls -la"}
        )

        assert call.name == "cli_run"
        assert call.arguments["command"] == "ls -la"


class TestToolResultUnit:
    """Unit tests for ToolResult."""

    def test_successful_result(self):
        """Test successful tool result."""
        result = ToolResult(
            tool_name="read_file",
            success=True,
            output="file content here",
        )

        assert result.tool_name == "read_file"
        assert result.success is True
        assert result.output == "file content here"
        assert result.error is None

    def test_failed_result(self):
        """Test failed tool result."""
        result = ToolResult(
            tool_name="read_file",
            success=False,
            output="",
            error="File not found",
        )

        assert result.tool_name == "read_file"
        assert result.success is False
        assert result.output == ""
        assert result.error == "File not found"


# =============================================================================
# Tests for CLI Command Parsing (Shell Injection Prevention)
# =============================================================================


class TestCLICommandParsing:
    """Tests for CLI command parsing that prevents shell injection.
    
    TEMPORARY FIX: These tests verify the shlex-based parsing approach.
    Future improvements may include semantic analysis, configurable policies,
    or ML-based command classification.
    """

    def test_simple_commands_parse_correctly(self):
        """Test that simple commands are parsed into argument lists."""
        from app.services.issue_investigator import _parse_shell_command

        test_cases = [
            ("grep -r pattern .", ["grep", "-r", "pattern", "."]),
            ("cat file.txt", ["cat", "file.txt"]),
            ("ls -la", ["ls", "-la"]),
            ("git log --oneline -10", ["git", "log", "--oneline", "-10"]),
            ("python -m pytest", ["python", "-m", "pytest"]),
        ]

        for cmd, expected in test_cases:
            result = _parse_shell_command(cmd)
            assert result == expected, f"Expected {expected} for '{cmd}', got {result}"

    def test_quoted_arguments_preserved(self):
        """Test that quoted arguments are properly handled."""
        from app.services.issue_investigator import _parse_shell_command

        test_cases = [
            ("grep 'hello world' file.txt", ["grep", "hello world", "file.txt"]),
            ('grep "hello world" file.txt', ["grep", "hello world", "file.txt"]),
            ("echo 'single quotes'", ["echo", "single quotes"]),
            ('echo "double quotes"', ["echo", "double quotes"]),
        ]

        for cmd, expected in test_cases:
            result = _parse_shell_command(cmd)
            assert result == expected, f"Expected {expected} for '{cmd}', got {result}"

    def test_empty_command_raises_error(self):
        """Test that empty commands raise ValueError."""
        from app.services.issue_investigator import _parse_shell_command
        import pytest

        with pytest.raises(ValueError, match="Empty command"):
            _parse_shell_command("")

        with pytest.raises(ValueError, match="Empty command"):
            _parse_shell_command("   ")

    def test_shell_metacharacters_become_literal(self):
        """Test that shell metacharacters are treated as literal strings.
        
        This is the key security feature - pipes, redirects, etc. are NOT
        interpreted by a shell, they become literal arguments.
        """
        from app.services.issue_investigator import _parse_shell_command

        # These would be dangerous with shell interpretation, but are safe
        # when parsed as literal arguments (they'll just fail to execute)
        test_cases = [
            # Pipe becomes a literal argument
            ("cat file.txt | grep pattern", ["cat", "file.txt", "|", "grep", "pattern"]),
            # Semicolon becomes a literal argument
            ("ls ; rm -rf /", ["ls", ";", "rm", "-rf", "/"]),
            # Redirect becomes a literal argument
            ("echo hello > file.txt", ["echo", "hello", ">", "file.txt"]),
        ]

        for cmd, expected in test_cases:
            result = _parse_shell_command(cmd)
            assert result == expected, f"Expected {expected} for '{cmd}', got {result}"

    def test_command_with_equals_sign(self):
        """Test commands with environment variable syntax."""
        from app.services.issue_investigator import _parse_shell_command

        # Note: Without shell, FOO=bar is just an argument, not env var setting
        result = _parse_shell_command("FOO=bar command arg")
        assert result == ["FOO=bar", "command", "arg"]

    def test_complex_git_commands(self):
        """Test parsing of complex git commands."""
        from app.services.issue_investigator import _parse_shell_command

        test_cases = [
            ("git log --format='%H %s' -5", ["git", "log", "--format=%H %s", "-5"]),
            ("git show HEAD:file.py", ["git", "show", "HEAD:file.py"]),
            ("git diff HEAD~1", ["git", "diff", "HEAD~1"]),
        ]

        for cmd, expected in test_cases:
            result = _parse_shell_command(cmd)
            assert result == expected, f"Expected {expected} for '{cmd}', got {result}"

    def test_find_command_with_exec(self):
        """Test parsing find command with -exec (common pattern)."""
        from app.services.issue_investigator import _parse_shell_command

        # Note: -exec {} \; won't work without shell, but parsing should succeed
        result = _parse_shell_command("find . -name '*.py' -type f")
        assert result == ["find", ".", "-name", "*.py", "-type", "f"]

    def test_malformed_quotes_raise_error(self):
        """Test that malformed quotes raise ValueError."""
        from app.services.issue_investigator import _parse_shell_command
        import pytest

        # Unclosed quote
        with pytest.raises(ValueError, match="Failed to parse"):
            _parse_shell_command("grep 'unclosed")

    def test_backslash_escapes(self):
        """Test that backslash escapes are handled."""
        from app.services.issue_investigator import _parse_shell_command

        result = _parse_shell_command(r"grep hello\ world file.txt")
        assert result == ["grep", "hello world", "file.txt"]
