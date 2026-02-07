"""Intent extraction from Python source code."""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path
from typing import List, Optional

from hindsight.models import (
    CommentIntent,
    DocstringIntent,
    IntentInfo,
    PatternIntent,
    TestIntent,
)

logger = logging.getLogger(__name__)


class IntentExtractor:
    """Parses code to understand developer intentions through docstrings,
    comments, tests, and code patterns."""

    def extract_from_file(self, file_path: str) -> IntentInfo:
        """Extract all intent signals from a Python source file."""
        path = Path(file_path)
        intent = IntentInfo(file_path=file_path)

        if not path.exists() or not path.is_file():
            logger.warning("File not found: %s", file_path)
            return intent

        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            logger.warning("Could not read file %s: %s", file_path, e)
            return intent

        # Parse AST
        tree = self._parse_ast(source, file_path)
        if tree is not None:
            intent.docstring_intents = self.parse_docstrings(tree)
            intent.pattern_intents = self.infer_from_patterns(tree)

        intent.comment_intents = self.extract_comments(source)

        # Check for associated test file
        if not path.name.startswith("test_"):
            test_path = path.parent / f"test_{path.name}"
            if not test_path.exists():
                # Also check a tests/ subdirectory
                test_path = path.parent / "tests" / f"test_{path.name}"
            if test_path.exists():
                intent.test_intents = self.analyze_test_cases(str(test_path))

        return intent

    def parse_docstrings(self, tree: ast.AST) -> List[DocstringIntent]:
        """Extract intent from function and class docstrings."""
        intents: List[DocstringIntent] = []

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue

            docstring = ast.get_docstring(node)
            if not docstring:
                continue

            params = {}
            return_desc = ""

            # Parse parameter descriptions (supports Google/NumPy/Sphinx styles)
            param_matches = re.findall(
                r"(?::param\s+(\w+):\s*(.+?)(?:\n|$))|"
                r"(?:(\w+)\s*(?:\(.*?\))?\s*:\s*(.+?)(?:\n|$))",
                docstring,
            )
            for match in param_matches:
                name = match[0] or match[2]
                desc = match[1] or match[3]
                if name and desc:
                    params[name.strip()] = desc.strip()

            # Parse return description
            ret_match = re.search(
                r"(?::returns?:\s*(.+?)(?:\n|$))|(?:Returns?:\s*\n\s+(.+?)(?:\n|$))",
                docstring,
            )
            if ret_match:
                return_desc = (ret_match.group(1) or ret_match.group(2) or "").strip()

            # Extract examples
            examples = re.findall(r">>>\s*(.+)", docstring)

            intents.append(
                DocstringIntent(
                    function_name=node.name,
                    intended_behavior=docstring.split("\n")[0].strip(),
                    parameters=params,
                    return_description=return_desc,
                    examples=examples,
                )
            )

        return intents

    def analyze_test_cases(self, test_file_path: str) -> List[TestIntent]:
        """Identify test cases and extract expected functionality descriptions."""
        path = Path(test_file_path)
        intents: List[TestIntent] = []

        if not path.exists():
            return intents

        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return intents

        tree = self._parse_ast(source, test_file_path)
        if tree is None:
            return intents

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_"):
                continue

            docstring = ast.get_docstring(node) or ""
            # Derive expected behavior from test name or docstring
            behavior = docstring.split("\n")[0] if docstring else self._test_name_to_behavior(node.name)

            # Try to infer the function under test
            tested_func = self._infer_tested_function(node)

            intents.append(
                TestIntent(
                    test_name=node.name,
                    expected_behavior=behavior,
                    tested_function=tested_func,
                )
            )

        return intents

    def extract_comments(self, source_code: str) -> List[CommentIntent]:
        """Extract developer comments and categorize them."""
        intents: List[CommentIntent] = []

        for i, line in enumerate(source_code.splitlines(), start=1):
            stripped = line.strip()

            # Skip shebang and encoding lines
            if stripped.startswith("#!") or stripped.startswith("# -*-"):
                continue

            if stripped.startswith("#"):
                text = stripped.lstrip("#").strip()
                if not text:
                    continue

                intent_type = "inline"
                text_lower = text.lower()
                if text_lower.startswith("todo"):
                    intent_type = "todo"
                elif text_lower.startswith("fixme") or text_lower.startswith("fix me"):
                    intent_type = "fixme"
                elif text_lower.startswith("note"):
                    intent_type = "note"
                elif text_lower.startswith("hack") or text_lower.startswith("workaround"):
                    intent_type = "workaround"

                intents.append(
                    CommentIntent(line_number=i, text=text, intent_type=intent_type)
                )

        return intents

    def infer_from_patterns(self, tree: ast.AST) -> List[PatternIntent]:
        """Infer developer intent from code patterns."""
        intents: List[PatternIntent] = []

        for node in ast.walk(tree):
            # Guard clauses (early returns on None/False checks)
            if isinstance(node, ast.If):
                intent = self._check_guard_clause(node)
                if intent:
                    intents.append(intent)

            # Try/except blocks indicate error handling intent
            if isinstance(node, ast.Try):
                intents.append(
                    PatternIntent(
                        pattern_type="error_handling",
                        description="Error handling for expected failure modes",
                        location=f"line {node.lineno}",
                    )
                )

            # Assert statements indicate invariant expectations
            if isinstance(node, ast.Assert):
                intents.append(
                    PatternIntent(
                        pattern_type="assertion",
                        description="Developer asserts invariant condition",
                        location=f"line {node.lineno}",
                    )
                )

            # Type checking patterns
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "isinstance":
                    intents.append(
                        PatternIntent(
                            pattern_type="type_check",
                            description="Runtime type validation",
                            location=f"line {node.lineno}",
                        )
                    )

            # Retry/loop patterns
            if isinstance(node, (ast.For, ast.While)):
                if self._is_retry_pattern(node):
                    intents.append(
                        PatternIntent(
                            pattern_type="retry_logic",
                            description="Retry mechanism for transient failures",
                            location=f"line {node.lineno}",
                        )
                    )

        return intents

    # --- Private helpers ---

    @staticmethod
    def _parse_ast(source: str, file_path: str) -> Optional[ast.AST]:
        try:
            return ast.parse(source, filename=file_path)
        except SyntaxError as e:
            logger.debug("Could not parse %s: %s", file_path, e)
            return None

    @staticmethod
    def _test_name_to_behavior(name: str) -> str:
        """Convert test_function_returns_none -> 'function returns none'."""
        parts = name.replace("test_", "", 1).split("_")
        return " ".join(parts)

    @staticmethod
    def _infer_tested_function(node: ast.FunctionDef) -> str:
        """Try to figure out which function a test is testing."""
        # Common pattern: test_<function_name>_...
        name = node.name
        if name.startswith("test_"):
            remainder = name[5:]
            # Take up to the first verb-like separator
            for sep in ("_returns", "_raises", "_when", "_should", "_with", "_handles"):
                if sep in remainder:
                    return remainder.split(sep)[0]
            return remainder
        return ""

    @staticmethod
    def _check_guard_clause(node: ast.If) -> Optional[PatternIntent]:
        """Check if an if-statement is a guard clause (early return on None/error)."""
        # Pattern: if x is None: return ...
        if (
            isinstance(node.test, ast.Compare)
            and len(node.test.ops) == 1
            and isinstance(node.test.ops[0], ast.Is)
        ):
            if node.body and isinstance(node.body[0], (ast.Return, ast.Raise)):
                return PatternIntent(
                    pattern_type="guard_clause",
                    description="Guard clause checking for None/invalid state",
                    location=f"line {node.lineno}",
                )

        # Pattern: if not x: return ...
        if isinstance(node.test, ast.UnaryOp) and isinstance(node.test.op, ast.Not):
            if node.body and isinstance(node.body[0], (ast.Return, ast.Raise)):
                return PatternIntent(
                    pattern_type="guard_clause",
                    description="Guard clause for falsy value check",
                    location=f"line {node.lineno}",
                )

        return None

    @staticmethod
    def _is_retry_pattern(node) -> bool:
        """Heuristic check for retry-like loop patterns."""
        # Look for loops with try/except and break/sleep
        for child in ast.walk(node):
            if isinstance(child, ast.Try):
                return True
        return False
