# AI Coding Assistant

An AI-powered coding assistant that can read, explain, and edit code from your terminal.

> 🚧 Work in progress — demo GIF coming soon.

## Features (planned)

- [ ] Chat with an LLM about your codebase
- [ ] Read and explain files
- [ ] Suggest and apply code edits
- [ ] Run commands and tests via tool use

## Tech stack

- Python 3.11+
- Anthropic Claude API
- pytest + GitHub Actions CI

## Getting started

```bash
git clone https://github.com/Sushmoy277/ai-coding-assistant.git
cd ai-coding-assistant
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then add your API key
```

## Project structure

```
src/assistant/   core agent loop and tools
tests/           unit tests
examples/        usage examples
```

## License

MIT
