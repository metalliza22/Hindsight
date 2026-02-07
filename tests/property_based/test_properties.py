"""Property-based tests for Hindsight using Hypothesis.

Each test references the corresponding property from the design document.
"""

import ast
import os
import string
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from hindsight.analyzer.hindsight_analyzer import HindsightAnalyzer
from hindsight.cache import CacheManager
from hindsight.config import Config
from hindsight.intent_extractor.parser import IntentExtractor
from hindsight.models import (
    CommitInfo,
    ErrorInfo,
    Explanation,
    FixSuggestion,
    IntentInfo,
    StackFrame,
)


# --- Strategies ---

error_types = st.sampled_from([
    "TypeError", "AttributeError", "NameError", "ValueError",
    "KeyError", "IndexError", "ImportError", "FileNotFoundError",
    "RuntimeError", "ZeroDivisionError", "AssertionError",
])

python_identifiers = st.from_regex(r"[a-z][a-z0-9_]{0,20}", fullmatch=True)

file_paths = st.builds(
    lambda name: f"{name}.py",
    python_identifiers,
)

line_numbers = st.integers(min_value=1, max_value=10000)

error_messages = st.text(
    alphabet=string.printable,
    min_size=1,
    max_size=200,
).filter(lambda s: s.strip())

commit_hashes = st.text(
    alphabet=string.hexdigits[:16],
    min_size=7,
    max_size=8,
)

relevance_scores = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)

commit_infos = st.builds(
    CommitInfo,
    hash=commit_hashes,
    author=python_identifiers,
    timestamp=st.datetimes(
        min_value=datetime(2020, 1, 1),
        max_value=datetime(2026, 12, 31),
    ),
    message=st.text(min_size=1, max_size=100).filter(lambda s: s.strip()),
    changed_files=st.lists(file_paths, min_size=0, max_size=5),
    relevance_score=relevance_scores,
)

stack_frames = st.builds(
    StackFrame,
    file_path=file_paths,
    line_number=line_numbers,
    function_name=python_identifiers,
    code_context=st.text(max_size=100),
)

error_infos = st.builds(
    ErrorInfo,
    error_type=error_types,
    message=error_messages,
    stack_trace=st.lists(stack_frames, min_size=0, max_size=5),
    affected_files=st.lists(file_paths, min_size=0, max_size=5),
    line_numbers=st.lists(line_numbers, min_size=0, max_size=5),
)


# --- Property Tests ---


class TestGitAnalysisProperties:
    """
    Feature: hindsight, Property 1: Git Analysis Completeness
    For any bug report with valid repository, the Git_Analyzer should examine
    exactly the last 50 commits (or all commits if fewer than 50 exist) and
    return relevant commits prioritized by recency and relevance to error location.
    """

    @given(error_info=error_infos)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_analyze_commits_returns_bounded_list(self, error_info, tmp_git_repo):
        """Property 1: Commit analysis returns at most `limit` commits."""
        from hindsight.git_parser.analyzer import GitAnalyzer
        analyzer = GitAnalyzer(str(tmp_git_repo))
        limit = 50
        commits = analyzer.analyze_commits(error_info, limit=limit)
        assert len(commits) <= limit
        assert all(isinstance(c, CommitInfo) for c in commits)

    """
    Feature: hindsight, Property 3: Repository Validation
    For any invalid git repository, the Git_Analyzer should return an
    appropriate error message without crashing.
    """

    @given(path_suffix=st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=10))
    @settings(max_examples=20)
    def test_invalid_repo_does_not_crash(self, path_suffix):
        """Property 3: Invalid repository paths don't cause crashes."""
        from hindsight.git_parser.analyzer import GitAnalyzer
        analyzer = GitAnalyzer(f"/tmp/nonexistent_{path_suffix}")
        assert analyzer.validate_repository() is False


