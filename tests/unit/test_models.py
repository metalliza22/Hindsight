"""Unit tests for data models."""

from datetime import datetime

from hindsight.models import (
    AnalysisResult,
    BugContext,
    CommitInfo,
    ErrorInfo,
    Explanation,
    FixSuggestion,
    IntentInfo,
    RootCause,
    StackFrame,
)


class TestErrorInfo:
    def test_default_fields(self):
        err = ErrorInfo(error_type="TypeError", message="bad type")
        assert err.error_type == "TypeError"
        assert err.message == "bad type"
        assert err.stack_trace == []
        assert err.affected_files == []
        assert err.line_numbers == []
        assert err.variable_context == {}
        assert err.raw_traceback == ""

    def test_with_stack_trace(self):
        frame = StackFrame(
            file_path="test.py",
            line_number=10,
            function_name="foo",
            code_context="x = 1",
        )
        err = ErrorInfo(
            error_type="ValueError",
            message="invalid",
            stack_trace=[frame],
            affected_files=["test.py"],
            line_numbers=[10],
        )
        assert len(err.stack_trace) == 1
        assert err.stack_trace[0].file_path == "test.py"


class TestCommitInfo:
    def test_creation(self):
        c = CommitInfo(
            hash="abc123",
            author="dev",
            timestamp=datetime(2026, 1, 1),
            message="fix bug",
            changed_files=["app.py"],
            relevance_score=0.7,
        )
        assert c.hash == "abc123"
        assert c.relevance_score == 0.7

    def test_default_score(self):
        c = CommitInfo(hash="x", author="y")
        assert c.relevance_score == 0.0


class TestBugContext:
    def test_context_hash_deterministic(self, sample_error_info, sample_commits):
        ctx1 = BugContext(error_info=sample_error_info, relevant_commits=sample_commits)
        ctx2 = BugContext(error_info=sample_error_info, relevant_commits=sample_commits)
        assert ctx1.context_hash() == ctx2.context_hash()

    def test_context_hash_varies(self, sample_error_info, sample_commits):
        ctx1 = BugContext(error_info=sample_error_info, relevant_commits=sample_commits)
        other_err = ErrorInfo(error_type="KeyError", message="missing key")
        ctx2 = BugContext(error_info=other_err, relevant_commits=sample_commits)
        assert ctx1.context_hash() != ctx2.context_hash()


class TestExplanation:
    def test_defaults(self):
        exp = Explanation(summary="test")
        assert exp.summary == "test"
        assert exp.root_cause == ""
        assert exp.fix_suggestions == []
        assert exp.educational_notes == []

    def test_with_fix_suggestions(self):
        fix = FixSuggestion(
            description="Add null check",
            code_example="if x is None: return",
            rationale="Prevent NoneType errors",
            difficulty="easy",
        )
        exp = Explanation(summary="Bug found", fix_suggestions=[fix])
        assert len(exp.fix_suggestions) == 1
        assert exp.fix_suggestions[0].difficulty == "easy"


class TestAnalysisResult:
    def test_defaults(self, sample_error_info):
        result = AnalysisResult(error_info=sample_error_info)
        assert result.root_cause is None
        assert result.explanation is None
        assert result.relevant_commits == []
        assert result.limitations == []
        assert result.analysis_time_seconds == 0.0


class TestRootCause:
    def test_with_commit(self, sample_commits):
        rc = RootCause(
            commit=sample_commits[0],
            description="Found it",
            confidence=0.9,
        )
        assert rc.commit.hash == "abc1234"
        assert rc.confidence == 0.9
