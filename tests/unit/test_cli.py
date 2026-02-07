"""Unit tests for the CLI interface."""

import pytest

from hindsight.cli.interface import Colors, HindsightCLI, main
from hindsight.models import (
    AnalysisResult,
    CommitInfo,
    ErrorInfo,
    Explanation,
    FixSuggestion,
    RootCause,
    StackFrame,
)


class TestCLIArgumentParsing:
    def setup_method(self):
        self.cli = HindsightCLI()

    def test_parse_error_message(self):
        args = self.cli.parse_arguments(["TypeError: bad type"])
        assert args.error == "TypeError: bad type"

    def test_parse_repo_flag(self):
        args = self.cli.parse_arguments(["-r", "/path/to/repo", "Error"])
        assert args.repo == "/path/to/repo"

    def test_parse_verbose(self):
        args = self.cli.parse_arguments(["-v", "Error"])
        assert args.verbose is True

    def test_parse_no_color(self):
        args = self.cli.parse_arguments(["--no-color", "Error"])
        assert args.no_color is True

    def test_parse_max_commits(self):
        args = self.cli.parse_arguments(["-n", "25", "Error"])
        assert args.max_commits == 25

    def test_parse_traceback_file(self):
        args = self.cli.parse_arguments(["-f", "error.txt"])
        assert args.traceback_file == "error.txt"

    def test_parse_no_cache(self):
        args = self.cli.parse_arguments(["--no-cache", "Error"])
        assert args.no_cache is True

    def test_parse_init(self):
        args = self.cli.parse_arguments(["--init"])
        assert args.init is True

    def test_parse_clear_cache(self):
        args = self.cli.parse_arguments(["--clear-cache"])
        assert args.clear_cache is True

    def test_parse_stdin_flag(self):
        args = self.cli.parse_arguments(["-"])
        assert args.error == "-"


class TestCLIFormatOutput:
    def setup_method(self):
        self.cli = HindsightCLI()

    def test_format_basic_result(self, sample_error_info):
        result = AnalysisResult(
            error_info=sample_error_info,
            analysis_time_seconds=1.5,
        )
        output = self.cli.format_output(result)
        assert "AttributeError" in output
        assert "NoneType" in output

    def test_format_with_explanation(self, sample_error_info):
        exp = Explanation(
            summary="User object is None",
            root_cause="Session timeout reduced",
            intent_vs_actual="Intended: always valid user. Actual: can be None.",
            commit_references=["abc123: reduced timeout"],
            fix_suggestions=[
                FixSuggestion(
                    description="Add null check",
                    code_example="if user is None: return",
                    rationale="Handle expired sessions",
                    difficulty="easy",
                )
            ],
            educational_notes=["Always check return values"],
        )
        result = AnalysisResult(
            error_info=sample_error_info,
            explanation=exp,
            analysis_time_seconds=2.0,
        )
        output = self.cli.format_output(result)
        assert "User object is None" in output
        assert "null check" in output.lower()
        assert "always check" in output.lower()

    def test_format_with_root_cause(self, sample_error_info, sample_commits):
        result = AnalysisResult(
            error_info=sample_error_info,
            root_cause=RootCause(
                commit=sample_commits[0],
                description="Found it",
                confidence=0.85,
            ),
            analysis_time_seconds=1.0,
        )
        output = self.cli.format_output(result)
        assert "abc1234" in output
        assert "85%" in output

    def test_format_with_limitations(self, sample_error_info):
        result = AnalysisResult(
            error_info=sample_error_info,
            limitations=["No API key available"],
            analysis_time_seconds=0.5,
        )
        output = self.cli.format_output(result)
        assert "No API key" in output


class TestCLIErrorHandling:
    def setup_method(self):
        self.cli = HindsightCLI()

    def test_handle_generic_error(self):
        msg = self.cli.handle_errors(ValueError("something broke"))
        assert "ValueError" in msg
        assert "something broke" in msg


class TestColorsDisable:
    def test_disable_colors(self):
        Colors.disable()
        assert Colors.RED == ""
        assert Colors.BOLD == ""
        assert Colors.RESET == ""
        # Re-enable for other tests
        Colors.RED = "\033[91m"
        Colors.BOLD = "\033[1m"
        Colors.RESET = "\033[0m"
        Colors.GREEN = "\033[92m"
        Colors.YELLOW = "\033[93m"
        Colors.BLUE = "\033[94m"
        Colors.MAGENTA = "\033[95m"
        Colors.CYAN = "\033[96m"
        Colors.DIM = "\033[2m"


class TestMainEntryPoint:
    def test_no_args_returns_error(self):
        exit_code = main([])
        assert exit_code != 0

    def test_init_flag(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "hindsight.config.DEFAULT_CONFIG_DIR", tmp_path / ".hindsight"
        )
        cli = HindsightCLI()
        cli.config.config_dir = tmp_path / ".hindsight"
        exit_code = cli.run(["--init"])
        assert exit_code == 0
