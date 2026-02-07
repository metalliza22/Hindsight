"""Setup configuration for Hindsight."""

from setuptools import setup, find_packages
from pathlib import Path

here = Path(__file__).parent
long_description = (here / "README.md").read_text(encoding="utf-8")

setup(
    name="hindsight-debugger",
    version="0.1.0",
    description="AI-powered debugging assistant that explains why bugs happen",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Mohammed Zaid",
    author_email="md.zaid22@gmail.com",
    url="https://github.com/metalliza22/Hindsight",
    packages=find_packages(exclude=["tests", "tests.*"]),
    python_requires=">=3.11",
    install_requires=[
        "gitpython>=3.1.40",
        "anthropic>=0.18.0",
        "pyyaml>=6.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "hypothesis>=6.82.0",
            "coverage>=7.3.0",
            "mypy>=1.5.0",
            "black>=23.7.0",
            "flake8>=6.1.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "hindsight=hindsight.cli.interface:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Debuggers",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
