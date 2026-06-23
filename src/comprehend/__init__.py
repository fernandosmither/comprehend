"""comprehend - knowledge-internalization interviewer as Claude.ai connectors + dashboard."""

from __future__ import annotations


def main() -> None:
    from .server import main as _main

    _main()
