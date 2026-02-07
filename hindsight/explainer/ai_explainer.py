"""AI-powered explanation generation using Anthropic Claude API."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import List, Optional

from hindsight.models import (
    BugContext,
    CommitInfo,
    Explanation,
    FixSuggestion,
    IntentInfo,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are Hindsight, an AI debugging assistant that explains why bugs happen.
Given error information, git history, and developer intent signals, provide:
1. A clear summary of what went wrong
2. The root cause, referencing specific commits
3. How the developer's intent differs from actual behavior
4. Concrete fix suggestions with code examples
5. Educational notes to help the developer learn

Be concise, specific, and reference actual code/commits. Format your response as structured sections.
"""

ANALYSIS_PROMPT_TEMPLATE = """\
## Error Information
- **Type**: {error_type}
- **Message**: {error_message}
- **Affected Files**: {affected_files}
- **Stack Trace**:
{stack_trace}

## Recent Relevant Commits
{commits_section}

## Developer Intent Signals
{intent_section}

---

Analyze this bug and provide your explanation in the following format:

SUMMARY: <one-paragraph summary>

ROOT_CAUSE: <explain the root cause, referencing specific commits>

INTENT_VS_ACTUAL: <how the developer's intent differs from actual behavior>

FIX_SUGGESTIONS:
- <suggestion 1>
- <suggestion 2>

EDUCATIONAL_NOTES:
- <learning point 1>
- <learning point 2>
"""


