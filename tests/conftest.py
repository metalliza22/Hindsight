"""Shared fixtures for Hindsight tests."""

import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from git import Repo

from hindsight.config import Config
from hindsight.models import (
    BugContext,
    CommitInfo,
    DocstringIntent,
    ErrorInfo,
    Explanation,
    IntentInfo,
    StackFrame,
)


@pytest.fixture
def sample_error_info():
    return ErrorInfo(
        error_type="AttributeError",
        message="'NoneType' object has no attribute 'name'",
        stack_trace=[
            StackFrame(
                file_path="user_service.py",
                line_number=18,
                function_name="display_profile",
                code_context="return f\"Welcome, {user.name}\"",
            ),
        ],
        affected_files=["user_service.py"],
        line_numbers=[18],
        raw_traceback=(
            'Traceback (most recent call last):\n'
            '  File "user_service.py", line 18, in display_profile\n'
            '    return f"Welcome, {user.name}"\n'
            "AttributeError: 'NoneType' object has no attribute 'name'"
        ),
    )


@pytest.fixture
def sample_traceback():
    return (
        'Traceback (most recent call last):\n'
        '  File "app.py", line 42, in main\n'
        '    result = process_data(data)\n'
        '  File "processor.py", line 15, in process_data\n'
        '    return data.transform()\n'
        "AttributeError: 'NoneType' object has no attribute 'transform'"
    )


@pytest.fixture
def sample_commits():
    return [
        CommitInfo(
            hash="abc1234",
            author="dev1",
            timestamp=datetime(2026, 2, 5, 10, 0),
            message="Reduce session timeout to 5 minutes",
            changed_files=["config.py", "user_service.py"],
            diff="- SESSION_TIMEOUT = 30\n+ SESSION_TIMEOUT = 5",
            relevance_score=0.8,
        ),
        CommitInfo(
            hash="def5678",
            author="dev2",
            timestamp=datetime(2026, 2, 4, 14, 30),
            message="Add user profile endpoint",
            changed_files=["user_service.py", "routes.py"],
            diff="+ def display_profile(session_id):\n+     user = get_user(session_id)\n+     return user.name",
            relevance_score=0.5,
        ),
        CommitInfo(
            hash="ghi9012",
            author="dev1",
            timestamp=datetime(2026, 2, 1, 9, 0),
            message="Update README",
            changed_files=["README.md"],
            diff="+ # New section",
            relevance_score=0.0,
        ),
    ]


@pytest.fixture
def sample_intent_info():
    return IntentInfo(
        file_path="user_service.py",
        docstring_intents=[
            DocstringIntent(
                function_name="display_profile",
                intended_behavior="Display user profile information",
                parameters={"session_id": "The active session identifier"},
                return_description="Formatted user profile string",
            ),
        ],
    )


@pytest.fixture
def sample_bug_context(sample_error_info, sample_commits, sample_intent_info):
    return BugContext(
        error_info=sample_error_info,
        relevant_commits=sample_commits,
        intent_info=sample_intent_info,
    )


@pytest.fixture
def default_config():
    return Config()


@pytest.fixture
def tmp_git_repo(tmp_path):
    """Create a temporary git repository with a few commits."""
    repo = Repo.init(tmp_path)

    # Create initial file and commit
    test_file = tmp_path / "app.py"
    test_file.write_text(
        'def greet(name):\n'
        '    """Greet a user by name."""\n'
        '    return f"Hello, {name}"\n'
    )
    repo.index.add(["app.py"])
    repo.index.commit("Initial commit: add greet function")

    # Second commit
    test_file.write_text(
        'def greet(name):\n'
        '    """Greet a user by name."""\n'
        '    if name is None:\n'
        '        raise ValueError("name cannot be None")\n'
        '    return f"Hello, {name}"\n'
    )
    repo.index.add(["app.py"])
    repo.index.commit("Add None check to greet")

    # Third commit: add a second file
    svc_file = tmp_path / "service.py"
    svc_file.write_text(
        'from app import greet\n\n'
        'def serve_user(user):\n'
        '    # TODO: handle missing user\n'
        '    return greet(user.name)\n'
    )
    repo.index.add(["service.py"])
    repo.index.commit("Add service layer")

    return tmp_path


@pytest.fixture
def sample_python_file(tmp_path):
    """Create a sample Python file for intent extraction testing."""
    code = '''\
"""Module for user management."""

# Configuration constants
MAX_RETRIES = 3


def get_user(user_id: int) -> dict:
    """Fetch a user by their ID.

    :param user_id: The unique user identifier
    :returns: User dictionary with name and email

    >>> get_user(1)
    {'name': 'Alice', 'email': 'alice@example.com'}
    """
    if user_id is None:
        return None
    # FIXME: This should use proper database lookup
    return {"name": "Alice", "email": "alice@example.com"}


def validate_email(email: str) -> bool:
    """Check if an email address is valid."""
    assert isinstance(email, str)
    return "@" in email


class UserService:
    """Service for managing users."""

    def __init__(self, db):
        self.db = db

    def create_user(self, name: str, email: str) -> dict:
        """Create a new user account.

        :param name: User's display name
        :param email: User's email address
        :returns: The created user record
        """
        if not name:
            raise ValueError("Name is required")
        try:
            return self.db.insert({"name": name, "email": email})
        except Exception as e:
            # Workaround for flaky DB connection
            for attempt in range(MAX_RETRIES):
                try:
                    return self.db.insert({"name": name, "email": email})
                except Exception:
                    continue
            raise
'''
    filepath = tmp_path / "user_mgmt.py"
    filepath.write_text(code)

    # Also create an associated test file
    test_code = '''\
"""Tests for user management."""

from user_mgmt import get_user, validate_email


def test_get_user_returns_dict():
    """Fetching a valid user should return a dictionary."""
    result = get_user(1)
    assert isinstance(result, dict)


def test_get_user_with_none():
    result = get_user(None)
    assert result is None


def test_validate_email_valid():
    """Valid emails should return True."""
    assert validate_email("test@example.com") is True


def test_validate_email_invalid():
    assert validate_email("not-an-email") is False
'''
    test_filepath = tmp_path / "test_user_mgmt.py"
    test_filepath.write_text(test_code)

    return filepath
