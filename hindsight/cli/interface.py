"""Command-line interface for Hindsight."""

from __future__ import annotations

import argparse
import sys
import time
import threading
from pathlib import Path
from typing import List, Optional

from hindsight import __version__
from hindsight.config import Config, get_api_key, setup_logging
from hindsight.models import AnalysisResult, Explanation


# ANSI color codes
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    DIM = "\033[2m"

    @classmethod
    def disable(cls):
        cls.RESET = ""
        cls.BOLD = ""
        cls.RED = ""
        cls.GREEN = ""
        cls.YELLOW = ""
        cls.BLUE = ""
        cls.MAGENTA = ""
        cls.CYAN = ""
        cls.DIM = ""


class ProgressIndicator:
    """Simple spinner for long-running operations."""

    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stage = ""

    def start(self, stage: str = "Analyzing"):
        self._stage = stage
        self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def update(self, stage: str):
        self._stage = stage

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)
        sys.stderr.write("\r\033[K")
        sys.stderr.flush()

    def _spin(self):
        idx = 0
        while self._running:
            frame = self.FRAMES[idx % len(self.FRAMES)]
            sys.stderr.write(f"\r{Colors.CYAN}{frame}{Colors.RESET} {self._stage}...")
            sys.stderr.flush()
            time.sleep(0.1)
            idx += 1