class BugExplainer:
    """Generates human-readable bug explanations using Claude AI."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514", timeout: int = 30, max_retries: int = 3):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = None

    @property
    def client(self):
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self.api_key)
            except ImportError:
                raise RuntimeError(
                    "anthropic package is required. Install with: pip install anthropic"
                )
        return self._client

    def generate_explanation(self, bug_context: BugContext) -> Explanation:
        """Generate a complete bug explanation from the analysis context."""
        prompt = self._build_prompt(bug_context)
        raw = self._call_api(prompt)

        if raw is None:
            return self._fallback_explanation(bug_context)

        return self._parse_response(raw, bug_context)

    async def generate_explanation_async(self, bug_context: BugContext) -> Explanation:
        """Async version of generate_explanation."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.generate_explanation, bug_context)

    def suggest_fixes(
        self, intent: IntentInfo, actual_behavior: str
    ) -> List[FixSuggestion]:
        """Generate fix suggestions based on intent vs actual behavior."""
        prompt = (
            f"Given the developer's intent:\n"
            f"- Docstrings: {[d.intended_behavior for d in intent.docstring_intents]}\n"
            f"- Test expectations: {[t.expected_behavior for t in intent.test_intents]}\n\n"
            f"And the actual behavior:\n{actual_behavior}\n\n"
            f"Provide 2-3 concrete fix suggestions. For each, give:\n"
            f"DESCRIPTION: <what to do>\nCODE: <code example>\nRATIONALE: <why>\nDIFFICULTY: <easy/medium/hard>"
        )

        raw = self._call_api(prompt)
        if raw is None:
            return []

        return self._parse_fix_suggestions(raw)

    def format_for_education(self, explanation: str) -> str:
        """Reformat an explanation to be more educational."""
        prompt = (
            f"Rewrite this debugging explanation to be more educational. "
            f"Add context about why this type of bug happens commonly and how "
            f"to prevent it in the future:\n\n{explanation}"
        )
        result = self._call_api(prompt)
        return result or explanation

    def include_commit_references(
        self, explanation: str, commits: List[CommitInfo]
    ) -> str:
        """Enrich an explanation with specific commit references."""
        if not commits:
            return explanation

        refs = "\n".join(
            f"  - {c.hash}: {c.message} (by {c.author}, {c.timestamp.strftime('%Y-%m-%d')})"
            for c in commits
            if c.relevance_score > 0
        )
        if refs:
            return f"{explanation}\n\nRelevant Commits:\n{refs}"
        return explanation

    # --- Private helpers ---

    def _build_prompt(self, ctx: BugContext) -> str:
        # Stack trace section
        stack_lines = []
        for frame in ctx.error_info.stack_trace:
            stack_lines.append(
                f'  File "{frame.file_path}", line {frame.line_number}, in {frame.function_name}'
            )
            if frame.code_context:
                stack_lines.append(f"    {frame.code_context}")
        stack_trace = "\n".join(stack_lines) or "(no stack trace available)"

        # Commits section
        relevant = [c for c in ctx.relevant_commits if c.relevance_score > 0]
        relevant.sort(key=lambda c: c.relevance_score, reverse=True)
        commits_parts = []
        for c in relevant[:10]:
            commits_parts.append(
                f"### Commit {c.hash} (score: {c.relevance_score:.2f})\n"
                f"Author: {c.author} | Date: {c.timestamp.strftime('%Y-%m-%d %H:%M')}\n"
                f"Message: {c.message}\n"
                f"Changed files: {', '.join(c.changed_files)}\n"
                f"Diff:\n```\n{c.diff[:2000]}\n```"
            )
        commits_section = "\n\n".join(commits_parts) or "(no relevant commits found)"

        # Intent section
        intent_parts = []
        if ctx.intent_info:
            for d in ctx.intent_info.docstring_intents:
                intent_parts.append(f"- Function `{d.function_name}`: {d.intended_behavior}")
            for t in ctx.intent_info.test_intents:
                intent_parts.append(f"- Test `{t.test_name}`: expects {t.expected_behavior}")
            for c in ctx.intent_info.comment_intents:
                if c.intent_type in ("todo", "fixme", "note", "workaround"):
                    intent_parts.append(f"- [{c.intent_type.upper()}] line {c.line_number}: {c.text}")
        intent_section = "\n".join(intent_parts) or "(no intent signals found)"

        return ANALYSIS_PROMPT_TEMPLATE.format(
            error_type=ctx.error_info.error_type,
            error_message=ctx.error_info.message,
            affected_files=", ".join(ctx.error_info.affected_files) or "(unknown)",
            stack_trace=stack_trace,
            commits_section=commits_section,
            intent_section=intent_section,
        )

    def _call_api(self, prompt: str) -> Optional[str]:
        """Call Claude API with retry and exponential backoff."""
        last_error = None

        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=2048,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.content[0].text
            except Exception as e:
                last_error = e
                logger.warning(
                    "API call failed (attempt %d/%d): %s",
                    attempt + 1,
                    self.max_retries + 1,
                    e,
                )
                if attempt < self.max_retries:
                    wait = 2 ** (attempt + 1)
                    time.sleep(wait)

        logger.error("All API attempts failed: %s", last_error)
        return None

    def _parse_response(self, raw: str, ctx: BugContext) -> Explanation:
        """Parse structured sections from the AI response."""
        sections = {
            "SUMMARY": "",
            "ROOT_CAUSE": "",
            "INTENT_VS_ACTUAL": "",
            "FIX_SUGGESTIONS": "",
            "EDUCATIONAL_NOTES": "",
        }

        current_key = None
        lines_buf: List[str] = []

        for line in raw.splitlines():
            stripped = line.strip()
            matched = False
            for key in sections:
                if stripped.startswith(f"{key}:"):
                    if current_key:
                        sections[current_key] = "\n".join(lines_buf).strip()
                    current_key = key
                    remainder = stripped[len(key) + 1:].strip()
                    lines_buf = [remainder] if remainder else []
                    matched = True
                    break
            if not matched and current_key is not None:
                lines_buf.append(line)

        if current_key:
            sections[current_key] = "\n".join(lines_buf).strip()

        # If parsing failed, use the raw response as summary
        if not any(sections.values()):
            return Explanation(summary=raw.strip())

        # Parse fix suggestions into structured objects
        fix_suggestions = self._parse_fix_suggestions(sections["FIX_SUGGESTIONS"])

        # Parse educational notes into a list
        edu_notes = [
            line.lstrip("- ").strip()
            for line in sections["EDUCATIONAL_NOTES"].splitlines()
            if line.strip() and line.strip() != "-"
        ]

        # Commit references
        commit_refs = [
            f"{c.hash}: {c.message}"
            for c in ctx.relevant_commits
            if c.relevance_score > 0
        ]

        return Explanation(
            summary=sections["SUMMARY"],
            root_cause=sections["ROOT_CAUSE"],
            intent_vs_actual=sections["INTENT_VS_ACTUAL"],
            commit_references=commit_refs,
            fix_suggestions=fix_suggestions,
            educational_notes=edu_notes,
        )

    @staticmethod
    def _parse_fix_suggestions(text: str) -> List[FixSuggestion]:
        """Parse fix suggestions from text."""
        if not text.strip():
            return []

        suggestions: List[FixSuggestion] = []
        current_desc = ""
        current_code = ""
        current_rationale = ""
        current_difficulty = "medium"

        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("DESCRIPTION:"):
                if current_desc:
                    suggestions.append(FixSuggestion(
                        description=current_desc,
                        code_example=current_code.strip(),
                        rationale=current_rationale,
                        difficulty=current_difficulty,
                    ))
                current_desc = stripped[len("DESCRIPTION:"):].strip()
                current_code = ""
                current_rationale = ""
                current_difficulty = "medium"
            elif stripped.startswith("CODE:"):
                current_code = stripped[len("CODE:"):].strip()
            elif stripped.startswith("RATIONALE:"):
                current_rationale = stripped[len("RATIONALE:"):].strip()
            elif stripped.startswith("DIFFICULTY:"):
                current_difficulty = stripped[len("DIFFICULTY:"):].strip().lower()
            elif stripped.startswith("- ") and not current_desc:
                # Simple bullet-point list of suggestions
                suggestions.append(FixSuggestion(description=stripped[2:].strip()))
            elif current_code is not None and current_desc:
                current_code += "\n" + line

        if current_desc:
            suggestions.append(FixSuggestion(
                description=current_desc,
                code_example=current_code.strip(),
                rationale=current_rationale,
                difficulty=current_difficulty,
            ))

        return suggestions

    @staticmethod
    def _fallback_explanation(ctx: BugContext) -> Explanation:
        """Generate a basic explanation without AI when API is unavailable."""
        summary = (
            f"Error: {ctx.error_info.error_type}: {ctx.error_info.message}"
        )
        root_cause = ""
        relevant = [c for c in ctx.relevant_commits if c.relevance_score > 0]
        if relevant:
            top = relevant[0]
            root_cause = (
                f"Most likely related to commit {top.hash}: {top.message} "
                f"(by {top.author}, relevance: {top.relevance_score:.2f})"
            )

        commit_refs = [f"{c.hash}: {c.message}" for c in relevant]

        limitations = [
            "AI explanation unavailable (API error). Showing basic analysis only.",
            "Run with a valid ANTHROPIC_API_KEY for detailed explanations.",
        ]

        return Explanation(
            summary=summary,
            root_cause=root_cause,
            commit_references=commit_refs,
            educational_notes=limitations,
        )