class TestIntentExtractionProperties:
    """
    Feature: hindsight, Property 4: Intent Extraction Completeness
    For any valid Python source file, the Intent_Extractor should parse all
    docstrings, comments, and code patterns, returning structured intent
    information for each relevant code section.
    """

    @given(
        func_name=python_identifiers,
        docstring=st.text(min_size=5, max_size=200).filter(lambda s: s.strip() and '"""' not in s and "'''" not in s),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_docstring_extraction_completeness(self, func_name, docstring, tmp_path):
        """Property 4: All function docstrings are extracted."""
        source = f'def {func_name}():\n    """{docstring}"""\n    pass\n'
        file_path = tmp_path / f"{func_name}.py"
        file_path.write_text(source)

        extractor = IntentExtractor()
        intent = extractor.extract_from_file(str(file_path))
        assert len(intent.docstring_intents) == 1
        assert intent.docstring_intents[0].function_name == func_name

    @given(
        comment_text=st.text(
            alphabet=string.ascii_letters + string.digits + " ",
            min_size=3,
            max_size=100,
        ).filter(lambda s: s.strip()),
    )
    @settings(max_examples=50)
    def test_comment_extraction(self, comment_text):
        """Property 4: All comments are extracted from source."""
        source = f"x = 1\n# {comment_text}\ny = 2\n"
        extractor = IntentExtractor()
        comments = extractor.extract_comments(source)
        assert len(comments) >= 1
        assert any(comment_text.strip() in c.text for c in comments)

    """
    Feature: hindsight, Property 5: Test Case Analysis
    For any test file, the Intent_Extractor should identify all test cases
    and extract their expected functionality descriptions.
    """

    @given(
        test_names=st.lists(
            python_identifiers,
            min_size=1,
            max_size=5,
            unique=True,
        ),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_all_test_cases_found(self, test_names, tmp_path):
        """Property 5: All test functions are identified."""
        lines = []
        for name in test_names:
            lines.append(f"def test_{name}():\n    assert True\n\n")
        source = "".join(lines)

        file_path = tmp_path / "test_generated.py"
        file_path.write_text(source)

        extractor = IntentExtractor()
        intents = extractor.analyze_test_cases(str(file_path))
        found_names = {t.test_name for t in intents}
        for name in test_names:
            assert f"test_{name}" in found_names


class TestErrorParsingProperties:
    """
    Feature: hindsight, Property 14: Stack Trace Parsing
    For any valid Python stack trace, the system should extract the complete
    call chain, affected files, line numbers, and available variable context.
    """

    @given(
        frames=st.lists(
            st.tuples(file_paths, line_numbers, python_identifiers),
            min_size=1,
            max_size=5,
        ),
        error_type=error_types,
        message=error_messages,
    )
    @settings(max_examples=50)
    def test_stack_trace_parsing_completeness(self, frames, error_type, message):
        """Property 14: All frames are extracted from valid tracebacks."""
        # Build a synthetic traceback
        lines = ["Traceback (most recent call last):"]
        for fp, ln, fn in frames:
            lines.append(f'  File "{fp}", line {ln}, in {fn}')
            lines.append(f"    some_code()")
        lines.append(f"{error_type}: {message}")
        traceback_str = "\n".join(lines)

        analyzer = HindsightAnalyzer(Config())
        result = analyzer.parse_error_message(traceback_str)

        assert result.error_type == error_type
        assert len(result.stack_trace) == len(frames)
        for i, (fp, ln, fn) in enumerate(frames):
            assert result.stack_trace[i].file_path == fp
            assert result.stack_trace[i].line_number == ln
            assert result.stack_trace[i].function_name == fn

    """
    Feature: hindsight, Property 15: Error Classification
    For any recognized error type, the system should categorize it.
    """

    @given(error_type=error_types)
    @settings(max_examples=20)
    def test_error_classification(self, error_type):
        """Property 15: All known error types are classified."""
        analyzer = HindsightAnalyzer(Config())
        category = analyzer.classify_error(error_type)
        assert category != "unknown_error"

    """
    Feature: hindsight, Property 16: Fallback Analysis
    For any unrecognized error format, the system should attempt generic
    analysis using available information rather than failing completely.
    """

    @given(text=st.text(min_size=1, max_size=500).filter(lambda s: s.strip()))
    @settings(max_examples=50)
    def test_fallback_never_crashes(self, text):
        """Property 16: Arbitrary input never crashes the parser."""
        analyzer = HindsightAnalyzer(Config())
        result = analyzer.parse_error_message(text)
        assert result is not None
        assert isinstance(result, ErrorInfo)
        assert result.error_type != ""


class TestCommitRankingProperties:
    """
    Feature: hindsight, Property 9: Multi-Commit Ranking
    For any scenario involving multiple relevant commits, the system should
    rank them by likelihood of causing the issue.
    """

    @given(
        scores=st.lists(
            relevance_scores,
            min_size=2,
            max_size=20,
        ),
    )
    @settings(max_examples=50)
    def test_ranking_is_sorted_descending(self, scores):
        """Property 9: Ranked commits are sorted by relevance score (descending)."""
        commits = [
            CommitInfo(hash=f"{i:07x}", author="dev", relevance_score=s)
            for i, s in enumerate(scores)
        ]
        analyzer = HindsightAnalyzer(Config())
        ranked = analyzer.rank_commits_by_likelihood(commits)
        for i in range(len(ranked) - 1):
            assert ranked[i].relevance_score >= ranked[i + 1].relevance_score


class TestCacheProperties:
    """
    Feature: hindsight, Property 17: Configuration Management
    Cache operations should be consistent and reliable.
    """

    @given(
        key=st.text(min_size=1, max_size=50).filter(lambda s: s.strip()),
        value=st.dictionaries(
            st.text(min_size=1, max_size=20),
            st.one_of(st.integers(), st.text(max_size=50), st.booleans()),
            min_size=1,
            max_size=5,
        ),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_cache_roundtrip(self, key, value, tmp_path):
        """Property: Cached values can be retrieved correctly."""
        cache = CacheManager(cache_dir=tmp_path / "cache", ttl=3600)
        cache.set("git_analysis", key, value)
        result = cache.get("git_analysis", key)
        assert result == value

    @given(
        key=st.text(min_size=1, max_size=50).filter(lambda s: s.strip()),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_cache_miss_returns_none(self, key, tmp_path):
        """Property: Missing cache entries return None."""
        cache = CacheManager(cache_dir=tmp_path / "cache", ttl=3600)
        assert cache.get("git_analysis", key) is None


class TestExplanationProperties:
    """
    Feature: hindsight, Property 10: Analysis Limitation Handling
    For any scenario where no clear root cause can be identified, the system
    should explain the analysis limitations.
    """

    @given(error_info=error_infos)
    @settings(max_examples=20)
    def test_no_root_cause_when_no_commits(self, error_info):
        """Property 10: Empty commit list yields None root cause."""
        analyzer = HindsightAnalyzer(Config())
        intent = IntentInfo(file_path="test.py")
        rc = analyzer.identify_root_cause([], intent)
        assert rc is None
