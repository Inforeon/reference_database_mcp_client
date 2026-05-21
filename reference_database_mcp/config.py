from __future__ import annotations

import argparse


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="reference-database-mcp",
        description="MCP server wrapper for the reference database REST API.",
    )
    parser.add_argument(
        "--server-url",
        default="http://localhost:8000",
        help="Base URL of the reference database server (default: %(default)s).",
    )
    return parser.parse_args(argv)
