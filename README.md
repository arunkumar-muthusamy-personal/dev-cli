# dev-cli

Interactive AI developer assistant for the terminal.

## Quick Start

```bash
# Install
cd cli
pip install -e ".[dev]"

# Configure your LLM (OpenAI-compatible)
export DEV_CLI_LLM_API_KEY=sk-...          # your API key
export DEV_CLI_LLM_MODEL=gpt-4o            # or claude-3-5-sonnet-20241022, llama3, etc.
export DEV_CLI_LLM_BASE_URL=https://api.openai.com/v1  # default

# Initialize your project
cd /path/to/your/project
dev-cli init

# Chat
dev-cli chat
```

## Supported LLM Providers

| Provider | `DEV_CLI_LLM_BASE_URL` | `DEV_CLI_LLM_MODEL` |
|----------|------------------------|---------------------|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o` |
| Anthropic | `https://api.anthropic.com/v1` | `claude-3-5-sonnet-20241022` |
| Azure OpenAI | `https://<resource>.openai.azure.com/openai/deployments/<deploy>` | `gpt-4o` |
| Ollama (local) | `http://localhost:11434/v1` | `llama3.2`, `mistral`, etc. |
| LM Studio | `http://localhost:1234/v1` | `<loaded model>` |
| Groq | `https://api.groq.com/openai/v1` | `llama-3.1-70b-versatile` |
| Together AI | `https://api.together.xyz/v1` | `meta-llama/Llama-3-70b` |

## Commands

```
dev-cli init       Initialize .dev-cli/ in your project
dev-cli chat       Start interactive AI chat
dev-cli analyze    Analyze project structure
dev-cli context    View/clear conversation history
dev-cli status     Show current config and project info
```

## In-Chat Commands

```
/history    Show conversation history
/clear      Clear conversation
/context    Show project manifest
/analyze    Re-scan project
/exit       Exit
/help       Show help
```

## Configuration

All settings can be overridden via environment variables (prefix: `DEV_CLI_`):

| Env Var | Default | Description |
|---------|---------|-------------|
| `DEV_CLI_LLM_BASE_URL` | `https://api.openai.com/v1` | LLM API base URL |
| `DEV_CLI_LLM_API_KEY` | *(required)* | API key |
| `DEV_CLI_LLM_MODEL` | `gpt-4o` | Model ID |
| `DEV_CLI_LLM_MAX_TOKENS` | `4096` | Max tokens per response |
| `DEV_CLI_LLM_TEMPERATURE` | `0.7` | Sampling temperature |
| `DEV_CLI_HISTORY_LIMIT` | `50` | Messages loaded from history |

## Development

```bash
pip install -e ".[dev]"
pytest
```
