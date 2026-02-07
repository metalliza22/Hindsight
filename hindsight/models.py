"""Core data models for Hindsight."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class StackFrame:
    file_path: str
    line_number: int
    function_name: str
    code_context: str = ""


@dataclass
class ErrorInfo:
    error_type: str
    message: str
    stack_trace: List[StackFrame] = field(default_factory=list)
    affected_files: List[str] = field(default_factory=list)
    line_numbers: List[int] = field(default_factory=list)
    variable_context: Dict[str, Any] = field(default_factory=dict)
    raw_traceback: str = ""


@dataclass
class ErrorLocation:
    file_path: str
    line_number: int
    function_name: str = ""


@dataclass
class FileChanges:
    file_path: str
    additions: List[str] = field(default_factory=list)
    deletions: List[str] = field(default_factory=list)
    diff: str = ""


@dataclass
class CommitInfo:
    hash: str
    author: str
    timestamp: datetime = field(default_factory=datetime.now)
    message: str = ""
    changed_files: List[str] = field(default_factory=list)
    diff: str = ""
    relevance_score: float = 0.0


@dataclass
class DocstringIntent:
    function_name: str
    intended_behavior: str
    parameters: Dict[str, str] = field(default_factory=dict)
    return_description: str = ""
    examples: List[str] = field(default_factory=list)


@dataclass
class TestIntent:
    test_name: str
    expected_behavior: str
    tested_function: str = ""


@dataclass
class CommentIntent:
    line_number: int
    text: str
    intent_type: str = "inline"  # inline, block, todo, fixme


@dataclass
class PatternIntent:
    pattern_type: str  # e.g. "guard_clause", "retry_logic", "validation"
    description: str
    location: str = ""


@dataclass
class IntentInfo:
    file_path: str
    docstring_intents: List[DocstringIntent] = field(default_factory=list)
    test_intents: List[TestIntent] = field(default_factory=list)
    comment_intents: List[CommentIntent] = field(default_factory=list)
    pattern_intents: List[PatternIntent] = field(default_factory=list)


@dataclass
class RepositoryContext:
    repo_path: str
    total_commits: int = 0
    primary_language: str = "python"
    recent_activity: str = ""


@dataclass
class BugContext:
    error_info: ErrorInfo
    relevant_commits: List[CommitInfo] = field(default_factory=list)
    intent_info: Optional[IntentInfo] = None
    repository_context: Optional[RepositoryContext] = None

    def context_hash(self) -> str:
        data = json.dumps({
            "error_type": self.error_info.error_type,
            "message": self.error_info.message,
            "files": self.error_info.affected_files,
            "commits": [c.hash for c in self.relevant_commits],
        }, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass
class FixSuggestion:
    description: str
    code_example: str = ""
    rationale: str = ""
    difficulty: str = "medium"  # easy, medium, hard


@dataclass
class Explanation:
    summary: str
    root_cause: str = ""
    intent_vs_actual: str = ""
    commit_references: List[str] = field(default_factory=list)
    fix_suggestions: List[FixSuggestion] = field(default_factory=list)
    educational_notes: List[str] = field(default_factory=list)


@dataclass
class RootCause:
    commit: Optional[CommitInfo] = None
    description: str = ""
    confidence: float = 0.0
    affected_lines: List[int] = field(default_factory=list)


@dataclass
class AnalysisResult:
    error_info: ErrorInfo
    root_cause: Optional[RootCause] = None
    explanation: Optional[Explanation] = None
    relevant_commits: List[CommitInfo] = field(default_factory=list)
    intent_info: Optional[IntentInfo] = None
    analysis_time_seconds: float = 0.0
    limitations: List[str] = field(default_factory=list)
