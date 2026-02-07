"""Unit tests for the AI Explainer component."""

from unittest.mock import MagicMock, patch
from datetime import datetime

import pytest

from hindsight.explainer.ai_explainer import BugExplainer
from hindsight.models import (
    BugContext,
    CommitInfo,
    ErrorInfo,
    Explanation,
    IntentInfo,
    DocstringIntent,
    StackFrame,
)


@pytest.fixture
def explainer():
    return BugExplainer(api_key="test-key", max_retries=0)


@pytest.fixture
def simple_bug_context():
    return BugContext(
        error_info=ErrorInfo(
            error_type="TypeError",
            message="bad type",
            stack_trace=[
                StackFrame(
                    file_path="app.py",
                    line_number=10,
                    function_name="run",
                    code_context="x.process()",
                )
            ],
            affected_files=["app.py"],
        ),
        relevant_commits=[
            CommitInfo(
                hash="abc123",
                author="dev",
                timestamp=datetime(2026, 1, 15),
                message="Refactor processing",
                changed_files=["app.py"],
                diff="- x = Thing()\n+ x = None",
                relevance_score=0.7,
            )
        ],
        intent_info=IntentInfo(
            file_path="app.py",
            docstring_intents=[
                DocstringIntent(
                    function_name="run",
                    intended_behavior="Process data through the pipeline",
                )
            ],
        ),
    )


class TestBugExplainerPromptBuilding:
    def test_build_prompt_includes_error_info(self, explainer, simple_bug_context):
        prompt = explainer._build_prompt(simple_bug_context)
        assert "TypeError" in prompt
        assert "bad type" in prompt
        assert "app.py" in prompt

    def test_build_prompt_includes_commits(self, explainer, simple_bug_context):
        prompt = explainer._build_prompt(simple_bug_context)
        assert "abc123" in prompt
        assert "Refactor processing" in prompt

    def test_build_prompt_includes_intent(self, explainer, simple_bug_context):
        prompt = explainer._build_prompt(simple_bug_context)
        assert "run" in prompt
        assert "Process data" in prompt

    def test_build_prompt_no_commits(self, explainer):
        ctx = BugContext(
            error_info=ErrorInfo(error_type="Error", message="test"),
        )
        prompt = explainer._build_prompt(ctx)
        assert "no relevant commits" in prompt.lower()


class TestResponseParsing:
    def test_parse_structured_response(self, explainer, simple_bug_context):
        raw = (
            "SUMMARY: The variable x was set to None.\n"
            "ROOT_CAUSE: Commit abc123 changed the initialization.\n"
            "INTENT_VS_ACTUAL: Intended to be a Thing, but got None.\n"
            "FIX_SUGGESTIONS:\n"
            "- Add a None check before calling process()\n"
            "- Restore the original Thing() initialization\n"
            "EDUCATIONAL_NOTES:\n"
            "- Always check for None before method calls\n"
            "- Use type hints to catch these issues earlier\n"
        )
        result = explainer._parse_response(raw, simple_bug_context)
        assert "None" in result.summary
        assert "abc123" in result.root_cause
        assert len(result.fix_suggestions) == 2
        assert len(result.educational_notes) == 2

    def test_parse_unstructured_response(self, explainer, simple_bug_context):
        raw = "This is just a plain text explanation without sections."
        result = explainer._parse_response(raw, simple_bug_context)
        assert result.summary == raw.strip()

    def test_parse_partial_response(self, explainer, simple_bug_context):
        raw = "SUMMARY: Something broke.\nROOT_CAUSE: Unknown."
        result = explainer._parse_response(raw, simple_bug_context)
        assert "broke" in result.summary
        assert result.root_cause == "Unknown."


class TestFallbackExplanation:
    def test_fallback_includes_error(self, explainer, simple_bug_context):
        result = explainer._fallback_explanation(simple_bug_context)
        assert "TypeError" in result.summary
        assert "bad type" in result.summary

    def test_fallback_includes_commit(self, explainer, simple_bug_context):
        result = explainer._fallback_explanation(simple_bug_context)
        assert "abc123" in result.root_cause

    def test_fallback_with_no_commits(self, explainer):
        ctx = BugContext(error_info=ErrorInfo(error_type="Error", message="fail"))
        result = explainer._fallback_explanation(ctx)
        assert "Error" in result.summary
        assert result.root_cause == ""


class TestFixSuggestionParsing:
    def test_parse_bullet_list(self):
        text = "- Add null check\n- Use optional chaining\n"
        result = BugExplainer._parse_fix_suggestions(text)
        assert len(result) == 2
        assert result[0].description == "Add null check"

    def test_parse_structured_suggestions(self):
        text = (
            "DESCRIPTION: Add a guard clause\n"
            "CODE: if x is None: return\n"
            "RATIONALE: Prevents NoneType errors\n"
            "DIFFICULTY: easy\n"
        )
        result = BugExplainer._parse_fix_suggestions(text)
        assert len(result) == 1
        assert result[0].description == "Add a guard clause"
        assert result[0].difficulty == "easy"

    def test_parse_empty_text(self):
        assert BugExplainer._parse_fix_suggestions("") == []


class TestCommitReferences:
    def test_include_references(self, explainer):
        commits = [
            CommitInfo(
                hash="abc123",
                author="dev",
                timestamp=datetime(2026, 1, 1),
                message="fix",
                relevance_score=0.5,
            )
        ]
        result = explainer.include_commit_references("Explanation text", commits)
        assert "abc123" in result
        assert "fix" in result

    def test_no_relevant_commits(self, explainer):
        commits = [
            CommitInfo(hash="x", author="y", relevance_score=0.0)
        ]
        result = explainer.include_commit_references("Text", commits)
        assert result == "Text"

    def test_empty_commits(self, explainer):
        result = explainer.include_commit_references("Text", [])
        assert result == "Text"


class TestAPICallWithMock:
    def test_generate_explanation_with_mock(self, simple_bug_context):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="SUMMARY: Mocked explanation.\nROOT_CAUSE: Test.")]
        mock_client.messages.create.return_value = mock_response

        explainer = BugExplainer(api_key="test-key", max_retries=0)
        explainer._client = mock_client

        result = explainer.generate_explanation(simple_bug_context)
        assert "Mocked explanation" in result.summary
        mock_client.messages.create.assert_called_once()

    def test_generate_falls_back_on_api_failure(self, simple_bug_context):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API error")

        explainer = BugExplainer(api_key="test-key", max_retries=0)
        explainer._client = mock_client

        result = explainer.generate_explanation(simple_bug_context)
        assert isinstance(result, Explanation)
        # Should use fallback
        assert "TypeError" in result.summary
