"""Unit tests for the Git Analyzer component."""

import pytest

from hindsight.git_parser.analyzer import GitAnalyzer, GitAnalyzerError
from hindsight.models import CommitInfo, ErrorInfo, ErrorLocation, StackFrame


class TestGitAnalyzerValidation:
    def test_valid_repository(self, tmp_git_repo):
        analyzer = GitAnalyzer(str(tmp_git_repo))
        assert analyzer.validate_repository() is True

    def test_invalid_repository(self, tmp_path):
        analyzer = GitAnalyzer(str(tmp_path))
        assert analyzer.validate_repository() is False

    def test_nonexistent_path(self):
        analyzer = GitAnalyzer("/nonexistent/path/repo")
        assert analyzer.validate_repository() is False

    def test_repo_property_raises_on_invalid(self, tmp_path):
        analyzer = GitAnalyzer(str(tmp_path))
        with pytest.raises(GitAnalyzerError):
            _ = analyzer.repo


class TestGitAnalyzerCommits:
    def test_analyze_commits_returns_list(self, tmp_git_repo):
        analyzer = GitAnalyzer(str(tmp_git_repo))
        error_info = ErrorInfo(
            error_type="ValueError",
            message="name cannot be None",
            affected_files=["app.py"],
        )
        commits = analyzer.analyze_commits(error_info, limit=50)
        assert isinstance(commits, list)
        assert len(commits) > 0

    def test_analyze_commits_respects_limit(self, tmp_git_repo):
        analyzer = GitAnalyzer(str(tmp_git_repo))
        error_info = ErrorInfo(error_type="Error", message="test")
        commits = analyzer.analyze_commits(error_info, limit=2)
        assert len(commits) <= 2

    def test_analyze_commits_scores_relevant_files(self, tmp_git_repo):
        analyzer = GitAnalyzer(str(tmp_git_repo))
        error_info = ErrorInfo(
            error_type="Error",
            message="test",
            affected_files=["app.py"],
        )
        commits = analyzer.analyze_commits(error_info)
        # At least some commits should have non-zero relevance
        relevant = [c for c in commits if c.relevance_score > 0]
        assert len(relevant) > 0

    def test_analyze_commits_with_stack_trace(self, tmp_git_repo):
        analyzer = GitAnalyzer(str(tmp_git_repo))
        error_info = ErrorInfo(
            error_type="Error",
            message="test",
            stack_trace=[
                StackFrame(
                    file_path="service.py",
                    line_number=5,
                    function_name="serve_user",
                )
            ],
        )
        commits = analyzer.analyze_commits(error_info)
        assert isinstance(commits, list)


class TestGitAnalyzerFileChanges:
    def test_get_file_changes(self, tmp_git_repo):
        analyzer = GitAnalyzer(str(tmp_git_repo))
        error_info = ErrorInfo(error_type="Error", message="test", affected_files=["app.py"])
        commits = analyzer.analyze_commits(error_info)
        # Get changes for the second commit (which modified app.py)
        if len(commits) >= 2:
            changes = analyzer.get_file_changes(commits[1].hash, "app.py")
            assert changes.file_path == "app.py"

    def test_get_file_changes_nonexistent_commit(self, tmp_git_repo):
        analyzer = GitAnalyzer(str(tmp_git_repo))
        changes = analyzer.get_file_changes("nonexistent", "app.py")
        assert changes.file_path == "app.py"
        assert changes.diff == ""


class TestGitAnalyzerPrioritization:
    def test_prioritize_commits(self, tmp_git_repo):
        analyzer = GitAnalyzer(str(tmp_git_repo))
        error_info = ErrorInfo(
            error_type="Error", message="test", affected_files=["app.py"]
        )
        commits = analyzer.analyze_commits(error_info)
        location = ErrorLocation(file_path="app.py", line_number=3)
        prioritized = analyzer.prioritize_commits(commits, location)
        assert isinstance(prioritized, list)
        # First result should have highest relevance
        if len(prioritized) >= 2:
            assert prioritized[0].relevance_score >= prioritized[1].relevance_score

    def test_get_total_commit_count(self, tmp_git_repo):
        analyzer = GitAnalyzer(str(tmp_git_repo))
        analyzer.validate_repository()
        count = analyzer.get_total_commit_count()
        assert count == 3  # We created 3 commits in the fixture
