"""Command-line interface: `ai-assist` or `python -m assistant`."""

from __future__ import annotations

import argparse
import sys

import anthropic
from dotenv import load_dotenv

from .agent import Agent
from .tools import Workspace


def confirm(description: str) -> bool:
    print(f"\n\033[33m? {description}\033[0m")
    try:
        return input("  Allow? [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def show_tool(name: str, tool_input: dict) -> None:
    if name == "bash":
        detail = tool_input.get("command", "restart")
    else:
        detail = f"{tool_input.get('command')} {tool_input.get('path', '')}"
    print(f"\033[2m  → {name}: {detail}\033[0m")


def show_text(text: str) -> None:
    print(f"\n\033[36massistant>\033[0m {text}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI coding assistant powered by Claude.")
    parser.add_argument("prompt", nargs="?", help="Run one request and exit instead of starting a chat.")
    parser.add_argument("--root", default=".", help="Project folder the assistant may work in (default: current folder).")
    parser.add_argument(
        "--effort",
        default="high",
        choices=["low", "medium", "high", "xhigh", "max"],
        help="How hard Claude thinks before acting (default: high).",
    )
    args = parser.parse_args(argv)

    load_dotenv()
    workspace = Workspace(args.root, approve=confirm)
    agent = Agent(workspace, effort=args.effort, on_text=show_text, on_tool=show_tool)

    def run(prompt: str) -> None:
        try:
            agent.ask(prompt)
        except anthropic.AuthenticationError:
            sys.exit("Authentication failed. Set ANTHROPIC_API_KEY in your .env file.")
        except anthropic.APIConnectionError:
            print("Network error: could not reach the Claude API.")
        except anthropic.APIStatusError as e:
            print(f"API error ({e.status_code}): {e.message}")

    if args.prompt:
        run(args.prompt)
        return 0

    print(f"AI Coding Assistant — working in {workspace.root}")
    print("Type a request, or 'exit' to quit.")
    while True:
        try:
            prompt = input("\n\033[32myou>\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if prompt.lower() in ("exit", "quit"):
            return 0
        if prompt:
            run(prompt)


if __name__ == "__main__":
    sys.exit(main())
