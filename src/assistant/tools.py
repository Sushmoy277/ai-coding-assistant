"""Local execution of Claude's bash and text-editor tools.

Every operation is confined to a single project root, and anything that
changes files or runs a command needs the user's approval first.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable
from urllib.parse import unquote

# Called with a description of the action; returns True if the user allows it.
Approver = Callable[[str], bool]

MAX_OUTPUT_CHARS = 20_000
SKIP_DIRS = {".git", "venv", ".venv", "node_modules", "__pycache__", ".pytest_cache"}


class ToolError(Exception):
    """A tool call failed; the message is sent back to Claude as an error result."""


def _truncate(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return text[:MAX_OUTPUT_CHARS] + f"\n... [truncated, {len(text) - MAX_OUTPUT_CHARS} more chars]"


class Workspace:
    """Runs tool calls inside one project directory."""

    def __init__(self, root: str | Path, approve: Approver, bash_timeout: int = 60):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise ValueError(f"Project root is not a directory: {self.root}")
        self.approve = approve
        self.bash_timeout = bash_timeout

    # ------------------------------------------------------------------ paths

    def resolve(self, raw_path: str) -> Path:
        """Turn a model-supplied path into a real path inside the project root."""
        if not raw_path:
            raise ToolError("A path is required.")
        if unquote(raw_path) != raw_path:
            raise ToolError("URL-encoded paths are not allowed.")
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = self.root / candidate
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self.root):
            raise ToolError(f"Path is outside the project root: {raw_path}")
        return resolved

    def _rel(self, path: Path) -> str:
        return str(path.relative_to(self.root)) or "."

    # --------------------------------------------------------------- dispatch

    def execute(self, name: str, tool_input: dict) -> tuple[str, bool]:
        """Run one tool call. Returns (content, is_error)."""
        try:
            if name == "bash":
                return self.bash(tool_input), False
            if name == "str_replace_based_edit_tool":
                return self.text_editor(tool_input), False
            raise ToolError(f"Unknown tool: {name}")
        except ToolError as e:
            return str(e), True
        except OSError as e:
            return f"{type(e).__name__}: {e}", True

    # ------------------------------------------------------------------- bash

    def bash(self, tool_input: dict) -> str:
        if tool_input.get("restart"):
            # Each command runs in a fresh subprocess, so there is no state to reset.
            return "Shell restarted."
        command = tool_input.get("command")
        if not command:
            raise ToolError("No command given.")
        if not self.approve(f"Run command: {command}"):
            raise ToolError("The user declined to run this command.")
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=self.bash_timeout,
            )
        except subprocess.TimeoutExpired:
            raise ToolError(f"Command timed out after {self.bash_timeout}s.")
        output = proc.stdout + proc.stderr
        if proc.returncode != 0:
            output += f"\n[exit code {proc.returncode}]"
        return _truncate(output) or "(no output)"

    # ------------------------------------------------------------ text editor

    def text_editor(self, tool_input: dict) -> str:
        command = tool_input.get("command")
        path = self.resolve(tool_input.get("path", ""))
        if command == "view":
            return self._view(path, tool_input.get("view_range"))
        if command == "create":
            return self._create(path, tool_input.get("file_text", ""))
        if command == "str_replace":
            return self._str_replace(path, tool_input.get("old_str", ""), tool_input.get("new_str", ""))
        if command == "insert":
            return self._insert(path, tool_input.get("insert_line"), tool_input.get("insert_text", ""))
        raise ToolError(f"Unknown editor command: {command}")

    def _view(self, path: Path, view_range: list[int] | None) -> str:
        if path.is_dir():
            return self._list_dir(path)
        if not path.is_file():
            raise ToolError(f"File not found: {self._rel(path)}")
        lines = path.read_text(errors="replace").splitlines()
        start, end = 1, len(lines)
        if view_range:
            start, end = view_range[0], view_range[1]
            if end == -1:
                end = len(lines)
            if start < 1 or start > max(end, 1) or end > len(lines):
                raise ToolError(f"Invalid view_range {view_range} for a {len(lines)}-line file.")
        numbered = [f"{n:6}\t{lines[n - 1]}" for n in range(start, end + 1)]
        return _truncate("\n".join(numbered)) or "(empty file)"

    def _list_dir(self, path: Path, max_depth: int = 2) -> str:
        entries: list[str] = []

        def walk(directory: Path, depth: int) -> None:
            for child in sorted(directory.iterdir()):
                if child.name in SKIP_DIRS or child.name.startswith("."):
                    continue
                entries.append(self._rel(child) + ("/" if child.is_dir() else ""))
                if child.is_dir() and depth < max_depth:
                    walk(child, depth + 1)

        walk(path, 1)
        return _truncate("\n".join(entries)) or "(empty directory)"

    def _create(self, path: Path, file_text: str) -> str:
        action = "Overwrite" if path.exists() else "Create"
        if not self.approve(f"{action} file {self._rel(path)} ({len(file_text.splitlines())} lines)"):
            raise ToolError("The user declined this file change.")
        if path.exists():
            path.with_name(path.name + ".bak").write_text(path.read_text())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(file_text)
        return f"{action}d {self._rel(path)}."

    def _str_replace(self, path: Path, old_str: str, new_str: str) -> str:
        if not path.is_file():
            raise ToolError(f"File not found: {self._rel(path)}")
        if not old_str:
            raise ToolError("old_str must not be empty.")
        text = path.read_text()
        count = text.count(old_str)
        if count == 0:
            raise ToolError("old_str was not found in the file.")
        if count > 1:
            raise ToolError(f"old_str matches {count} places; add more context so it matches once.")
        if not self.approve(f"Edit {self._rel(path)}:\n--- old\n{old_str}\n+++ new\n{new_str}"):
            raise ToolError("The user declined this file change.")
        path.write_text(text.replace(old_str, new_str, 1))
        return f"Edited {self._rel(path)}."

    def _insert(self, path: Path, insert_line: int | None, insert_text: str) -> str:
        if not path.is_file():
            raise ToolError(f"File not found: {self._rel(path)}")
        lines = path.read_text().splitlines(keepends=True)
        if not isinstance(insert_line, int) or not 0 <= insert_line <= len(lines):
            raise ToolError(f"insert_line must be between 0 and {len(lines)}.")
        if not self.approve(f"Insert into {self._rel(path)} after line {insert_line}:\n{insert_text}"):
            raise ToolError("The user declined this file change.")
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        new_text = insert_text if insert_text.endswith("\n") else insert_text + "\n"
        lines.insert(insert_line, new_text)
        path.write_text("".join(lines))
        return f"Inserted text into {self._rel(path)} after line {insert_line}."
