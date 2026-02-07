"""Core orchestrator for the Hindsight analysis pipeline."""

from __future__ import annotations

import logging
import re
import time
from typing import List, Optional

from hindsight.cache import CacheManager
from hindsight.config import Config, get_api_key
from hindsight.explainer.ai_explainer import BugExplainer
from hindsight.git_parser.analyzer import GitAnalyzer, GitAnalyzerError
from hindsight.intent_extractor.parser import IntentExtractor
from hindsight.models import (
    AnalysisResult,
    BugContext,
    CommitInfo,
    ErrorInfo,
    ErrorLocation,
    IntentInfo,
    RepositoryContext,
    RootCause,
    StackFrame,
)

logger = logging.getLogger(__name__)

# Common Python error type patterns
ERROR_TYPE_PATTERNS = {
    "TypeError": "type_error",
    "AttributeError": "attribute_error",
    "NameError": "name_error",
    "ValueError": "value_error",
    "KeyError": "key_error",
    "IndexError": "index_error",
    "ImportError": "import_error",
    "ModuleNotFoundError": "import_error",
    "FileNotFoundError": "file_error",
    "IOError": "io_error",
    "OSError": "os_error",
    "RuntimeError": "runtime_error",
    "ZeroDivisionError": "math_error",
    "StopIteration": "iteration_error",
    "RecursionError": "recursion_error",
    "MemoryError": "resource_error",
    "OverflowError": "math_error",
    "SyntaxError": "syntax_error",
    "IndentationError": "syntax_error",
    "AssertionError": "assertion_error",
    "NotImplementedError": "not_implemented",
    "PermissionError": "permission_error",
    "TimeoutError": "timeout_error",
    "ConnectionError": "network_error",
}

# Regex for Python traceback parsing
TRACEBACK_HEADER = re.compile(r"Traceback \(most recent call last\):")
FRAME_PATTERN = re.compile(
    r'\s*File "(.+?)", line (\d+), in (.+)'
)
ERROR_LINE_PATTERN = re.compile(r"^(\w+(?:\.\w+)*(?:Error|Exception|Warning))\s*:\s*(.*)")
SIMPLE_ERROR_PATTERN = re.compile(r"^(\w+(?:\.\w+)*)\s*:\s*(.*)")


