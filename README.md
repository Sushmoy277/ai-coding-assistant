# AI Coding Assistant

An AI coding assistant for your terminal. Ask it to explain code, fix bugs, or add features: it reads your files, edits them, and runs commands like your tests, with your approval at every step.

Built on the Claude API (`claude-opus-5-5`) with a hand-written agent loop.

> 🚧 Work in progress — demo GIF coming soon.

## Features

- Chat with Claude about your codebase, or run a single request from the command line
- Reads files and folders, creates files, and makes exact search-and-replace edits
- Runs shell commands (tests, linters, git) and reads the output
- Asks before every command and every file change; you can say no
- Every file operation is locked to the project folder; paths that escape it (`../`, symlinks, absolute paths elsewhere) are rejected
- Safety refusals are retried automatically on a fallback model

## How it works

```
 you ──► Agent.ask()
           │
           ▼
   ┌── Claude API (messages + tools) ◄──────────┐
   │       │                                    │
   │  stop_reason == "tool_use"?                │
   │       │ yes                                │
   │       ▼                                    │
   │  Workspace.execute()                       │
   │   ├─ bash          → run command (approved)│
   │   └─ text editor   → view / create /       │
   │                      str_replace / insert  │
   │       │                                    │
   │       └── tool_result ─────────────────────┘
   │
   └─ no ──► final answer
```

- [`agent.py`](src/assistant/agent.py): the loop. Sends the conversation and the two tools to Claude, runs each `tool_use` block, sends all results back in one message, and repeats until Claude is done.
- [`tools.py`](src/assistant/tools.py): runs Claude's built-in `bash` and `str_replace_based_edit_tool` tools locally, with path confinement, approval prompts, timeouts, and output limits.
- [`cli.py`](src/assistant/cli.py): the terminal interface.

## Getting started

Requires Python 3.11+ and an [Anthropic API key](https://console.anthropic.com/).

```bash
git clone https://github.com/Sushmoy277/ai-coding-assistant.git
cd ai-coding-assistant
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # then add your API key
```

## Usage

Start a chat in the current folder:

```bash
ai-assist
```

Point it at another project:

```bash
ai-assist --root ~/code/my-project
```

Run one request and exit:

```bash
ai-assist "Explain what src/assistant/agent.py does"
```

`--effort low|medium|high|xhigh|max` controls how hard Claude thinks before acting (default `high`).

## Running tests

```bash
pytest
```

The tests use a fake Claude client, so they need no API key.

## Safety notes

Commands run through your shell, in the project folder, only after you approve them. Read each one before you say yes, especially anything that deletes files or touches the network.

## Tech stack

- Python 3.11+
- [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python)
- pytest + GitHub Actions CI

## License

MIT
