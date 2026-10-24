"""Command-line interface for Kawach GitHub Fix Pipeline."""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from pydantic import SecretStr

from kawach_fix.graph import run_fix_pipeline
from kawach_fix.redact import RedactingLoggingFilter
from kawach_fix.schemas import FixRequest


def setup_cli_logging():
    """Install redacting logging filter onto standard logging handlers."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("[%(levelname)s] %(asctime)s - %(name)s: %(message)s")
    )
    handler.addFilter(RedactingLoggingFilter())

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers = [handler]


def main():
    """CLI entrypoint."""
    setup_cli_logging()

    parser = argparse.ArgumentParser(
        prog="kawach-fix",
        description="Autonomous GitHub Fix Pipeline for Playwright test failures.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    run_parser = subparsers.add_parser("run", help="Run fix pipeline on a JSON request file.")
    run_parser.add_argument("request_file", type=str, help="Path to JSON file containing FixRequest.")
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform all verification and fix synthesis steps without pushing to GitHub.",
    )
    run_parser.add_argument(
        "--pat",
        type=str,
        default=None,
        help="GitHub Personal Access Token (defaults to GITHUB_PAT env var or request JSON).",
    )

    args = parser.parse_args()

    if args.subcommand == "run":
        req_path = Path(args.request_file).resolve()
        if not req_path.is_file():
            sys.stderr.write(f"Error: request file '{req_path}' does not exist.\n")
            sys.exit(2)

        try:
            req_data = json.loads(req_path.read_text(encoding="utf-8"))
        except Exception as e:
            sys.stderr.write(f"Error: failed to parse JSON in '{req_path}': {e}\n")
            sys.exit(2)

        # Allow PAT injection via flag or GITHUB_PAT env var if missing
        if args.pat:
            req_data["github_pat"] = args.pat
        elif "github_pat" not in req_data and "GITHUB_PAT" in os.environ:
            req_data["github_pat"] = os.environ["GITHUB_PAT"]

        if args.dry_run:
            opts = req_data.setdefault("options", {})
            opts["dry_run"] = True

        try:
            request = FixRequest.model_validate(req_data)
        except Exception as e:
            sys.stderr.write(f"Error: invalid FixRequest payload: {e}\n")
            sys.exit(2)

        # Run pipeline
        result = run_fix_pipeline(request)
        print(result.model_dump_json(indent=2))

        # Exit code mapping
        if result.status in ("pr_opened", "pr_exists", "dry_run_ready"):
            sys.exit(0)
        else:
            sys.exit(1)


if __name__ == "__main__":
    main()
