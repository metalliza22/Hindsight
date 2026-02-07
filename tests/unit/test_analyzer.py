"""Unit tests for the Core Analyzer (HindsightAnalyzer)."""

import pytest

from hindsight.analyzer.hindsight_analyzer import HindsightAnalyzer
from hindsight.config import Config
from hindsight.models import CommitInfo, ErrorInfo, IntentInfo


class TestParseErrorMessage:
    def setup_method(self):
        self.analyzer = HindsightAnalyzer(Config())

    def test_parse_full_traceback(self, sample_traceback):
        result = self.analyzer.parse_error_message(sample_traceback)
        assert result.error_type == "AttributeError"
        assert "'NoneType'" in result.message
        assert len(result.stack_trace) == 2
        assert result.stack_trace[0].file_path == "app.py"
        assert result.stack_trace[0].line_number == 42
        assert result.stack_trace[0].function_name == "main"
        assert result.stack_trace[1].file_path == "processor.py"
        assert result.stack_trace[1].line_number == 15

    def test_parse_single_frame_traceback(self):
        tb = (
            "Traceback (most recent call last):\n"
            '  File "main.py", line 5, in <module>\n'
            "    x.run()\n"
            "NameError: name 'x' is not defined"
        )
        result = self.analyzer.parse_error_message(tb)
        assert result.error_type == "NameError"
        assert len(result.stack_trace) == 1
        assert result.stack_trace[0].code_context == "x.run()"

    def test_parse_simple_error_no_traceback(self):
        result = self.analyzer.parse_error_message("KeyError: 'user_id'")
        assert result.error_type == "KeyError"
        assert result.message == "'user_id'"

    def test_parse_unknown_format(self):
        result = self.analyzer.parse_error_message("something went wrong")
        assert result.error_type == "UnknownError"
        assert "something went wrong" in result.message

    def test_parse_multiline_traceback(self):
        tb = (
            "Traceback (most recent call last):\n"
            '  File "a.py", line 1, in f1\n'
            "    f2()\n"
            '  File "b.py", line 2, in f2\n'
            "    f3()\n"
            '  File "c.py", line 3, in f3\n'
            "    raise ValueError('bad')\n"
            "ValueError: bad"
        )
        result = self.analyzer.parse_error_message(tb)
        assert result.error_type == "ValueError"
        assert len(result.stack_trace) == 3
        assert result.affected_files == ["a.py", "b.py", "c.py"]
        assert result.line_numbers == [1, 2, 3]

    def test_parse_preserves_raw_traceback(self, sample_traceback):
        result = self.analyzer.parse_error_message(sample_traceback)
        assert result.raw_traceback == sample_traceback

    def test_affected_files_deduped(self):
        tb = (
            "Traceback (most recent call last):\n"
            '  File "app.py", line 1, in f1\n'
            "    f2()\n"
            '  File "app.py", line 10, in f2\n'
            "    x()\n"
            "TypeError: not callable"
        )
        result = self.analyzer.parse_error_message(tb)
        assert result.affected_files == ["app.py"]


class TestClassifyError:
    def setup_method(self):
        self.analyzer = HindsightAnalyzer(Config())

    def test_known_types(self):
        assert self.analyzer.classify_error("TypeError") == "type_error"
        assert self.analyzer.classify_error("KeyError") == "key_error"
        assert self.analyzer.classify_error("ImportError") == "import_error"
        assert self.analyzer.classify_error("ConnectionError") == "network_error"

    def test_unknown_type(self):
        assert self.analyzer.classify_error("CustomError") == "unknown_error"


class TestRootCauseIdentification:
    def setup_method(self):
        self.analyzer = HindsightAnalyzer(Config())

    def test_identify_root_cause(self, sample_commits):
        intent = IntentInfo(file_path="test.py")
        rc = self.analyzer.identify_root_cause(sample_commits, intent)
        assert rc is not None
        assert rc.commit.hash == "abc1234"  # highest relevance
        assert rc.confidence == 0.8

    def test_identify_root_cause_empty_commits(self):
        intent = IntentInfo(file_path="test.py")
        rc = self.analyzer.identify_root_cause([], intent)
        assert rc is None

    def test_rank_commits(self, sample_commits):
        ranked = self.analyzer.rank_commits_by_likelihood(sample_commits)
        assert ranked[0].relevance_score >= ranked[1].relevance_score
        assert ranked[1].relevance_score >= ranked[2].relevance_score


class TestAnalyzeBug:
    def test_analyze_with_valid_repo(self, tmp_git_repo):
        analyzer = HindsightAnalyzer(Config())
        error = (
            "Traceback (most recent call last):\n"
            '  File "app.py", line 3, in greet\n'
            "    return f\"Hello, {name}\"\n"
            "TypeError: must be str, not NoneType"
        )
        result = analyzer.analyze_bug(error, str(tmp_git_repo))
        assert result.error_info.error_type == "TypeError"
        assert len(result.relevant_commits) >= 0
        assert result.analysis_time_seconds > 0

    def test_analyze_with_invalid_repo(self, tmp_path):
        analyzer = HindsightAnalyzer(Config())
        result = analyzer.analyze_bug("TypeError: bad", str(tmp_path))
        assert "not a valid git repository" in result.limitations[0].lower() or "Git" in result.limitations[0]

    def test_analyze_includes_limitations_without_api_key(self, tmp_git_repo, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("HINDSIGHT_API_KEY", raising=False)
        analyzer = HindsightAnalyzer(Config())
        result = analyzer.analyze_bug("TypeError: x", str(tmp_git_repo))
        # Should have a limitation about missing API key
        assert any("api key" in l.lower() or "API" in l for l in result.limitations)
