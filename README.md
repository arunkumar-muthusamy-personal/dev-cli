# dev-cli

Interactive AI developer assistant for the terminal — works with any OpenAI-compatible LLM.

## Features

- **Conversational & stateful** — remembers context across turns within a session
- **Project-aware** — auto-detects languages, frameworks, and key files (Python, Node.js, Terraform, SQL)
- **AWS CLI integration** — ask questions about your infrastructure; dev-cli runs the right `aws` commands and feeds the output to the LLM
- **Git integration** — ask about history, diffs, stashes; dev-cli runs `git` commands and includes output in context
- **Shell integration** — run arbitrary shell commands and include their output in the conversation
- **File context** — automatically reads relevant files; manually inject specific files with `/files`
- **Local-first** — all conversation history stored in `.dev-cli/` inside your project

---

## Installation

### Standalone binaries (no Python required)

Download the latest binary for your platform from [GitHub Releases](https://github.com/arunkumar-muthusamy-personal/dev-cli/releases):

| Platform | Binary |
|----------|--------|
| Linux    | `dev-cli-linux` |
| macOS    | `dev-cli-macos` |
| Windows  | `dev-cli-windows.exe` |

**macOS — first run:**
```bash
chmod +x dev-cli-macos
xattr -d com.apple.quarantine dev-cli-macos   # remove Gatekeeper quarantine
./dev-cli-macos --version
```

**Windows:**
```powershell
.\dev-cli-windows.exe --version
```

---

## Quick Start

### 1. Configure your LLM

Create a `.env` file in your project (or export variables in your shell):

```bash
DEV_CLI_LLM_BASE_URL=https://api.openai.com/v1
DEV_CLI_LLM_API_KEY=sk-...
DEV_CLI_LLM_MODEL=gpt-4o
```

> The `.env` file is loaded from your **current working directory** or from the **directory where the binary lives** (useful for standalone installs).

### 2. Initialize your project

```bash
cd /path/to/your/project
dev-cli init
```

### 3. Chat

```bash
dev-cli chat
```

---

## Supported LLM Providers

Any OpenAI-compatible API works. Set `DEV_CLI_LLM_BASE_URL` and `DEV_CLI_LLM_MODEL` accordingly:

| Provider | `DEV_CLI_LLM_BASE_URL` | Example model |
|----------|------------------------|---------------|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o` |
| Anthropic | `https://api.anthropic.com/v1` | `claude-3-5-sonnet-20241022` |
| Azure OpenAI | `https://<resource>.openai.azure.com/openai/deployments/<deploy>` | `gpt-4o` |
| Ollama (local) | `http://localhost:11434/v1` | `llama3.2`, `mistral` |
| LM Studio | `http://localhost:1234/v1` | *(loaded model)* |
| vLLM | `http://localhost:8000/v1` | *(loaded model)* |
| Groq | `https://api.groq.com/openai/v1` | `llama-3.1-70b-versatile` |
| Together AI | `https://api.together.xyz/v1` | `meta-llama/Llama-3-70b` |

**Local LLMs (no API key needed):** set `DEV_CLI_LLM_API_KEY` to any non-empty value, e.g. `ollama`.

**Self-signed certificates (e.g. vLLM dev server):** set `DEV_CLI_LLM_VERIFY_SSL=false`.

---

## Commands

```
dev-cli init       Initialise .dev-cli/ in the current project
dev-cli chat       Start an interactive AI chat session
dev-cli analyze    Analyse and print the project structure
dev-cli context    View or clear conversation history
dev-cli status     Show current config, auth status, and project info
dev-cli --version  Print version
```

### `dev-cli chat` options

| Flag | Description |
|------|-------------|
| `--project-path / -p` | Project directory (default: current directory) |
| `--aws-profile` | AWS profile to use for AWS CLI commands |
| `--no-history` | Start fresh without loading previous conversation |
| `--no-files` | Disable automatic file context injection |
| `--no-hints` | Hide the bottom key-binding toolbar |
| `--limit / -n` | Max messages to load from history (default: 50) |

---

## In-Chat Slash Commands

| Command | Description |
|---------|-------------|
| `/help` | Show available slash commands |
| `/history` | Show conversation history for this session |
| `/clear` | Clear conversation history |
| `/context` | Show the detected project manifest |
| `/analyze` | Re-scan project structure |
| `/run <cmd>` | Run a shell command and include output in context |
| `/git <cmd>` | Run a git command and include output in context |
| `/aws <cmd>` | Run an AWS CLI command and include output in context |
| `/files <paths>` | Read specific files into context (space-separated) |
| `/exit` / `/quit` | Exit the chat session |

### Examples

```
> why is my Lambda timing out?
> /aws logs tail /aws/lambda/my-func --filter-pattern ERROR
> /git log --oneline -20
> /run pytest tests/ -q
> /files src/handler.py src/models.py
> refactor this service to use async/await
> can you create a script to parse this CSV file?
```

---

## Input & Key Bindings

The chat prompt supports multi-line input and tab completion.

| Key | Action |
|-----|--------|
| `Enter` | Send message |
| `Alt+Enter` (Option+Enter on macOS) | Insert newline (for multi-line input) |
| `Tab` | Auto-complete slash commands and file paths |
| `Ctrl+C` | Exit |

**Pasting multi-line text**: paste freely — the entire block lands in the input buffer. Press `Enter` when ready to send.

**Tab completion**: works for slash commands (`/run`, `/files`, etc.) and file paths starting with `./`, `../`, or `~`.

> **macOS note**: To use Option+Enter as a newline, enable "Use Option as Meta key" in your terminal:
> - **Terminal.app**: Preferences → Profiles → Keyboard → ✓ Use Option as Meta key
> - **iTerm2**: Preferences → Profiles → Keys → Left Option key → Esc+

---

## Configuration

All settings use the `DEV_CLI_` prefix and can be set via environment variables or a `.env` file.

| Env Var | Default | Description |
|---------|---------|-------------|
| `DEV_CLI_LLM_BASE_URL` | *(required)* | Base URL of the OpenAI-compatible API |
| `DEV_CLI_LLM_API_KEY` | *(required)* | API key (use any value for local LLMs) |
| `DEV_CLI_LLM_MODEL` | `gpt-4o` | Model ID |
| `DEV_CLI_LLM_MAX_TOKENS` | `4096` | Max tokens per response |
| `DEV_CLI_LLM_TEMPERATURE` | `0.7` | Sampling temperature |
| `DEV_CLI_LLM_VERIFY_SSL` | `true` | Set to `false` to skip SSL verification (self-signed certs) |
| `DEV_CLI_HISTORY_LIMIT` | `50` | Number of messages loaded from history per session |
| `DEV_CLI_SHOW_HINTS` | `true` | Show the bottom key-binding toolbar in chat |
| `DEV_CLI_MANIFEST_TTL_SECONDS` | `3600` | Seconds before re-scanning the project manifest |
| `DEV_CLI_MODE` | `direct` | `direct` calls the LLM API; `proxy` routes through a backend |
| `DEV_CLI_LOG_LEVEL` | `INFO` | Log level |
| `DEV_CLI_VERBOSE` | `false` | Enable verbose output |

Extra variables in your `.env` file (e.g. `DATABASE_URL`, `NODE_ENV`) are silently ignored.

### Example `.env`

```bash
# LLM — OpenAI
DEV_CLI_LLM_BASE_URL=https://api.openai.com/v1
DEV_CLI_LLM_API_KEY=sk-...
DEV_CLI_LLM_MODEL=gpt-4o

# LLM — local Ollama
# DEV_CLI_LLM_BASE_URL=http://localhost:11434/v1
# DEV_CLI_LLM_API_KEY=ollama
# DEV_CLI_LLM_MODEL=llama3.2

# LLM — vLLM with self-signed cert
# DEV_CLI_LLM_BASE_URL=https://my-vllm-server:8000/v1
# DEV_CLI_LLM_API_KEY=token
# DEV_CLI_LLM_MODEL=mistral-7b
# DEV_CLI_LLM_VERIFY_SSL=false
```

---

## Project Storage

dev-cli stores per-project data in `.dev-cli/` inside your project folder:

```
your-project/
└── .dev-cli/
    ├── conversation.db        # SQLite — full conversation history
    └── project_manifest.json  # Detected languages, frameworks, key files
```

Add `.dev-cli/` to your `.gitignore` to avoid committing it.

---

## Development

```bash
git clone https://github.com/arunkumar-muthusamy-personal/dev-cli.git
cd dev-cli
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src/ tests/
```

---

## Version

Current version: **0.2.10**
