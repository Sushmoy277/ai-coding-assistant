"""The agent loop: send the conversation to Claude, run the tools it asks for, repeat."""

from __future__ import annotations

from typing import Any, Callable

import anthropic

from .tools import Workspace

MODEL = "claude-opus-5-5"
MAX_TOKENS = 16_000
MAX_STEPS = 50  # tool round-trips allowed for one user request

# Anthropic-defined tools: Claude already knows their input format.
TOOLS = [
    {"type": "bash_20250124", "name": "bash"},
    {"type": "text_editor_20250728", "name": "str_replace_based_edit_tool"},
]

# If a request is declined by a safety classifier, the API retries it on a
# fallback model chosen by the refusal category.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

SYSTEM_PROMPT = """You are a coding assistant working in the user's project at {root}.

Use the text editor tool to read and change files, and the bash tool to run
commands such as tests, linters, or git status. Use paths relative to the
project root. Read the relevant code before you change it, keep changes small
and focused, and run the tests when there are any. The user approves every
command and file change, and may decline; if they do, adjust your approach.

When you finish, say briefly what you changed and anything left to do."""


class Agent:
    def __init__(
        self,
        workspace: Workspace,
        client: anthropic.Anthropic | None = None,
        model: str = MODEL,
        effort: str = "high",
        on_text: Callable[[str], None] = print,
        on_tool: Callable[[str, dict], None] | None = None,
    ):
        self.workspace = workspace
        self.client = client or anthropic.Anthropic()
        self.model = model
        self.effort = effort
        self.on_text = on_text
        self.on_tool = on_tool or (lambda name, tool_input: None)
        self.system = SYSTEM_PROMPT.format(root=workspace.root)
        self.messages: list[dict[str, Any]] = []

    def ask(self, prompt: str) -> str:
        """Handle one user request and return Claude's final text."""
        turn_start = len(self.messages)
        self.messages.append({"role": "user", "content": prompt})

        for _ in range(MAX_STEPS):
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=self.system,
                tools=TOOLS,
                messages=self.messages,
                output_config={"effort": self.effort},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )

            if response.stop_reason in ("refusal", "max_tokens"):
                # Drop this unfinished turn so the history stays valid for the next request.
                del self.messages[turn_start:]
                if response.stop_reason == "refusal":
                    return "[Claude declined this request. Try rephrasing it.]"
                return "[The response hit the token limit. Try a smaller request.]"

            # Append the full content (thinking and tool_use blocks included), never just the text.
            self.messages.append({"role": "assistant", "content": response.content})
            text = "\n".join(b.text for b in response.content if b.type == "text").strip()
            if text:
                self.on_text(text)

            tool_calls = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason != "tool_use" or not tool_calls:
                return text

            results = []
            for call in tool_calls:
                self.on_tool(call.name, call.input)
                content, is_error = self.workspace.execute(call.name, call.input)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call.id,
                        "content": content,
                        "is_error": is_error,
                    }
                )
            # All results for one assistant turn go back in a single user message.
            self.messages.append({"role": "user", "content": results})

        return f"[Stopped after {MAX_STEPS} tool steps.]"