class HindsightCLI:
    """Main CLI class for the Hindsight debugging assistant."""

    def __init__(self):
        self.config = Config.load()
        self.progress = ProgressIndicator()

    def parse_arguments(self, args: Optional[List[str]] = None) -> argparse.Namespace:
        parser = argparse.ArgumentParser(
            prog="hindsight",
            description="Hindsight - AI-powered debugging assistant that explains why bugs happen",
            epilog=(
                "Examples:\n"
                '  hindsight "TypeError: \'NoneType\' object has no attribute \'name\'"\n'
                "  hindsight --traceback-file error.txt\n"
                "  hindsight --repo /path/to/project \"KeyError: 'user_id'\"\n"
                "  cat traceback.txt | hindsight -\n"
            ),
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )

        parser.add_argument(
            "error",
            nargs="?",
            help='Error message or traceback to analyze. Use "-" to read from stdin.',
        )
        parser.add_argument(
            "--traceback-file", "-f",
            help="Read error/traceback from a file",
        )
        parser.add_argument(
            "--repo", "-r",
            default=".",
            help="Path to the git repository (default: current directory)",
        )
        parser.add_argument(
            "--verbose", "-v",
            action="store_true",
            help="Enable verbose output",
        )
        parser.add_argument(
            "--no-color",
            action="store_true",
            help="Disable colored output",
        )
        parser.add_argument(
            "--max-commits", "-n",
            type=int,
            help=f"Maximum commits to analyze (default: {self.config.analysis.max_commits})",
        )
        parser.add_argument(
            "--no-cache",
            action="store_true",
            help="Disable result caching",
        )
        parser.add_argument(
            "--clear-cache",
            action="store_true",
            help="Clear the analysis cache and exit",
        )
        parser.add_argument(
            "--init",
            action="store_true",
            help="Initialize configuration and exit",
        )
        parser.add_argument(
            "--version",
            action="version",
            version=f"hindsight {__version__}",
        )

        return parser.parse_args(args)

    def run(self, args: Optional[List[str]] = None) -> int:
        """Main entry point. Returns exit code."""
        parsed = self.parse_arguments(args)

        if parsed.no_color:
            Colors.disable()
            self.config.output.color = False

        if parsed.verbose:
            self.config.output.verbose = True

        setup_logging(self.config)

        if parsed.init:
            return self._handle_init()

        if parsed.clear_cache:
            return self._handle_clear_cache()

        # Apply CLI overrides
        if parsed.max_commits:
            self.config.analysis.max_commits = parsed.max_commits
        if parsed.no_cache:
            self.config.cache.enabled = False

        # Get the error message
        error_message = self._get_error_message(parsed)
        if not error_message:
            print(f"{Colors.RED}Error: No error message provided.{Colors.RESET}")
            print(f"Usage: hindsight \"<error message>\" or hindsight -f <traceback_file>")
            return 1

        repo_path = str(Path(parsed.repo).resolve())

        return self._run_analysis(error_message, repo_path)

    def format_output(self, result: AnalysisResult) -> str:
        """Format an analysis result for terminal display."""
        lines: List[str] = []
        C = Colors

        lines.append("")
        lines.append(f"{C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}")
        lines.append(f"{C.BOLD}{C.CYAN}  Hindsight Analysis{C.RESET}")
        lines.append(f"{C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}")
        lines.append("")

        # Error info
        lines.append(f"{C.RED}{C.BOLD}Error:{C.RESET} {result.error_info.error_type}: {result.error_info.message}")
        if result.error_info.affected_files:
            lines.append(f"{C.DIM}Files: {', '.join(result.error_info.affected_files)}{C.RESET}")
        lines.append("")

        if result.explanation:
            exp = result.explanation

            # Summary
            if exp.summary:
                lines.append(f"{C.BOLD}{C.BLUE}Summary{C.RESET}")
                lines.append(f"  {exp.summary}")
                lines.append("")

            # Root Cause
            if exp.root_cause:
                lines.append(f"{C.BOLD}{C.YELLOW}Root Cause{C.RESET}")
                for line in exp.root_cause.splitlines():
                    lines.append(f"  {line}")
                lines.append("")

            # Intent vs Actual
            if exp.intent_vs_actual:
                lines.append(f"{C.BOLD}{C.MAGENTA}Intent vs Reality{C.RESET}")
                for line in exp.intent_vs_actual.splitlines():
                    lines.append(f"  {line}")
                lines.append("")

            # Commit References
            if exp.commit_references:
                lines.append(f"{C.BOLD}{C.CYAN}Relevant Commits{C.RESET}")
                for ref in exp.commit_references[:5]:
                    lines.append(f"  {C.DIM}-{C.RESET} {ref}")
                lines.append("")

            # Fix Suggestions
            if exp.fix_suggestions:
                lines.append(f"{C.BOLD}{C.GREEN}Suggested Fixes{C.RESET}")
                for i, fix in enumerate(exp.fix_suggestions, 1):
                    lines.append(f"  {C.GREEN}{i}.{C.RESET} {fix.description}")
                    if fix.code_example:
                        lines.append(f"     {C.DIM}Code:{C.RESET}")
                        for code_line in fix.code_example.splitlines():
                            lines.append(f"       {code_line}")
                    if fix.rationale:
                        lines.append(f"     {C.DIM}Why: {fix.rationale}{C.RESET}")
                    lines.append("")

            # Educational Notes
            if exp.educational_notes:
                lines.append(f"{C.BOLD}{C.BLUE}Notes{C.RESET}")
                for note in exp.educational_notes:
                    lines.append(f"  {C.DIM}-{C.RESET} {note}")
                lines.append("")

        # Root cause from analysis
        if result.root_cause and result.root_cause.commit:
            rc = result.root_cause
            lines.append(f"{C.BOLD}{C.YELLOW}Most Likely Cause{C.RESET}")
            lines.append(
                f"  Commit {rc.commit.hash} by {rc.commit.author}: {rc.commit.message}"
            )
            lines.append(f"  Confidence: {rc.confidence:.0%}")
            lines.append("")

        # Limitations
        if result.limitations:
            lines.append(f"{C.DIM}Limitations:{C.RESET}")
            for lim in result.limitations:
                lines.append(f"  {C.DIM}- {lim}{C.RESET}")
            lines.append("")

        # Footer
        lines.append(f"{C.DIM}Analysis completed in {result.analysis_time_seconds:.1f}s{C.RESET}")
        lines.append(f"{C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}")
        lines.append("")

        return "\n".join(lines)

    def handle_errors(self, error: Exception) -> str:
        """Format an error for display."""
        return f"{Colors.RED}Error: {type(error).__name__}: {error}{Colors.RESET}"

    # --- Private helpers ---

    def _get_error_message(self, parsed: argparse.Namespace) -> Optional[str]:
        """Get the error message from args, file, or stdin."""
        if parsed.traceback_file:
            try:
                return Path(parsed.traceback_file).read_text()
            except OSError as e:
                print(f"{Colors.RED}Error reading file: {e}{Colors.RESET}")
                return None

        if parsed.error == "-":
            if sys.stdin.isatty():
                print("Reading from stdin (Ctrl+D to finish):")
            return sys.stdin.read()

        return parsed.error

    def _run_analysis(self, error_message: str, repo_path: str) -> int:
        """Run the analysis pipeline with progress indication."""
        from hindsight.analyzer.hindsight_analyzer import HindsightAnalyzer

        analyzer = HindsightAnalyzer(config=self.config)

        self.progress.start("Analyzing error and repository")
        try:
            result = analyzer.analyze_bug(error_message, repo_path)
        except Exception as e:
            self.progress.stop()
            print(self.handle_errors(e))
            return 1
        finally:
            self.progress.stop()

        output = self.format_output(result)
        print(output)
        return 0

    def _handle_init(self) -> int:
        """Initialize configuration."""
        config_path = self.config.config_dir / "config.yaml"
        if config_path.exists():
            print(f"Configuration already exists at {config_path}")
            return 0

        self.config.save()
        print(f"{Colors.GREEN}Configuration created at {config_path}{Colors.RESET}")

        api_key = get_api_key()
        if not api_key:
            print(
                f"\n{Colors.YELLOW}Note:{Colors.RESET} Set your API key:\n"
                f"  export ANTHROPIC_API_KEY=your-key-here\n"
                f"  # or\n"
                f"  export HINDSIGHT_API_KEY=your-key-here"
            )

        return 0

    def _handle_clear_cache(self) -> int:
        """Clear the cache."""
        from hindsight.cache import CacheManager

        cache_dir = self.config.config_dir / "cache"
        if not cache_dir.exists():
            print("No cache to clear.")
            return 0

        cache = CacheManager(cache_dir)
        count = cache.clear()
        print(f"{Colors.GREEN}Cleared {count} cached entries.{Colors.RESET}")
        return 0


def main(args: Optional[List[str]] = None) -> int:
    """Entry point for the CLI."""
    cli = HindsightCLI()
    try:
        return cli.run(args)
    except KeyboardInterrupt:
        print(f"\n{Colors.DIM}Interrupted.{Colors.RESET}")
        return 130
    except Exception as e:
        print(cli.handle_errors(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