class HindsightAnalyzer:
    """Orchestrates the entire Hindsight analysis pipeline."""

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self._cache: Optional[CacheManager] = None

        if self.config.cache.enabled:
            cache_dir = self.config.config_dir / "cache"
            self._cache = CacheManager(
                cache_dir=cache_dir,
                ttl=self.config.cache.ttl,
                max_size_mb=self.config.cache.max_size,
            )

    def analyze_bug(self, error_message: str, repo_path: str) -> AnalysisResult:
        """Run the full analysis pipeline: parse error -> git analysis -> intent extraction -> AI explanation."""
        start_time = time.time()
        limitations: List[str] = []

        # Step 1: Parse the error message
        error_info = self.parse_error_message(error_message)

        # Step 2: Git analysis
        git_analyzer = GitAnalyzer(repo_path)
        if not git_analyzer.validate_repository():
            return AnalysisResult(
                error_info=error_info,
                analysis_time_seconds=time.time() - start_time,
                limitations=["Not a valid git repository. Git analysis skipped."],
            )

        commits = git_analyzer.analyze_commits(
            error_info, limit=self.config.analysis.max_commits
        )

        # Prioritize commits if we have a specific error location
        if error_info.stack_trace:
            top_frame = error_info.stack_trace[-1]
            location = ErrorLocation(
                file_path=top_frame.file_path,
                line_number=top_frame.line_number,
                function_name=top_frame.function_name,
            )
            commits = git_analyzer.prioritize_commits(commits, location)

        relevant_commits = [c for c in commits if c.relevance_score > 0]

        # Step 3: Intent extraction
        intent_extractor = IntentExtractor()
        combined_intent = IntentInfo(file_path="(combined)")

        for file_path in error_info.affected_files:
            try:
                intent = intent_extractor.extract_from_file(file_path)
                combined_intent.docstring_intents.extend(intent.docstring_intents)
                combined_intent.test_intents.extend(intent.test_intents)
                combined_intent.comment_intents.extend(intent.comment_intents)
                combined_intent.pattern_intents.extend(intent.pattern_intents)
            except Exception as e:
                logger.debug("Intent extraction failed for %s: %s", file_path, e)
                limitations.append(f"Could not extract intent from {file_path}: {e}")

        # Step 4: Identify root cause
        root_cause = self.identify_root_cause(relevant_commits, combined_intent)

        # Step 5: Build context and generate AI explanation
        repo_context = RepositoryContext(
            repo_path=repo_path,
            total_commits=git_analyzer.get_total_commit_count(),
        )

        bug_context = BugContext(
            error_info=error_info,
            relevant_commits=relevant_commits,
            intent_info=combined_intent,
            repository_context=repo_context,
        )

        explanation = self._generate_explanation(bug_context, limitations)

        return AnalysisResult(
            error_info=error_info,
            root_cause=root_cause,
            explanation=explanation,
            relevant_commits=relevant_commits,
            intent_info=combined_intent,
            analysis_time_seconds=time.time() - start_time,
            limitations=limitations,
        )

    def parse_error_message(self, error_message: str) -> ErrorInfo:
        """Parse a Python error message / traceback into structured ErrorInfo."""
        lines = error_message.strip().splitlines()
        stack_frames: List[StackFrame] = []
        error_type = ""
        message = ""
        affected_files: List[str] = []
        line_numbers: List[int] = []

        i = 0
        # Look for traceback header
        while i < len(lines):
            if TRACEBACK_HEADER.match(lines[i]):
                i += 1
                break
            i += 1
        else:
            # No traceback header found; try to parse as simple error line
            return self._parse_simple_error(error_message)

        # Parse stack frames
        while i < len(lines):
            frame_match = FRAME_PATTERN.match(lines[i])
            if frame_match:
                file_path = frame_match.group(1)
                line_num = int(frame_match.group(2))
                func_name = frame_match.group(3)
                code_ctx = ""
                if i + 1 < len(lines) and not FRAME_PATTERN.match(lines[i + 1]):
                    code_ctx = lines[i + 1].strip()
                    i += 1

                stack_frames.append(StackFrame(
                    file_path=file_path,
                    line_number=line_num,
                    function_name=func_name,
                    code_context=code_ctx,
                ))
                affected_files.append(file_path)
                line_numbers.append(line_num)
            else:
                # This might be the error line
                err_match = ERROR_LINE_PATTERN.match(lines[i].strip())
                if err_match:
                    error_type = err_match.group(1)
                    message = err_match.group(2)
                    break
                else:
                    simple_match = SIMPLE_ERROR_PATTERN.match(lines[i].strip())
                    if simple_match:
                        error_type = simple_match.group(1)
                        message = simple_match.group(2)
                        break
            i += 1

        # If we still don't have an error type, check the last line
        if not error_type and lines:
            last = lines[-1].strip()
            err_match = ERROR_LINE_PATTERN.match(last) or SIMPLE_ERROR_PATTERN.match(last)
            if err_match:
                error_type = err_match.group(1)
                message = err_match.group(2)

        return ErrorInfo(
            error_type=error_type or "UnknownError",
            message=message or error_message.strip(),
            stack_trace=stack_frames,
            affected_files=list(dict.fromkeys(affected_files)),  # dedupe, preserve order
            line_numbers=line_numbers,
            raw_traceback=error_message,
        )

    def identify_root_cause(
        self, commits: List[CommitInfo], intent: IntentInfo
    ) -> Optional[RootCause]:
        """Identify the most likely commit that introduced the bug."""
        if not commits:
            return None

        ranked = self.rank_commits_by_likelihood(commits)
        if not ranked:
            return None

        top = ranked[0]
        return RootCause(
            commit=top,
            description=f"Most likely introduced in commit {top.hash}: {top.message}",
            confidence=top.relevance_score,
        )

    def rank_commits_by_likelihood(
        self, commits: List[CommitInfo]
    ) -> List[CommitInfo]:
        """Rank commits by likelihood of causing the issue."""
        return sorted(commits, key=lambda c: c.relevance_score, reverse=True)

    def classify_error(self, error_type: str) -> str:
        """Categorize an error type into a general class."""
        return ERROR_TYPE_PATTERNS.get(error_type, "unknown_error")

    # --- Private helpers ---

    def _parse_simple_error(self, error_message: str) -> ErrorInfo:
        """Fallback parser for non-traceback error messages."""
        lines = error_message.strip().splitlines()
        error_type = "UnknownError"
        message = error_message.strip()

        for line in lines:
            match = ERROR_LINE_PATTERN.match(line.strip()) or SIMPLE_ERROR_PATTERN.match(line.strip())
            if match:
                error_type = match.group(1)
                message = match.group(2)
                break

        # Try to extract file references from the message
        file_refs = re.findall(r'["\']?([/\w.-]+\.py)["\']?', error_message)

        return ErrorInfo(
            error_type=error_type,
            message=message,
            affected_files=list(dict.fromkeys(file_refs)),
            raw_traceback=error_message,
        )

    def _generate_explanation(
        self, bug_context: BugContext, limitations: List[str]
    ):
        """Generate AI explanation, with caching and fallback."""
        from hindsight.models import Explanation

        # Check cache
        if self._cache:
            ctx_hash = bug_context.context_hash()
            cached = self._cache.get("ai_responses", ctx_hash)
            if cached:
                logger.info("Using cached AI explanation")
                return Explanation(
                    summary=cached.get("summary", ""),
                    root_cause=cached.get("root_cause", ""),
                    intent_vs_actual=cached.get("intent_vs_actual", ""),
                    commit_references=cached.get("commit_references", []),
                    fix_suggestions=[],
                    educational_notes=cached.get("educational_notes", []),
                )

        # Try AI explanation
        api_key = get_api_key()
        if not api_key:
            limitations.append(
                "No API key found. Set ANTHROPIC_API_KEY or HINDSIGHT_API_KEY "
                "environment variable for AI-powered explanations."
            )
            return self._basic_explanation(bug_context, limitations)

        try:
            explainer = BugExplainer(
                api_key=api_key,
                model=self.config.api.model,
                timeout=self.config.api.timeout,
                max_retries=self.config.api.max_retries,
            )
            explanation = explainer.generate_explanation(bug_context)

            # Cache the result
            if self._cache:
                self._cache.set("ai_responses", bug_context.context_hash(), {
                    "summary": explanation.summary,
                    "root_cause": explanation.root_cause,
                    "intent_vs_actual": explanation.intent_vs_actual,
                    "commit_references": explanation.commit_references,
                    "educational_notes": explanation.educational_notes,
                })

            return explanation

        except Exception as e:
            logger.error("AI explanation failed: %s", e)
            limitations.append(f"AI explanation failed: {e}")
            return self._basic_explanation(bug_context, limitations)

    @staticmethod
    def _basic_explanation(bug_context: BugContext, limitations: List[str]):
        """Generate a basic explanation without AI."""
        from hindsight.models import Explanation

        summary = f"{bug_context.error_info.error_type}: {bug_context.error_info.message}"

        root_cause = ""
        relevant = [c for c in bug_context.relevant_commits if c.relevance_score > 0]
        if relevant:
            top = relevant[0]
            root_cause = (
                f"Most likely related to commit {top.hash} by {top.author}: "
                f"{top.message}"
            )

        intent_vs_actual = ""
        if bug_context.intent_info:
            intents = bug_context.intent_info.docstring_intents
            if intents:
                intent_vs_actual = (
                    f"Intended behavior of `{intents[0].function_name}`: "
                    f"{intents[0].intended_behavior}"
                )

        return Explanation(
            summary=summary,
            root_cause=root_cause,
            intent_vs_actual=intent_vs_actual,
            commit_references=[f"{c.hash}: {c.message}" for c in relevant[:5]],
            educational_notes=limitations,
        )
