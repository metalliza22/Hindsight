"""Unit tests for the Intent Extractor component."""

import ast

import pytest

from hindsight.intent_extractor.parser import IntentExtractor


class TestIntentExtractorFromFile:
    def test_extract_from_valid_file(self, sample_python_file):
        extractor = IntentExtractor()
        intent = extractor.extract_from_file(str(sample_python_file))
        assert intent.file_path == str(sample_python_file)
        assert len(intent.docstring_intents) > 0
        assert len(intent.comment_intents) > 0
        assert len(intent.pattern_intents) > 0

    def test_extract_from_nonexistent_file(self):
        extractor = IntentExtractor()
        intent = extractor.extract_from_file("/nonexistent/file.py")
        assert intent.file_path == "/nonexistent/file.py"
        assert intent.docstring_intents == []
        assert intent.comment_intents == []

    def test_extract_finds_test_intents(self, sample_python_file):
        extractor = IntentExtractor()
        intent = extractor.extract_from_file(str(sample_python_file))
        # Should find the test file and extract test intents
        assert len(intent.test_intents) > 0


class TestDocstringParsing:
    def test_parse_function_docstrings(self, sample_python_file):
        extractor = IntentExtractor()
        source = sample_python_file.read_text()
        tree = ast.parse(source)
        intents = extractor.parse_docstrings(tree)
        func_names = [d.function_name for d in intents]
        assert "get_user" in func_names
        assert "validate_email" in func_names
        assert "UserService" in func_names

    def test_parse_param_descriptions(self, sample_python_file):
        extractor = IntentExtractor()
        source = sample_python_file.read_text()
        tree = ast.parse(source)
        intents = extractor.parse_docstrings(tree)
        get_user_intent = next(d for d in intents if d.function_name == "get_user")
        assert "user_id" in get_user_intent.parameters

    def test_parse_return_description(self, sample_python_file):
        extractor = IntentExtractor()
        source = sample_python_file.read_text()
        tree = ast.parse(source)
        intents = extractor.parse_docstrings(tree)
        get_user_intent = next(d for d in intents if d.function_name == "get_user")
        assert get_user_intent.return_description != ""

    def test_parse_examples(self, sample_python_file):
        extractor = IntentExtractor()
        source = sample_python_file.read_text()
        tree = ast.parse(source)
        intents = extractor.parse_docstrings(tree)
        get_user_intent = next(d for d in intents if d.function_name == "get_user")
        assert len(get_user_intent.examples) > 0

    def test_empty_source(self):
        extractor = IntentExtractor()
        tree = ast.parse("")
        intents = extractor.parse_docstrings(tree)
        assert intents == []


class TestCommentExtraction:
    def test_extract_inline_comments(self):
        extractor = IntentExtractor()
        source = "x = 1\n# This calculates the sum\ny = x + 1\n"
        comments = extractor.extract_comments(source)
        assert len(comments) == 1
        assert comments[0].text == "This calculates the sum"
        assert comments[0].intent_type == "inline"

    def test_extract_todo_comments(self):
        extractor = IntentExtractor()
        source = "# TODO: refactor this\nx = 1\n"
        comments = extractor.extract_comments(source)
        assert len(comments) == 1
        assert comments[0].intent_type == "todo"

    def test_extract_fixme_comments(self):
        extractor = IntentExtractor()
        source = "# FIXME: broken edge case\n"
        comments = extractor.extract_comments(source)
        assert len(comments) == 1
        assert comments[0].intent_type == "fixme"

    def test_skip_shebang_and_encoding(self):
        extractor = IntentExtractor()
        source = "#!/usr/bin/env python\n# -*- coding: utf-8 -*-\n# Real comment\n"
        comments = extractor.extract_comments(source)
        assert len(comments) == 1
        assert comments[0].text == "Real comment"

    def test_skip_empty_comments(self):
        extractor = IntentExtractor()
        source = "#\n# \n# Actual comment\n"
        comments = extractor.extract_comments(source)
        assert len(comments) == 1


class TestTestCaseAnalysis:
    def test_analyze_test_file(self, sample_python_file):
        extractor = IntentExtractor()
        test_path = sample_python_file.parent / f"test_{sample_python_file.name}"
        intents = extractor.analyze_test_cases(str(test_path))
        assert len(intents) == 4
        names = [t.test_name for t in intents]
        assert "test_get_user_returns_dict" in names
        assert "test_validate_email_valid" in names

    def test_analyze_test_extracts_behavior(self, sample_python_file):
        extractor = IntentExtractor()
        test_path = sample_python_file.parent / f"test_{sample_python_file.name}"
        intents = extractor.analyze_test_cases(str(test_path))
        with_docstring = next(t for t in intents if t.test_name == "test_get_user_returns_dict")
        assert "dictionary" in with_docstring.expected_behavior.lower() or "dict" in with_docstring.expected_behavior.lower()

    def test_analyze_nonexistent_test_file(self):
        extractor = IntentExtractor()
        intents = extractor.analyze_test_cases("/nonexistent/test_file.py")
        assert intents == []


class TestPatternInference:
    def test_detect_guard_clause(self):
        extractor = IntentExtractor()
        source = "def foo(x):\n    if x is None:\n        return\n    print(x)\n"
        tree = ast.parse(source)
        patterns = extractor.infer_from_patterns(tree)
        types = [p.pattern_type for p in patterns]
        assert "guard_clause" in types

    def test_detect_error_handling(self):
        extractor = IntentExtractor()
        source = "def foo():\n    try:\n        x = 1\n    except:\n        pass\n"
        tree = ast.parse(source)
        patterns = extractor.infer_from_patterns(tree)
        types = [p.pattern_type for p in patterns]
        assert "error_handling" in types

    def test_detect_assertion(self):
        extractor = IntentExtractor()
        source = "def foo(x):\n    assert x > 0\n    return x\n"
        tree = ast.parse(source)
        patterns = extractor.infer_from_patterns(tree)
        types = [p.pattern_type for p in patterns]
        assert "assertion" in types

    def test_detect_type_check(self):
        extractor = IntentExtractor()
        source = "def foo(x):\n    if isinstance(x, int):\n        return x\n"
        tree = ast.parse(source)
        patterns = extractor.infer_from_patterns(tree)
        types = [p.pattern_type for p in patterns]
        assert "type_check" in types

    def test_detect_retry_pattern(self, sample_python_file):
        extractor = IntentExtractor()
        source = sample_python_file.read_text()
        tree = ast.parse(source)
        patterns = extractor.infer_from_patterns(tree)
        types = [p.pattern_type for p in patterns]
        assert "retry_logic" in types
