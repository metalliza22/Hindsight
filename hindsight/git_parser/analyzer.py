"""Git repository analysis for identifying bug-related commits."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from git import InvalidGitRepositoryError, NoSuchPathError, Repo
from git.exc import GitCommandError

from hindsight.models import CommitInfo, ErrorInfo, ErrorLocation, FileChanges

logger = logging.getLogger(__name__)


class GitAnalyzerError(Exception):
    """Raised when git analysis encounters an error."""


class GitAnalyzer:
    """Examines git repository history to identify relevant commits and code changes."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        self._repo: Optional[Repo] = None

    def validate_repository(self) -> bool:
        """Check if the path is a valid git repository."""
        try:
            self._repo = Repo(self.repo_path)
            return not self._repo.bare
        except (InvalidGitRepositoryError, NoSuchPathError):
            return False

    @property
    def repo(self) -> Repo:
        if self._repo is None:
            if not self.validate_repository():
                raise GitAnalyzerError(
                    f"Not a valid git repository: {self.repo_path}"
                )
        return self._repo

    def analyze_commits(
        self, error_info: ErrorInfo, limit: int = 50
    ) -> List[CommitInfo]:
        """Analyze recent commits and find ones relevant to the error.

        Examines the last `limit` commits and identifies those that touched
        files mentioned in the error traceback.
        """
        try:
            commits = list(self.repo.iter_commits(max_count=limit))
        except GitCommandError as e:
            logger.error("Failed to read commit history: %s", e)
            return []

        affected_files = set(error_info.affected_files)
        # Also extract files from stack frames
        for frame in error_info.stack_trace:
            affected_files.add(frame.file_path)

        result: List[CommitInfo] = []
        for commit in commits:
            changed = self._get_changed_files(commit)
            # Check if any changed file overlaps with affected files
            overlap = self._files_overlap(changed, affected_files)
            relevance = self._compute_relevance(
                commit, changed, affected_files, error_info
            )

            commit_info = CommitInfo(
                hash=commit.hexsha[:8],
                author=str(commit.author),
                timestamp=datetime.fromtimestamp(commit.committed_date),
                message=commit.message.strip(),
                changed_files=changed,
                diff=self._get_commit_diff(commit),
                relevance_score=relevance if overlap else 0.0,
            )
            result.append(commit_info)

        return result

    def get_file_changes(self, commit_hash: str, file_path: str) -> FileChanges:
        """Get detailed file changes for a specific commit and file."""
        try:
            commit = self.repo.commit(commit_hash)
        except Exception as e:
            logger.error("Could not find commit %s: %s", commit_hash, e)
            return FileChanges(file_path=file_path)

        additions = []
        deletions = []
        diff_text = ""

        try:
            parent = commit.parents[0] if commit.parents else self.repo.tree("4b825dc642cb6eb9a060e54bf899d69f82e25eb3")
            diffs = parent.diff(commit, create_patch=True)
            for d in diffs:
                target = d.b_path or d.a_path
                if target and self._path_matches(target, file_path):
                    diff_text = d.diff.decode("utf-8", errors="replace") if isinstance(d.diff, bytes) else str(d.diff)
                    for line in diff_text.splitlines():
                        if line.startswith("+") and not line.startswith("+++"):
                            additions.append(line[1:])
                        elif line.startswith("-") and not line.startswith("---"):
                            deletions.append(line[1:])
                    break
        except Exception as e:
            logger.debug("Error getting file changes: %s", e)

        return FileChanges(
            file_path=file_path,
            additions=additions,
            deletions=deletions,
            diff=diff_text,
        )

    def prioritize_commits(
        self, commits: List[CommitInfo], error_location: ErrorLocation
    ) -> List[CommitInfo]:
        """Re-rank commits by relevance to a specific error location."""
        for commit in commits:
            bonus = 0.0
            for cf in commit.changed_files:
                if self._path_matches(cf, error_location.file_path):
                    bonus += 0.3
                    break
            # Recency bonus - more recent commits get higher scores
            commit.relevance_score += bonus

        return sorted(commits, key=lambda c: c.relevance_score, reverse=True)

    def get_total_commit_count(self) -> int:
        """Return the total number of commits in the repository."""
        try:
            return int(self.repo.git.rev_list("--count", "HEAD"))
        except GitCommandError:
            return 0

    # --- Private helpers ---

    def _get_changed_files(self, commit) -> List[str]:
        """Get list of files changed in a commit."""
        try:
            if commit.parents:
                diffs = commit.parents[0].diff(commit)
            else:
                diffs = commit.diff(None)
            files = []
            for d in diffs:
                if d.b_path:
                    files.append(d.b_path)
                elif d.a_path:
                    files.append(d.a_path)
            return files
        except Exception:
            return []

    def _get_commit_diff(self, commit) -> str:
        """Get the full diff text for a commit."""
        try:
            if commit.parents:
                return self.repo.git.diff(commit.parents[0].hexsha, commit.hexsha)
            else:
                return self.repo.git.show(commit.hexsha, format="", p=True)
        except GitCommandError:
            return ""

    @staticmethod
    def _files_overlap(changed: List[str], affected: set) -> bool:
        for cf in changed:
            for af in affected:
                if cf.endswith(af) or af.endswith(cf) or Path(cf).name == Path(af).name:
                    return True
        return False

    @staticmethod
    def _path_matches(path_a: str, path_b: str) -> bool:
        return (
            path_a == path_b
            or path_a.endswith(path_b)
            or path_b.endswith(path_a)
            or Path(path_a).name == Path(path_b).name
        )

    @staticmethod
    def _compute_relevance(
        commit, changed: List[str], affected: set, error_info: ErrorInfo
    ) -> float:
        """Score a commit's relevance to the error (0.0 to 1.0)."""
        score = 0.0

        # File overlap score
        overlap_count = sum(
            1
            for cf in changed
            for af in affected
            if cf.endswith(af) or af.endswith(cf) or Path(cf).name == Path(af).name
        )
        if overlap_count > 0:
            score += min(0.5, overlap_count * 0.15)

        # Recency score (based on age in days)
        age_days = (datetime.now() - datetime.fromtimestamp(commit.committed_date)).days
        if age_days <= 1:
            score += 0.3
        elif age_days <= 7:
            score += 0.2
        elif age_days <= 30:
            score += 0.1

        # Message keywords
        msg_lower = commit.message.lower()
        for keyword in ("fix", "bug", "error", "patch", "hotfix", "revert"):
            if keyword in msg_lower:
                score += 0.1
                break

        return min(1.0, score)
