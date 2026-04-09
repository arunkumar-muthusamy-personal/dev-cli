# Dev-CLI: Interactive Project Assistant Specification

**Status:** Specification (Pre-Development)  
**Version:** 1.0  
**Last Updated:** March 20, 2026

-----

## Table of Contents

1. [Executive Summary](#executive-summary)
1. [Vision & Goals](#vision--goals)
1. [Architecture Overview](#architecture-overview)
1. [Technology Stack](#technology-stack)
1. [Project Structure](#project-structure)
1. [Requirements](#requirements)
1. [CLI Design & Commands](#cli-design--commands)
1. [VS Code Extension Design](#vs-code-extension-design)
1. [Context Management](#context-management)
1. [Authentication & Authorization](#authentication--authorization)
1. [Backend API Specification](#backend-api-specification)
1. [Rate Limiting & Quotas](#rate-limiting--quotas)
1. [Multi-Language Support](#multi-language-support)
1. [Bedrock Integration](#bedrock-integration)
1. [Build, Test & Deployment](#build-test--deployment)
1. [Security & Privacy](#security--privacy)
1. [Development Roadmap](#development-roadmap)
1. [Future Enhancements](#future-enhancements)

-----

## Executive Summary

**Dev-CLI** is an interactive developer productivity tool that brings conversational AI assistance directly into your project workflow. Inspired by Kiro-CLI, it integrates with AWS Bedrock (Claude models) to provide intelligent code analysis, refactoring suggestions, debugging help, and dependency mapping across polyglot projects.

### Key Features

- **Interactive CLI & VS Code Chat Interface** – Native terminal experience + VS Code webview
- **Conversational & Stateful** – Remembers project context across conversation turns
- **Multi-Language Support** – Python, Node.js, Angular, Terraform, SQL, PySpark, NoSQL, Vector DBs
- **Local-First Architecture** – All conversation history and context stored in `.dev-cli/` folder
- **Okta SSO Integration** – AWS SSO-like auth flow (local token validation, no backend session store)
- **Production-Grade** – Rate limiting, 24h session expiry, audit logs, GDPR-compliant

### Target Users

- Solo developers and small/medium teams
- Polyglot projects (multiple languages/frameworks)
- Developers preferring terminal or VS Code UI
- Organizations using Okta as IDP

### Success Metrics

- CLI installation: >1k users (PyPI downloads)
- VS Code extension: >500 active users
- Average session length: >15 minutes
- User satisfaction: NPS >50
- API uptime: 99.9%
- P95 latency: <5 seconds

-----

## Vision & Goals

### Primary Goals

1. **Developer Productivity** – Answer “understand,” “debug,” “refactor,” “optimize” questions in seconds
1. **Project Context Awareness** – Understand project structure, dependencies, and architecture automatically
1. **Conversational UX** – Feel like pair-programming with an AI, with full context history
1. **Privacy by Default** – No project code leaves the user’s machine unless explicitly sent to Bedrock
1. **Easy Distribution** – One-command installation (pip), optional VS Code extension for GUI users

### Non-Goals

- Web-based dashboard (for now) – focus on CLI and VS Code
- Team collaboration features – single-user focus (v1.0)
- Offline LLM inference – rely on Bedrock (can add local models later)
- IDE plugins beyond VS Code – scope to VS Code initially

-----

## Architecture Overview

### System Diagram (Revised: Backend Proxy via Private API Gateway + VPC Endpoint)

```
┌──────────────────────────────────────────────────────────────────┐
│                     Developer's Laptop (VPN)                      │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│ ┌────────────────────────────────────────────────────────────┐  │
│ │  CLI / VS Code Extension                                  │  │
│ │  ├─ ~/.dev-cli/config (system-level: JWT token)          │  │
│ │  ├─ project/.dev-cli/conversation.db (project-level)     │  │
│ │  ├─ project/.dev-cli/project_manifest.json               │  │
│ │  ├─ Okta JWT Validation (Local JWK)                       │  │
│ │  └─ AWS CLI Execution (subprocess, user's profile)        │  │
│ └────────────────────────────────────────────────────────────┘  │
│                          │                                       │
│                          ▼                                       │
│                   POST /api/v1/chat                              │
│          (Via VPN → Private API Gateway)                        │
│                                                                  │
└──────────────────────────┬───────────────────────────────────────┘
                           │
        ┌──────────────────┴──────────────────┐
        │    (Over VPN - Private Network)     │
        │                                     │
        ▼                                     ▼
    ┌───────────────────────────────────────────────────┐
    │         Corporate VPC (Private Network)           │
    ├───────────────────────────────────────────────────┤
    │                                                   │
    │  ┌─────────────────────────────────────────────┐ │
    │  │ Private API Gateway                         │ │
    │  │ - VPC Endpoint (private PrivateLink)        │ │
    │  │ - No public internet access                 │ │
    │  │ - Only accessible from VPN                  │ │
    │  └────────────┬────────────────────────────────┘ │
    │               │                                   │
    │               ▼                                   │
    │  ┌─────────────────────────────────────────────┐ │
    │  │ Lambda (Backend API)                        │ │
    │  │ ├─ Validate JWT + Okta group               │ │
    │  │ ├─ Check rate limits (DynamoDB)            │ │
    │  │ ├─ Route to LLM Provider                   │ │
    │  │ └─ Log to CloudWatch                       │ │
    │  └────────────┬────────────────────────────────┘ │
    │               │                                   │
    │     ┌─────────┴─────────┐                        │
    │     │                   │                        │
    │     ▼                   ▼                        │
    │  ┌──────────┐      ┌──────────┐                 │
    │  │ Bedrock  │      │ OpenAI   │ (future)        │
    │  │ Provider │      │ Provider │                 │
    │  │ (Day 1)  │      │ (Fallback)                │
    │  └──────────┘      └──────────┘                 │
    │                                                   │
    └───────────────────────────────────────────────────┘
         │                              │
         │ (AWS API)                    │ (HTTPS)
         │                              │
         ▼                              ▼
    AWS Bedrock               OpenAI API (Optional)
    (boto3)                   (future provider)

    ┌────────────────────────────────────────────────┐
    │  Shared Services (Inside VPC)                  │
    ├────────────────────────────────────────────────┤
    │                                                │
    │  DynamoDB Table: dev-cli-rate-limits           │
    │  ├─ user_id#{date}                             │
    │  ├─ tokens_used, cost_usd, credits_remaining   │
    │  └─ daily_limit (configurable per user)        │
    │                                                │
    │  CloudWatch Logs                               │
    │  ├─ All API calls (audit trail)                │
    │  ├─ AWS CLI executions                         │
    │  ├─ LLM provider calls                         │
    │  └─ Retention: 90 days                         │
    │                                                │
    └────────────────────────────────────────────────┘
```

**Key Architecture Decisions:**

- ✅ **Backend Proxy Pattern** – CLI → Private API Gateway → Lambda → LLM Provider
- ✅ **Private API Gateway + VPC Endpoint** – All traffic stays within corporate VPN/VPC
- ✅ **LLM Provider Abstraction** – Day 1 support for Bedrock, extensible for OpenAI/others
- ✅ **No User IAM Requirements** – Only backend Lambda needs LLM permissions
- ✅ **Centralized Rate Limiting** – Backend controls quota + costs per user
- ✅ **AWS CLI execution** – CLI runs AWS CLI with user’s profile (separate from Bedrock)
- ✅ **System-level auth** – Single JWT token in ~/.dev-cli/config (reused across all projects)
- ✅ **Project-level storage** – Each project has its own .dev-cli/conversation.db

### Data Flow (Revised: Backend Proxy via Private API Gateway)

```
User: dev-cli chat --aws-profile prod
         ↓
1. Load system-level token from ~/.dev-cli/config
         ↓
   Token exists & valid? 
   ├─ No → Initiate Okta SSO (see auth flow)
   └─ Yes → Continue
         ↓
2. Load AWS Profile (auto-detect or explicit)
         ↓
3. Initialize project context:
   ├─ Load .dev-cli/conversation.db (conversation history)
   ├─ Load .dev-cli/project_manifest.json (languages, frameworks)
   └─ Scan project files (intelligent reader)
         ↓
4. Enter chat loop:
   User: "Check CloudWatch logs for lambda errors"
         ↓
5. AWS CLI Execution (if needed):
   ├─ Detect AWS command request in user message
   ├─ Parse: "CloudWatch logs" → aws logs tail /aws/lambda/...
   ├─ Ask user: "Run: aws logs tail /aws/lambda/my-func --profile prod? (y/n)"
   ├─ If modify/delete command: "⚠️  This command will MODIFY resources. Confirm? (y/n)"
   ├─ Execute: subprocess("aws logs tail ... --profile prod")
   ├─ Capture stdout + stderr
   └─ Add to request body
         ↓
6. Intelligent File Reading:
   ├─ Based on user question, identify relevant files
   ├─ Example: "lambda errors" → include lambda handler, error logs, config
   ├─ Read files respecting size limits (10MB per file, 50MB total)
   └─ Add file content to request body
         ↓
7. Build Request to Backend API:
   {
     "message": "Check CloudWatch logs for lambda errors",
     "aws_cli_output": "[error logs from step 5]",
     "file_contents": { "handler.py": "...", "config.yaml": "..." },
     "project_manifest": { "languages": [...], "frameworks": [...] },
     "conversation_history": [previous messages]
   }
         ↓
8. POST /api/v1/chat (over VPN → Private API Gateway)
   ├─ Header: Authorization: Bearer <JWT>
   ├─ Endpoint: https://api.internal.company.com/api/v1/chat
   │           (via VPC Endpoint, no public internet)
   └─ Body: [request from step 7]
         ↓
9. Backend Lambda Processing:
   ├─ Validate JWT signature (local JWK validation)
   ├─ Extract user_id from JWT
   ├─ Check Okta group: "dev-cli-users" ✓
   ├─ Check rate limits (DynamoDB: user_id#{date})
   │  └─ Has user exceeded daily quota?
   ├─ Build system prompt (language-specific)
   ├─ Select LLM provider (factory pattern):
   │  ├─ Get provider from config (bedrock | openai | ...)
   │  ├─ Instantiate provider (BedrockProvider, OpenAIProvider, etc.)
   │  └─ Call: provider.invoke(system_prompt, messages, ...)
   ├─ Stream response back to CLI
   └─ Log to CloudWatch (audit trail)
         ↓
10. Backend calls LLM Provider (Abstracted):
    Provider.invoke(
      system_prompt="You are an expert...",
      messages=[...context + user message...],
      max_tokens=2048,
      temperature=0.7,
      stream=True
    )
         ↓
11. LLM Provider (Day 1: Bedrock):
    ├─ Backend's Lambda has boto3 Bedrock permissions
    ├─ bedrock.invoke_model(modelId="claude-3-sonnet-...", ...)
    ├─ Stream response tokens back
    └─ Provider returns AsyncIterator[str]
         ↓
12. Backend streams response to CLI:
    ├─ Content-Type: text/event-stream
    ├─ data: {"type": "token", "content": "I'll"}
    ├─ data: {"type": "token", "content": " help"}
    ├─ data: {"type": "usage", "tokens": 450}
    └─ data: {"type": "done"}
         ↓
13. CLI receives streamed response:
    ├─ Display response with syntax highlighting
    ├─ Store in .dev-cli/conversation.db
    ├─ Track tokens used
    └─ Display in real-time
         ↓
14. Backend updates cost tracking (DynamoDB):
    ├─ tokens_used += (input + output tokens)
    ├─ cost_usd += calculate_cost(tokens)
    ├─ credits_remaining -= cost_usd
    ├─ Check if user exceeded daily limit
    └─ TTL: 32 days
         ↓
15. Backend logs to CloudWatch:
    {
      "timestamp": "2025-03-20T14:30:00Z",
      "user_id": "okta_user_123",
      "email": "john@company.com",
      "model": "claude-3-sonnet",
      "provider": "bedrock",
      "input_tokens": 450,
      "output_tokens": 200,
      "total_tokens": 650,
      "cost_usd": 0.00195,
      "execution_time_ms": 1245,
      "aws_commands": ["logs tail"],
      "files_included": 2,
      "status": "success"
    }
         ↓
16. Complete:
    ✓ Response displayed in CLI
    ✓ Conversation saved locally (.dev-cli/conversation.db)
    ✓ Cost tracked (DynamoDB)
    ✓ Audit logged (CloudWatch)
    ✓ Quota updated (DynamoDB: user_id#{date})
```

### Key Architectural Principles

1. **Thick Client** – CLI and VS Code Extension own their data (`.dev-cli/` folder)
1. **Local-First Auth** – Token validation happens locally using cached Okta JWK keys
1. **Stateless Backend** – No session store; every request is validated via JWT signature
1. **Modular Language Support** – Pluggable language detectors and prompt handlers
1. **Streaming Responses** – Stream Bedrock output directly to user for fast feedback

-----

## Technology Stack

### Frontend (CLI)

|Component        |Technology     |Notes                           |
|-----------------|---------------|--------------------------------|
|**Language**     |Python 3.11+   |Cross-platform, DevOps-friendly |
|**CLI Framework**|Typer + Click  |Modern async CLI library        |
|**Local Storage**|SQLite         |Zero-dependency, file-based     |
|**HTTP Client**  |httpx + asyncio|Async HTTP, streaming support   |
|**Auth**         |authlib + OIDC |OAuth2 PKCE flow, JWK validation|
|**Config**       |pydantic       |Settings validation, env vars   |
|**Crypto**       |cryptography   |Token encryption at rest        |

### Frontend (VS Code Extension)

|Component      |Technology  |Notes                       |
|---------------|------------|----------------------------|
|**Language**   |TypeScript 5|Type-safe, VS Code native   |
|**Framework**  |React 18    |Webview UI                  |
|**Styling**    |Tailwind CSS|Utility-first, lightweight  |
|**HTTP Client**|axios       |Promise-based, simple       |
|**State**      |Zustand     |Lightweight state management|

### Backend

|Component        |Technology                |Notes                           |
|-----------------|--------------------------|--------------------------------|
|**Language**     |Python 3.11+              |Same as CLI, shared libraries   |
|**Framework**    |FastAPI                   |Async, automatic docs, streaming|
|**LLM**          |AWS Bedrock               |Claude 3 Sonnet/Opus models     |
|**Auth**         |python-jose + cryptography|JWT validation, JWK caching     |
|**Rate Limiting**|DynamoDB                  |Distributed rate limit tracking |
|**Logging**      |structlog                 |Structured, audit-trail ready   |
|**Testing**      |pytest                    |Fixtures, async support         |

### Infrastructure

|Component           |Technology         |Notes                              |
|--------------------|-------------------|-----------------------------------|
|**Compute**         |ECS Fargate        |Serverless containers, auto-scaling|
|**API Gateway**     |AWS API Gateway    |JWT validation (optional), routing |
|**Auth Provider**   |Okta               |Organizational SSO                 |
|**Rate Limit Store**|DynamoDB           |Distributed key-value              |
|**Secrets**         |AWS Secrets Manager|API keys, Bedrock credentials      |
|**Logging**         |CloudWatch         |Centralized logs, dashboards       |
|**IaC**             |Terraform          |Infrastructure as code             |
|**CI/CD**           |GitHub Actions     |Build, test, publish workflow      |

### Distribution

|Target        |Format             |Distribution              |
|--------------|-------------------|--------------------------|
|**Python CLI**|Wheel              |PyPI (pip install dev-cli)|
|**Docker**    |Image              |Docker Hub, ECR           |
|**VS Code**   |Extension          |VS Code Marketplace       |
|**Binaries**  |Linux/macOS/Windows|GitHub Releases           |

-----

## Project Structure

### Monorepo Layout

```
dev-cli/                              # Root (monorepo)
│
├── .github/
│   └── workflows/
│       ├── test.yml                  # Run tests on push
│       ├── publish-cli.yml           # Publish to PyPI + GitHub Releases
│       └── publish-extension.yml     # Publish to VS Code Marketplace
│
├── cli/                              # Python CLI package (main product)
│   ├── pyproject.toml                # Poetry configuration
│   ├── setup.py                      # Legacy setup (if needed)
│   ├── src/dev_cli/
│   │   ├── __main__.py               # Entry point
│   │   ├── main.py                   # CLI app (Typer)
│   │   ├── config.py                 # Settings (pydantic)
│   │   ├── version.py                # Version info
│   │   │
│   │   ├── commands/                 # CLI commands
│   │   │   ├── __init__.py
│   │   │   ├── chat.py               # Interactive chat loop
│   │   │   ├── analyze.py            # Analyze project structure
│   │   │   ├── init.py               # Initialize .dev-cli/ folder
│   │   │   ├── config.py             # Config management (auth, settings)
│   │   │   ├── context.py            # Manage conversation history
│   │   │   ├── logout.py             # Clear token
│   │   │   └── login.py              # Trigger Okta SSO
│   │   │
│   │   ├── auth/                     # Authentication
│   │   │   ├── __init__.py
│   │   │   ├── okta.py               # Okta OIDC flow (PKCE)
│   │   │   ├── token_store.py        # Secure token storage (~/.dev-cli/)
│   │   │   ├── jwt_validator.py      # Local JWT validation + JWK caching
│   │   │   └── callback_handler.py   # Local HTTP callback server
│   │   │
│   │   ├── storage/                  # Local context storage (.dev-cli/)
│   │   │   ├── __init__.py
│   │   │   ├── conversation.py       # SQLite conversation DB
│   │   │   ├── manifest.py           # Project manifest reader
│   │   │   ├── models.py             # Pydantic data models
│   │   │   └── schema.py             # SQLite schema definitions
│   │   │
│   │   ├── aws_cli/                 # AWS CLI integration
│   │   │   ├── __init__.py
│   │   │   ├── manager.py           # AWS CLI execution manager
│   │   │   ├── profile_detector.py  # Auto-detect AWS profiles
│   │   │   ├── command_parser.py    # Parse user intent → AWS command
│   │   │   ├── command_classifier.py # Classify: read|modify|delete
│   │   │   └── cache.py             # Cache AWS CLI results (30s TTL)
│   │   │
│   │   ├── bedrock/                 # Direct Bedrock integration (no backend)
│   │   │   ├── __init__.py
│   │   │   ├── direct_client.py     # Direct boto3 Bedrock client
│   │   │   ├── prompt_builder.py    # Build system + user prompts
│   │   │   └── streaming.py         # Stream response handler
│   │   │
│   │   │   ├── __init__.py
│   │   │   ├── detector.py           # Main detector (orchestrator)
│   │   │   ├── python.py             # Python framework detector
│   │   │   ├── nodejs.py             # Node.js/TypeScript detector
│   │   │   ├── terraform.py          # Terraform/IaC detector
│   │   │   ├── sql.py                # SQL/database detector
│   │   │   └── utils.py              # File scanning utilities
│   │   │
│   │   ├── api_client/               # Backend API communication
│   │   │   ├── __init__.py
│   │   │   ├── client.py             # HTTP client wrapper
│   │   │   ├── models.py             # Request/response models
│   │   │   └── streaming.py          # Stream response handler
│   │   │
│   │   ├── utils/
│   │   │   ├── __init__.py
│   │   │   ├── logging.py            # Structured logging
│   │   │   ├── crypto.py             # Token encryption
│   │   │   └── validators.py         # Input validation
│   │   │
│   │   └── prompts/                  # System prompts (language-specific)
│   │       ├── __init__.py
│   │       ├── python.py
│   │       ├── nodejs.py
│   │       ├── terraform.py
│   │       └── sql.py
│   │
│   ├── tests/
│   │   ├── conftest.py               # Pytest fixtures
│   │   ├── unit/
│   │   │   ├── test_auth.py
│   │   │   ├── test_storage.py
│   │   │   ├── test_detectors.py
│   │   │   └── test_api_client.py
│   │   ├── integration/
│   │   │   ├── test_chat_flow.py
│   │   │   └── test_okta_flow.py
│   │   └── fixtures/
│   │       ├── mock_bedrock.py
│   │       └── sample_projects/
│   │
│   └── README.md                     # CLI documentation
│
├── backend/                          # FastAPI backend service
│   ├── pyproject.toml                # Poetry configuration
│   ├── src/backend/
│   │   ├── __main__.py               # Uvicorn entry point
│   │   ├── main.py                   # FastAPI app
│   │   ├── config.py                 # Settings (env vars)
│   │   │
│   │   ├── routers/                  # API endpoints
│   │   │   ├── __init__.py
│   │   │   ├── chat.py               # POST /api/v1/chat
│   │   │   ├── analyze.py            # POST /api/v1/analyze
│   │   │   ├── summarize.py          # POST /api/v1/summarize
│   │   │   └── usage.py              # GET /api/v1/usage
│   │   │
│   │   ├── auth/                     # Authentication middleware
│   │   │   ├── __init__.py
│   │   │   ├── jwt_validator.py      # JWT signature validation
│   │   │   ├── jwk_manager.py        # Okta JWK key caching
│   │   │   └── rate_limiter.py       # Rate limit middleware
│   │   │
│   │   ├── bedrock/                  # Bedrock integration
│   │   │   ├── __init__.py
│   │   │   ├── client.py             # Bedrock API wrapper
│   │   │   ├── models.py             # Bedrock request/response models
│   │   │   ├── prompt_builder.py     # Build system + user prompts
│   │   │   └── streaming.py          # Stream response handler
│   │   │
│   │   ├── services/                 # Business logic
│   │   │   ├── __init__.py
│   │   │   ├── chat_service.py       # Orchestrate chat flow
│   │   │   ├── analysis_service.py   # Project analysis
│   │   │   ├── rate_limit_service.py # Rate limit tracking
│   │   │   └── context_builder.py    # Build context from project files
│   │   │
│   │   ├── models/                   # Pydantic models
│   │   │   ├── __init__.py
│   │   │   ├── requests.py           # Request schemas
│   │   │   ├── responses.py          # Response schemas
│   │   │   └── domain.py             # Domain models
│   │   │
│   │   └── utils/
│   │       ├── logging.py
│   │       └── validators.py
│   │
│   ├── tests/                        # Backend tests
│   │   ├── conftest.py
│   │   ├── unit/
│   │   │   ├── test_jwt_validator.py
│   │   │   ├── test_rate_limiter.py
│   │   │   ├── test_bedrock_client.py
│   │   │   └── test_services.py
│   │   ├── integration/
│   │   │   ├── test_chat_endpoint.py
│   │   │   └── test_okta_validation.py
│   │   └── fixtures/
│   │       └── mock_bedrock.py
│   │
│   └── README.md
│
├── extension/                        # VS Code Extension
│   ├── package.json                  # Extension manifest
│   ├── tsconfig.json
│   ├── webpack.config.js
│   │
│   ├── src/
│   │   ├── extension.ts              # Extension entry point
│   │   ├── webview.ts                # Webview manager
│   │   │
│   │   ├── panels/                   # VS Code panels
│   │   │   └── ChatPanel.ts          # Chat sidebar panel
│   │   │
│   │   ├── providers/                # VS Code providers
│   │   │   ├── CommandProvider.ts    # Command palette commands
│   │   │   └── StatusBarProvider.ts  # Status bar (auth, quota)
│   │   │
│   │   ├── auth/                     # Auth integration
│   │   │   ├── OktaAuth.ts           # OIDC flow
│   │   │   └── TokenManager.ts       # Token storage/validation
│   │   │
│   │   ├── storage/                  # .dev-cli/ integration
│   │   │   ├── FileSystemStorage.ts  # Read/write .dev-cli/
│   │   │   └── ConversationDB.ts     # SQLite access
│   │   │
│   │   ├── api/                      # Backend API client
│   │   │   └── ApiClient.ts
│   │   │
│   │   ├── ui/                       # React components
│   │   │   ├── ChatView.tsx
│   │   │   ├── ConversationSidebar.tsx
│   │   │   ├── MessageInput.tsx
│   │   │   ├── MessageDisplay.tsx
│   │   │   └── ContextBrowser.tsx
│   │   │
│   │   └── utils/
│   │       ├── logging.ts
│   │       └── validators.ts
│   │
│   ├── webview-ui/                   # React app for webview
│   │   ├── index.tsx
│   │   ├── App.tsx
│   │   ├── styles/
│   │   └── components/               # React components
│   │
│   ├── tests/
│   │   ├── unit/
│   │   └── integration/
│   │
│   └── README.md
│
├── infrastructure/                   # Terraform IaC
│   ├── terraform.tf                  # Provider config
│   ├── variables.tf                  # Input variables
│   ├── outputs.tf                    # Outputs
│   │
│   ├── modules/
│   │   ├── api/                      # API Gateway + ALB
│   │   │   ├── main.tf
│   │   │   ├── variables.tf
│   │   │   └── outputs.tf
│   │   │
│   │   ├── compute/                  # ECS Fargate
│   │   │   ├── main.tf
│   │   │   ├── variables.tf
│   │   │   └── iam.tf
│   │   │
│   │   ├── database/                 # DynamoDB (rate limits)
│   │   │   ├── main.tf
│   │   │   └── variables.tf
│   │   │
│   │   ├── auth/                     # Okta integration
│   │   │   ├── main.tf
│   │   │   └── variables.tf
│   │   │
│   │   ├── monitoring/               # CloudWatch
│   │   │   ├── main.tf
│   │   │   └── alarms.tf
│   │   │
│   │   └── secrets/                  # Secrets Manager
│   │       └── main.tf
│   │
│   ├── dev.tfvars                    # Dev environment
│   └── prod.tfvars                   # Prod environment
│
├── docs/
│   ├── ARCHITECTURE.md               # Architecture deep-dive
│   ├── API.md                        # API reference
│   ├── CLI.md                        # CLI command reference
│   ├── EXTENSION.md                  # VS Code extension guide
│   ├── AUTH.md                       # Okta SSO flow
│   ├── LANGUAGES.md                  # Supported languages
│   ├── DEPLOYMENT.md                 # Deployment guide
│   └── CONTRIBUTING.md               # Dev contribution guide
│
├── .gitignore
├── README.md                         # Project overview
├── ROADMAP.md                        # Development roadmap
└── LICENSE
```

## AWS CLI Integration

### Overview

Dev-CLI can execute AWS CLI commands to help developers triage infrastructure issues (CloudWatch logs, IAM permissions, Lambda config, RDS schema, S3 metadata, etc.). This uses the **user’s active AWS profile** and respects their **AWS IAM permissions**.

### Architecture

```
CLI detects AWS request in user message
         ↓
Auto-detect AWS profile OR ask user
         ↓
Load AWS credentials from ~/.aws/credentials
         ↓
Check if command is modify/delete
         ├─ Yes: Show command, ask user confirmation
         └─ No: Execute immediately (or ask based on config)
         ↓
Execute: subprocess("aws <command> --profile <profile>")
         ↓
Capture output (stdout + stderr)
         ↓
Cache result (30s TTL, avoid duplicate calls)
         ↓
Add to Bedrock context: "AWS result: [output]"
         ↓
Bedrock analyzes output + project files
         ↓
Provide insights: "The error is caused by..."
```

### AWS Profile Detection

#### Priority Order (What CLI checks):

1. **Explicit flag:** `dev-cli chat --aws-profile prod`
1. **Environment variable:** `export AWS_PROFILE=prod && dev-cli chat`
1. **Default profile in ~/.aws/config:** `[default]`
1. **Auto-detect:** Scan available profiles, show list, ask user

#### Example: Auto-Detection

```bash
$ dev-cli chat

🔍 Detecting AWS profiles...
  ✓ Found 3 profiles:
    - default (account: 123456789)
    - prod (account: 987654321, region: us-west-2)
    - staging (account: 555555555, region: us-east-1)

Which profile? (default: prod)
> prod

✓ Using AWS profile: prod
✓ Authenticated as: arn:aws:iam::987654321:role/DevRole
✓ Permissions: bedrock:InvokeModel, logs:*, cloudwatch:*, iam:List*

Ready to chat! Type your question.
> Check CloudWatch logs for lambda errors
```

### AWS Command Execution

#### Supported Use Cases

```python
# Detect and execute AWS CLI commands from user message

# Example 1: View CloudWatch logs
User: "Show me the last 10 error logs from my lambda"
CLI Detection: aws logs tail /aws/lambda/my-func --max-items 10
User Confirmation: "Run this? (y/n)" → y
Execution: ✓ [log output]

# Example 2: Check IAM permissions
User: "What permissions do I have?"
CLI Detection: aws iam list-attached-user-policies --user-name john
User Confirmation: "Run this? (y/n)" → y
Execution: ✓ [policies list]

# Example 3: Get Lambda config
User: "Show environment variables for my lambda"
CLI Detection: aws lambda get-function-configuration --function-name my-func
User Confirmation: "Run this? (y/n)" → y
Execution: ✓ [config JSON]

# Example 4: Check RDS schema (RISKY - ask first)
User: "List all tables in the database"
CLI Detection: aws rds describe-db-instances
User Confirmation: "⚠️  This could list sensitive config. Confirm? (y/n)" → y
Execution: ✓ [database list]

# Example 5: Modify (DANGEROUS - always ask)
User: "Reset the environment variable"
CLI Detection: aws lambda update-function-configuration ...
User Confirmation: "⚠️  This will MODIFY Lambda. Confirm? (y/n)" → y
Execution: ✓ [update confirmed]

# Example 6: Delete (VERY DANGEROUS - double confirm)
User: "Delete this log group"
CLI Detection: aws logs delete-log-group --log-group-name /aws/lambda/...
User Confirmation (1): "⚠️  DESTRUCTIVE: This will DELETE /aws/lambda/... Confirm? (y/n)" → y
User Confirmation (2): "Type 'DELETE' to confirm permanent deletion:" → DELETE
Execution: ✓ [deletion confirmed]
```

### Command Classification & Confirmation

#### Read-Only Commands (Auto-execute, no confirm)

```
aws logs tail <log-group>
aws cloudwatch get-metric-statistics
aws iam list-attached-user-policies
aws lambda get-function-configuration
aws s3api head-bucket
aws rds describe-db-instances
aws dynamodb describe-table
aws ec2 describe-instances
aws secretsmanager get-secret-value (with audit)
```

#### Modify Commands (Ask user first)

```
aws lambda update-function-configuration
aws dynamodb update-item
aws s3api put-object-acl
aws rds modify-db-instance
aws ec2 create-security-group
aws iam attach-user-policy
```

#### Delete Commands (Double confirm)

```
aws logs delete-log-group
aws dynamodb delete-item
aws s3 rm s3://bucket/key
aws rds delete-db-instance
aws ec2 terminate-instances
aws iam delete-user-policy
```

### Implementation: AWS CLI Module

```python
# cli/src/aws_cli/manager.py

class AWSCLIManager:
    """Execute AWS CLI commands with user's active profile"""
    
    def __init__(self):
        self.cache = {}  # {command_hash: (output, timestamp)}
        self.cache_ttl = 30  # 30 seconds
    
    async def detect_profile(self):
        """Auto-detect AWS profile"""
        # 1. Check --aws-profile flag
        # 2. Check AWS_PROFILE env var
        # 3. Check ~/.aws/config [default]
        # 4. List available profiles, ask user
    
    async def detect_aws_command(self, user_message: str) -> str | None:
        """Parse user message for AWS CLI command intent"""
        # Use NLP/patterns to detect:
        # - "show logs" → aws logs tail
        # - "what permissions" → aws iam list-attached-user-policies
        # - "lambda config" → aws lambda get-function-configuration
        # - etc.
        pass
    
    async def classify_command(self, command: str) -> str:
        """Classify: read|modify|delete"""
        if any(cmd in command for cmd in ["tail", "describe", "list", "get"]):
            return "read"
        elif any(cmd in command for cmd in ["update", "put", "create"]):
            return "modify"
        elif any(cmd in command for cmd in ["delete", "remove", "terminate"]):
            return "delete"
    
    async def execute(
        self,
        command: str,
        profile: str,
        auto_confirm: bool = False
    ) -> str:
        """Execute AWS CLI command with confirmation"""
        
        # Check cache
        cache_key = hash((command, profile))
        if cache_key in self.cache:
            cached_output, cached_time = self.cache[cache_key]
            if time.time() - cached_time < self.cache_ttl:
                return cached_output
        
        # Classify command
        classification = await self.classify_command(command)
        
        # Confirm based on classification
        if classification == "read":
            confirm = True  # No confirm needed
        elif classification == "modify":
            confirm = await self._ask_user(
                f"ℹ️  This will MODIFY resources:\n{command}\nConfirm? (y/n)",
                require_type=False
            )
        elif classification == "delete":
            confirm = await self._ask_user(
                f"⚠️  DESTRUCTIVE: This will DELETE resources:\n{command}\nConfirm? (y/n)",
                require_type=False
            )
            if confirm:
                confirm = await self._ask_user(
                    "Type 'DELETE' to confirm permanent deletion:",
                    require_type="DELETE"
                )
        
        if not confirm:
            return "[Cancelled by user]"
        
        # Execute
        try:
            result = subprocess.run(
                f"aws {command} --profile {profile}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            output = result.stdout if result.returncode == 0 else result.stderr
            
            # Cache result
            self.cache[cache_key] = (output, time.time())
            
            return output
        except subprocess.TimeoutExpired:
            return "[Error: Command timeout (30s)]"
        except Exception as e:
            return f"[Error: {str(e)}]"
    
    async def _ask_user(self, prompt: str, require_type: str | bool = False):
        """Ask user for confirmation"""
        if require_type is False:
            # Yes/no question
            user_input = input(f"{prompt} > ").strip().lower()
            return user_input in ["y", "yes"]
        else:
            # Require exact string
            user_input = input(f"{prompt} > ").strip()
            return user_input == require_type

# Usage in chat loop:
aws_manager = AWSCLIManager()

# In chat loop:
user_message = "Check CloudWatch logs"
detected_cmd = await aws_manager.detect_aws_command(user_message)
if detected_cmd:
    aws_output = await aws_manager.execute(detected_cmd, profile="prod")
    # Add aws_output to Bedrock context
```

### Error Handling

```python
# Handle AWS CLI errors gracefully

if "InvalidParameterException" in output:
    return "Error: Invalid AWS parameter. Check your syntax."

if "NoCredentialsError" in output:
    return "Error: No AWS credentials found. Check ~/.aws/credentials"

if "AccessDenied" in output:
    return "Error: Access denied. Your AWS role lacks this permission."

if "ThrottlingException" in output:
    return "Error: AWS API throttled. Retry in a few seconds."
```

### Audit Logging

All AWS CLI executions are logged to CloudWatch:

```json
{
  "timestamp": "2025-03-20T14:30:00Z",
  "user_id": "okta_user_123",
  "aws_profile": "prod",
  "aws_command": "aws logs tail /aws/lambda/my-func",
  "command_classification": "read",
  "user_confirmed": true,
  "execution_time_ms": 245,
  "status": "success",
  "output_length": 5120
}
```

### Functional Requirements

#### FR-1: Interactive CLI Experience

- **FR-1.1** – CLI supports interactive multi-turn conversation (chat loop)
- **FR-1.2** – User can ask questions like: “develop this”, “enhance”, “debug”, “refactor”, “test”, “dependency mapping”
- **FR-1.3** – CLI maintains conversation history in `.dev-cli/conversation.db`
- **FR-1.4** – User can view/clear/export conversation history
- **FR-1.5** – CLI respects configurable history limit (default: last 50 messages)
- **FR-1.6** – CLI supports both terminal TTY mode and piped input

#### FR-2: VS Code Extension Experience

- **FR-2.1** – VS Code extension provides sidebar chat panel
- **FR-2.2** – Chat panel UI mirrors CLI experience (same conversation history, context)
- **FR-2.3** – Extension shows project path and detected languages in header
- **FR-2.4** – Extension supports file browser (read-only) to understand project structure
- **FR-2.5** – Extension displays auth status and quota usage in status bar

#### FR-3: Multi-Language Support

- **FR-3.1** – Auto-detect project languages: Python, Node.js, TypeScript, Terraform, SQL, Go, etc.
- **FR-3.2** – Build project manifest with detected frameworks (FastAPI, React, Django, Express, etc.)
- **FR-3.3** – Provide language-specific system prompts for Bedrock
- **FR-3.4** – Support polyglot projects (mixed languages)
- **FR-3.5** – Extensible detector system for future languages

#### FR-4: Context Management

- **FR-4.1** – All conversation stored in `.dev-cli/conversation.db` (SQLite)
- **FR-4.2** – Project metadata stored in `.dev-cli/project_manifest.json`
- **FR-4.3** – Config (auth token, settings) in `~/.dev-cli/config`
- **FR-4.4** – Support context summarization (auto or manual)
- **FR-4.5** – Store summaries in `.dev-cli/summaries/`
- **FR-4.6** – `.dev-cli/` folder excluded from git by default

#### FR-5: Authentication & Session Management

- **FR-5.1** – User runs `dev-cli login` → browser opens → Okta SSO
- **FR-5.2** – Local callback server (localhost:8888) captures auth code
- **FR-5.3** – CLI exchanges code for JWT (PKCE flow)
- **FR-5.4** – CLI validates JWT locally using Okta JWK keys (cached)
- **FR-5.5** – Token stored encrypted in `~/.dev-cli/config`
- **FR-5.6** – Session valid for 24 hours; auto-refresh if < 1h remaining
- **FR-5.7** – User can logout: `dev-cli logout` clears token
- **FR-5.8** – VS Code extension reuses same token from CLI

#### FR-6: API Integration

- **FR-6.1** – CLI sends chat request to backend with JWT in Authorization header
- **FR-6.2** – Backend validates JWT signature locally
- **FR-6.3** – Backend enforces rate limits (per-user per-day)
- **FR-6.4** – Backend streams Bedrock response back to client
- **FR-6.5** – Backend logs all requests (audit trail)

#### FR-7: Rate Limiting

- **FR-7.1** – Default quota: 100 requests per user per day
- **FR-7.2** – Quota configurable per user (admin panel or env var)
- **FR-7.3** – Soft limit warning at 80% usage
- **FR-7.4** – Hard limit returns 429 Too Many Requests
- **FR-7.5** – Daily reset at midnight UTC
- **FR-7.6** – CLI displays remaining quota

### Non-Functional Requirements

#### NFR-1: Performance

- **NFR-1.1** – P50 response time (time-to-first-token): < 2s
- **NFR-1.2** – P95 response time: < 5s
- **NFR-1.3** – CLI startup time: < 1s
- **NFR-1.4** – Extension webview load: < 2s

#### NFR-2: Reliability

- **NFR-2.1** – Backend uptime: 99.9%
- **NFR-2.2** – Graceful degradation if Bedrock unavailable
- **NFR-2.3** – Retry logic for transient failures (exponential backoff)
- **NFR-2.4** – Local conversation stored even if API call fails

#### NFR-3: Scalability

- **NFR-3.1** – Support 1000s of concurrent users
- **NFR-3.2** – Stateless backend (no session affinity needed)
- **NFR-3.3** – Rate limit tracking via DynamoDB (distributed)

#### NFR-4: Security

- **NFR-4.1** – All tokens encrypted at rest (using OS keyring or ~/.dev-cli/ encrypted file)
- **NFR-4.2** – All communication TLS 1.2+
- **NFR-4.3** – JWT signed and verified via JWK
- **NFR-4.4** – Project code not stored on backend (unless explicitly cached)
- **NFR-4.5** – GDPR compliance: export/delete user data on request

#### NFR-5: Usability

- **NFR-5.1** – One-command installation: `pip install dev-cli`
- **NFR-5.2** – Minimal setup: `dev-cli init` in project folder
- **NFR-5.3** – Clear error messages and troubleshooting
- **NFR-5.4** – Help system: `dev-cli --help`, `dev-cli <command> --help`

-----

## CLI Design & Commands

### Command Reference

#### Global Flags

```
--help, -h           Show help
--version, -v        Show version
--verbose            Verbose logging (debug level)
--config <path>      Config file path (default: ~/.dev-cli/config)
```

#### `dev-cli init`

Initialize `.dev-cli/` folder in current project.

```bash
$ dev-cli init [--project-path /path/to/project]

Description:
  Creates .dev-cli/ folder and initializes:
  - config.json (blank, waiting for auth)
  - conversation.db (empty SQLite DB)
  - project_manifest.json (auto-detected languages/frameworks)

Options:
  --project-path PATH   Project path (default: current directory)
  --force              Overwrite existing .dev-cli/ (with warning)

Example:
  $ cd my-project
  $ dev-cli init
  ✓ Created .dev-cli/ folder
  ✓ Detected languages: python, typescript
  ✓ Detected frameworks: fastapi, react
  ✓ Run 'dev-cli login' to authenticate
```

#### `dev-cli login`

Authenticate via Okta SSO.

```bash
$ dev-cli login

Description:
  Opens browser → Okta login page
  Waits for callback on localhost:8888
  Exchanges auth code for JWT
  Stores token in ~/.dev-cli/config

Output:
  ✓ Authenticated as user@example.com
  ✓ Session valid until 2025-03-21 14:30:00 UTC
  ✓ Ready to use dev-cli!

Example:
  $ dev-cli login
  Opening Okta login in browser...
  Waiting for callback on http://localhost:8888/callback
  [User logs in via browser]
  ✓ Authenticated successfully
```

#### `dev-cli chat`

Start interactive chat session.

```bash
$ dev-cli chat [--project-path /path/to/project]

Description:
  Interactive multi-turn conversation loop
  Loads conversation history from .dev-cli/conversation.db
  Sends messages to backend API + Bedrock
  Streams responses back to terminal

Options:
  --project-path PATH   Project path (default: current directory)
  --no-history          Start fresh (don't load history)
  --limit N             Load last N messages (default: 50)

Usage:
  > develop this new feature: user authentication
  
  AI: I'll help you implement user authentication...
  [response streaming...]
  
  > how do I test this module?
  
  AI: Here are the key test cases...
  
  > exit (or Ctrl+C)

Commands within chat:
  /history             Show conversation history
  /clear               Clear conversation
  /summary             Generate summary of conversation
  /analyze             Analyze project structure
  /context             Show current context (project manifest)
  /exit or /quit       Exit chat loop
  /help                Show in-chat help
```

#### `dev-cli analyze`

Analyze project structure (one-shot, no conversation).

```bash
$ dev-cli analyze [--project-path PATH] [--output json|md|text]

Description:
  Analyzes project:
  - Detected languages and frameworks
  - File structure
  - Key dependencies
  - Architecture insights

Options:
  --project-path PATH   Project path (default: current directory)
  --output FORMAT       Output format: json, md, text (default: text)
  --depth N             Max folder depth to scan (default: 3)

Example:
  $ dev-cli analyze --output md > project_analysis.md
  
  Output:
  # Project Analysis: MyAPI
  
  ## Languages Detected
  - Python 3.11 (FastAPI)
  - JavaScript/TypeScript (React)
  
  ## Key Files
  - main.py (FastAPI app)
  - requirements.txt (Python deps)
  - package.json (Node deps)
  
  ## Architecture
  - Monorepo (backend + frontend)
  - FastAPI REST API on port 8000
  - React SPA on port 3000
```

#### `dev-cli config`

Manage configuration and settings.

```bash
$ dev-cli config [--set KEY=VALUE | --get KEY | --list]

Description:
  View or modify CLI configuration

Options:
  --set KEY=VALUE       Set config value
  --get KEY             Get config value
  --list                List all config (excluding sensitive)
  --reset               Reset to defaults

Settings:
  history_limit        Max messages to store (default: 50)
  auto_summarize       Auto-summarize after N messages (default: 0, disabled)
  bedrock_model        Model: sonnet|opus (default: sonnet)
  rate_limit_warning   Warn at % of daily quota (default: 80)

Example:
  $ dev-cli config --set history_limit=100
  ✓ Updated history_limit to 100

  $ dev-cli config --get bedrock_model
  sonnet

  $ dev-cli config --list
  history_limit: 50
  auto_summarize: 0
  bedrock_model: sonnet
  rate_limit_warning: 80
```

#### `dev-cli context`

Manage conversation context.

```bash
$ dev-cli context [--view | --clear | --export | --summary]

Description:
  View or manage local conversation context

Options:
  --view               Show conversation history (paginated)
  --clear              Clear all conversations (with confirmation)
  --export FILE        Export conversation to markdown/JSON
  --summary            Generate/show summary
  --limit N            Show last N messages (with --view)

Example:
  $ dev-cli context --view --limit 10
  
  Conversation History (last 10 messages):
  
  1. User: How do I optimize the database query?
     AI: Here are some optimization strategies...
     
  2. User: Can I use indexes?
     AI: Yes, indexes can significantly improve...
  
  $ dev-cli context --summary
  
  Summary (auto-generated):
  Discussed database query optimization, including index usage...
```

#### `dev-cli logout`

Clear authentication token.

```bash
$ dev-cli logout

Description:
  Clears JWT token from ~/.dev-cli/config
  Logs out user (next command will require re-auth)

Example:
  $ dev-cli logout
  ✓ Logged out successfully
  ✓ Next run will require authentication
```

#### `dev-cli status`

Show CLI status and quota.

```bash
$ dev-cli status

Description:
  Display authentication status and API quota usage

Output:
  Authentication:
    User: john.doe@example.com
    Status: Authenticated
    Session expires: 2025-03-21 14:30:00 UTC
    
  API Quota (Today):
    Used: 45 / 100 requests
    Remaining: 55 (55%)
    Resets: 2025-03-21 00:00:00 UTC
    
  Project:
    Path: /home/user/my-project
    Languages: python, typescript
    Last active: 2025-03-20 14:00:00 UTC
```

### Chat Loop Example

```bash
$ dev-cli chat

📁 Project: /home/user/my-api
🔍 Detected: Python (FastAPI), PostgreSQL, Docker

[Loaded 5 previous messages from history]

> I'm getting a timeout error in the payment API endpoint. Can you help debug?

🤖 Assistant:
I'll help you debug the timeout. Based on your project structure, I can see
you're using FastAPI with PostgreSQL. Let me analyze the payment endpoint...

[Response streaming...]

The timeout is likely caused by:
1. Unoptimized database query in get_payment_status()
2. Missing index on payments.user_id
3. No query timeout set

Recommendations:
- Add database index: CREATE INDEX idx_payments_user ON payments(user_id);
- Set query timeout: db_timeout=5000 in your ORM config
- Consider caching payment statuses

> Can you show me the code changes?

🤖 Assistant:
Here's the refactored code...

[Code blocks with syntax highlighting]

> Exit (Ctrl+C)

✓ Conversation saved (6 messages)
✓ Summary: "Debugged payment API timeout; recommended db index + query timeout"
```

-----

## VS Code Extension Design

### Overview

The VS Code Extension provides a **Chat Webview Panel** in the sidebar, offering the same experience as the CLI but with a graphical interface.

### User Experience

#### Installation

```bash
# From VS Code Marketplace
1. Open VS Code
2. Ctrl+Shift+X (Extensions)
3. Search "Dev-CLI"
4. Click Install
5. Reload VS Code
```

#### Setup

```
1. Open Command Palette (Ctrl+Shift+P)
2. "Dev-CLI: Set Project Path"
3. Select project folder
4. Extension detects languages, initializes .dev-cli/
5. Status bar shows "Dev-CLI: Ready" (green dot)
```

#### Login

```
1. Click "Dev-CLI" in sidebar (or Ctrl+Shift+D)
2. Chat panel opens
3. If not authenticated, shows "Login" button
4. Click → browser opens → Okta login
5. Extension validates token, shows "Authenticated as ..."
6. Chat becomes active
```

#### Chat Interaction

```
┌────────────────────────────────────────────┐
│ 📁 Dev-CLI: /Users/user/my-project        │
│ 🟢 john.doe@example.com | 45/100 quota    │
├────────────────────────────────────────────┤
│                                            │
│ 1. User: refactor this service            │
│    AI: I'll help refactor the service...  │
│    [response streaming]                    │
│                                            │
│ 2. User: What about error handling?       │
│    AI: Here's a better error handling...  │
│                                            │
├────────────────────────────────────────────┤
│ [Message input box]                        │
│ Type your question or use /help            │
│ [Send button]                              │
├────────────────────────────────────────────┤
│ 📂 Files | 📋 Context | ⚙️ Settings       │
│                                            │
│ [Collapsible file browser]                 │
│ my-project/                                │
│  ├─ src/                                   │
│  │  ├─ main.py ✓                          │
│  │  └─ services/                          │
│  └─ tests/                                 │
└────────────────────────────────────────────┘
```

### Extension Components

#### ChatPanel (Main Sidebar)

- **Message Display** – Scrollable conversation history with syntax highlighting
- **Message Input** – Text box with `/command` support
- **Header** – Project path, user info, quota meter
- **Tabs** – Files, Context, Settings
- **Status Bar** – Auth status, quota, last sync time

#### File Browser

- Read-only tree view of project files
- Click file → open in editor + include in context
- Shows icons for file types (Python, TS, JSON, etc.)
- Filters: hide .dev-cli/, node_modules, .git, etc.

#### Context Tab

- Shows `project_manifest.json` (languages, frameworks)
- Displays `~/.dev-cli/config` (settings, not secrets)
- Shows conversation summary

#### Settings Tab

- Auth status + login/logout
- History limit slider
- Model selection (Sonnet/Opus)
- Clear conversation button
- Export conversation button

#### Status Bar

- Left: “Dev-CLI: Ready” (green dot) or “Dev-CLI: Not authenticated” (red)
- Right: “45/100 quota” (click to open panel)

### Commands (Command Palette)

```
Dev-CLI: Open Chat Panel             (Ctrl+Shift+D)
Dev-CLI: Set Project Path
Dev-CLI: Login
Dev-CLI: Logout
Dev-CLI: Clear Conversation
Dev-CLI: Export Conversation
Dev-CLI: View Context
Dev-CLI: Analyze Project
Dev-CLI: Show Quota
Dev-CLI: Open Settings
```

### Implementation Details

#### Extension Entry Point

```typescript
// src/extension.ts
export async function activate(context: vscode.ExtensionContext) {
  // Initialize extension
  // Register commands
  // Load token from ~/.dev-cli/config
  // Create ChatPanel webview
  // Set up status bar
  // Register handlers
}
```

#### Token Management

```typescript
// src/auth/TokenManager.ts
// Read token from ~/.dev-cli/config
// Validate JWT locally (using Okta JWK keys)
// Handle refresh token logic
// Trigger re-auth if expired
```

#### .dev-cli/ Integration

```typescript
// src/storage/FileSystemStorage.ts
// Read/write to .dev-cli/ folder
// SQLite access via sqlite3 library
// Project manifest reading
// Conversation DB operations
```

#### API Client

```typescript
// src/api/ApiClient.ts
// HTTP client with JWT in Authorization header
// Streaming response handling
// Error handling + retry logic
```

### UI Components (React)

```
ChatView
  ├─ ChatHeader (project path, user, quota)
  ├─ MessageList (scrollable conversation)
  │  └─ MessageItem (user/AI message with syntax highlighting)
  ├─ MessageInput (text box + /commands)
  └─ Tabs
     ├─ Files (tree view)
     ├─ Context (manifest + settings)
     └─ Settings (auth, config, actions)
```

-----

## Context Management

### Local Storage Schema (`.dev-cli/` + `~/.dev-cli/`)

```
SYSTEM-LEVEL (Shared across ALL projects):
~/.dev-cli/
├── config.json                        # Single login token (encrypted JWT) + settings
│   └─ Shared across all projects/CLI invocations
│   └─ Updated when token refreshes
└── .gitignore                         # Prevent accidental commits

PROJECT-LEVEL (Per project):
project-folder/.dev-cli/
├── conversation.db                    # SQLite: conversation history for THIS project
├── project_manifest.json              # Auto-detected languages, frameworks, structure
├── summaries/
│   ├── summary_20250320.md           # Auto-generated summary
│   └── summary_manual_20250320.md    # User-triggered summary
└── .gitignore                         # Ignore .dev-cli/ in git
```

**Key Difference from v1.0:**

- ✅ Auth token is **system-level** (~/.dev-cli/config) – login once, use everywhere
- ✅ Conversations are **project-level** (.dev-cli/conversation.db) – each project isolated
- ✅ Settings stored in **system-level** config – global preferences (bedrock_model, history_limit, etc.)

### `config.json` Schema

```json
{
  "version": "1.0",
  "user": {
    "sub": "okta-user-id",
    "email": "user@example.com"
  },
  "auth": {
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",  // Encrypted
    "token_expires_at": "2025-03-21T14:30:00Z",
    "refresh_token": "ref_...",                     // Encrypted (optional)
    "refresh_expires_at": "2025-06-20T14:30:00Z"
  },
  "settings": {
    "history_limit": 50,
    "auto_summarize_after": 0,
    "bedrock_model": "sonnet",
    "rate_limit_warning_percent": 80,
    "include_file_context": true
  },
  "api": {
    "endpoint": "https://api.dev-cli.example.com",
    "timeout_seconds": 30
  }
}
```

### `conversation.db` Schema (SQLite)

```sql
CREATE TABLE conversations (
  id TEXT PRIMARY KEY,
  project_path TEXT NOT NULL,
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  summary TEXT
);

CREATE TABLE messages (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(id),
  role TEXT NOT NULL,  -- 'user' or 'assistant'
  content TEXT NOT NULL,
  tokens_used INTEGER,
  created_at TIMESTAMP,
  FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE TABLE context_snapshots (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(id),
  project_manifest JSONB,  -- Languages, frameworks, structure
  included_files TEXT,     -- JSON list of files included in context
  created_at TIMESTAMP,
  FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);
```

### `project_manifest.json` Schema

```json
{
  "version": "1.0",
  "scanned_at": "2025-03-20T14:30:00Z",
  "project": {
    "name": "my-api",
    "path": "/Users/user/my-api",
    "description": "FastAPI + React web application"
  },
  "languages": [
    {
      "language": "Python",
      "version": "3.11",
      "file_count": 45,
      "frameworks": ["fastapi", "sqlalchemy", "pydantic"],
      "key_files": ["main.py", "requirements.txt"]
    },
    {
      "language": "TypeScript",
      "version": "5.0",
      "file_count": 32,
      "frameworks": ["react", "axios"],
      "key_files": ["package.json", "tsconfig.json"]
    }
  ],
  "databases": [
    {
      "type": "postgresql",
      "detected_by": ["sqlalchemy URLs in main.py"],
      "version": "14"
    }
  ],
  "infrastructure": [
    {
      "type": "docker",
      "files": ["Dockerfile", "docker-compose.yml"]
    },
    {
      "type": "terraform",
      "files": ["main.tf", "variables.tf"],
      "providers": ["aws"]
    }
  ],
  "dependencies": {
    "total_direct": 28,
    "total_transitive": 450,
    "outdated_packages": 3
  },
  "structure": {
    "folders": [
      {"path": "src", "type": "source"},
      {"path": "tests", "type": "tests"},
      {"path": "infra", "type": "infrastructure"},
      {"path": "docs", "type": "documentation"}
    ]
  }
}
```

### Context Lifecycle

```
1. User runs: dev-cli chat
   ↓
2. Load conversation_id from ~/.dev-cli/config (or generate new)
   ↓
3. Load last N messages from conversation.db
   ↓
4. Load project_manifest.json (auto-detect if missing)
   ↓
5. Load latest context_snapshot from conversation.db
   ↓
6. Build prompt:
   - System prompt (language-specific)
   - Project context (manifest)
   - File context (if included)
   - Conversation history (last N turns)
   ↓
7. Send to Bedrock
   ↓
8. Get response
   ↓
9. Store in conversation.db + write to terminal
   ↓
10. Track tokens, update summaries
```

### Memory & Summarization

#### Auto-Summarization

```python
# Trigger after N messages (configurable)
if len(conversation.messages) % auto_summarize_after == 0:
    summary = bedrock.summarize(conversation.messages)
    save_to_summaries_folder(summary)
    # Keep full conversation + summary
```

#### Manual Summarization

```bash
$ dev-cli context --summary
# Generates new summary of entire conversation
# Stores in .dev-cli/summaries/summary_manual_DATE.md
```

#### Summary Format

```markdown
# Conversation Summary

**Date:** 2025-03-20  
**Duration:** 2 hours  
**Message Count:** 42  
**Tokens Used:** 15,230

## Topics Discussed

1. Database query optimization
   - Identified N+1 query problem
   - Recommended index on user_id
   - Provided refactored query

2. Error handling improvements
   - Discussed exception handling strategies
   - Reviewed current error logs
   - Suggested custom exception classes

## Key Recommendations

- [ ] Add database index (critical)
- [ ] Refactor payment endpoint (high priority)
- [ ] Update error handling (medium priority)

## Next Steps

Continue with frontend optimization...
```

-----

## Authentication & Authorization

### System-Level Authentication (One Login, Everywhere)

```
Scenario 1: First use
  $ dev-cli chat (in any project)
  → Check ~/.dev-cli/config for token
  → Token doesn't exist
  → dev-cli login
  → Browser: Okta SSO
  → Token stored in ~/.dev-cli/config
  → dev-cli chat continues

Scenario 2: Second project, same device
  $ dev-cli chat (in different project)
  → Check ~/.dev-cli/config for token
  → Token exists & valid
  → Reuse token (no re-auth needed)
  → dev-cli chat starts immediately

Scenario 3: Token expired (after 24 hours)
  $ dev-cli chat
  → Check ~/.dev-cli/config for token
  → Token expired
  → Auto-refresh token (using refresh_token)
  → Continue chat
  → If refresh fails: dev-cli login
```

**Key Benefit:** Users authenticate **once per system**, not once per project or invocation.

### Okta SSO Flow (AWS SSO-Like)

#### Step 1: Trigger Login

```bash
$ dev-cli login

CLI Output:
Opening Okta login in browser...
Waiting for callback on http://localhost:8888/callback
Press Ctrl+C to cancel
```

#### Step 2: Start Callback Server

```python
# src/auth/callback_handler.py
app = FastAPI()
callback_url = "http://localhost:8888/callback"

@app.get("/callback")
async def callback(code: str, state: str):
    # Receive auth code from Okta
    # Validate state for CSRF protection
    # Exchange code for JWT
    # Return HTML: "You can close this window"
```

#### Step 3: Exchange Code for JWT (PKCE)

```python
# src/auth/okta.py
async def exchange_code_for_token(code: str):
    """Exchange Okta auth code for JWT"""
    
    token_endpoint = f"{okta_domain}/oauth2/v1/token"
    
    response = httpx.post(
        token_endpoint,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://localhost:8888/callback",
            "client_id": config.OKTA_CLIENT_ID,
            "client_secret": config.OKTA_CLIENT_SECRET,
            "code_verifier": stored_code_verifier  # PKCE
        }
    )
    
    token_response = response.json()
    access_token = token_response["access_token"]
    id_token = token_response["id_token"]
    expires_in = token_response["expires_in"]
    
    return {
        "access_token": access_token,
        "id_token": id_token,
        "expires_at": datetime.now() + timedelta(seconds=expires_in)
    }
```

#### Step 4: Validate JWT Locally (No Backend Call)

```python
# src/auth/jwt_validator.py
class JWTValidator:
    def __init__(self, okta_domain: str):
        self.okta_domain = okta_domain
        self.jwk_cache = {}
        self.jwk_cache_ttl = 3600
    
    async def validate_token(self, token: str):
        """Validate JWT signature locally (no Okta call)"""
        try:
            # Decode without verification first
            unverified = jwt.get_unverified_header(token)
            kid = unverified["kid"]
            
            # Get cached JWK keys (cache for 1 hour)
            keys = await self.get_jwk_keys()
            key = self._find_key_by_kid(keys, kid)
            
            # Convert JWK to PEM
            public_key = jwk_to_pem(key)
            
            # Verify signature
            payload = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"]
            )
            
            # Check expiry
            if payload["exp"] < time.time():
                raise JWTError("Token expired")
            
            return payload  # Contains: sub, email, groups, etc.
        except JWTError as e:
            raise JWTError(f"Invalid token: {e}")
```

#### Step 5: Store Token Securely (Encrypted)

```python
# src/auth/token_store.py
class SecureTokenStore:
    def __init__(self, config_path: str = "~/.dev-cli/config"):
        self.config_path = Path(config_path).expanduser()
        self.encryption_key = self._get_or_create_key()
    
    def save_token(self, token_data: dict):
        """Save token encrypted to ~/.dev-cli/config"""
        config = self._load_config()
        config["auth"] = {
            "access_token": self._encrypt(token_data["access_token"]),
            "token_expires_at": token_data["expires_at"].isoformat(),
            "refresh_token": self._encrypt(token_data.get("refresh_token", ""))
        }
        self._save_config(config)
    
    def load_token(self) -> dict | None:
        """Load and decrypt token from ~/.dev-cli/config"""
        config = self._load_config()
        if "auth" not in config:
            return None
        
        auth = config["auth"]
        return {
            "access_token": self._decrypt(auth["access_token"]),
            "expires_at": datetime.fromisoformat(auth["token_expires_at"]),
            "refresh_token": self._decrypt(auth.get("refresh_token", ""))
        }
```

### Authorization: Okta Group Membership

Only users in the **`dev-cli-users`** Okta group can use the tool.

#### Group Extraction from JWT

```python
# JWT payload contains groups
{
    "sub": "okta_user_123",
    "email": "john@company.com",
    "groups": ["engineering", "dev-cli-users", "frontend-team"]
}
```

#### Authorization Check

```python
# When CLI makes API call to backend:

def authorize_user(jwt_payload: dict):
    """Check if user is in dev-cli-users group"""
    
    groups = jwt_payload.get("groups", [])
    
    if "dev-cli-users" not in groups:
        raise HTTPException(
            status_code=403,
            detail="Not authorized. User must be in 'dev-cli-users' Okta group."
        )
    
    return True
```

**If user is NOT in group:**

```
Error: Not authorized to use Dev-CLI
Reason: User must be in 'dev-cli-users' Okta group
Contact: devtools@company.com to request access
```

### Authorization: AWS Permissions

AWS IAM **already protects** destructive operations. Dev-CLI trusts AWS RBAC:

```
User's AWS Role: arn:aws:iam::123456789:role/DeveloperRole

Permissions:
  ✓ bedrock:InvokeModel           (needed for Bedrock calls)
  ✓ logs:*                         (needed for CloudWatch logs)
  ✓ cloudwatch:*                  (needed for metrics)
  ✓ iam:List*                     (read-only IAM)
  ✓ lambda:GetFunctionConfiguration (read-only Lambda)
  ✗ iam:AttachUserPolicy          (DENIED by IAM role)
  ✗ ec2:TerminateInstances        (DENIED by IAM role)

If user tries to run dangerous command (e.g., delete S3 bucket):
  1. CLI asks for confirmation: "Confirm delete? (y/n)"
  2. User confirms
  3. CLI executes: aws s3 rm s3://bucket
  4. AWS IAM policy BLOCKS if user doesn't have s3:DeleteBucket
  5. AWS returns: "User is not authorized to perform: s3:DeleteBucket"
```

**No additional command whitelist needed** — AWS IAM is the gatekeeper.

### Full Authentication Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ User runs: dev-cli chat                                         │
└──────────────────────┬──────────────────────────────────────────┘
                       │
       ┌───────────────▼──────────────┐
       │ Load JWT from ~/.dev-cli/config
       ├──────────────────────────────┤
       │ Exists? Valid? Expired?       │
       └───────────────┬──────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
     Exists      Expired        Missing
    & Valid    (< 1h left)       (First use)
        │              │              │
        ▼              ▼              ▼
     Continue    Refresh Token  dev-cli login
        │        (auto or ask)    │
        │              │          │
        │              ▼          ▼
        │           Valid?     Browser Opens
        │              │       Okta Login Page
        │              │          │
        └──────────────┴──────────┼──────────┐
                                  │          │
                          User enters       User
                          credentials      declines
                          & MFA             │
                                  │         │
                                  ▼         ▼
                            Okta validates  CLI stops
                                  │
                                  ▼
                        Okta redirects to:
                    localhost:8888/callback
                    ?code=...&state=...
                                  │
                                  ▼
                    CLI callback handler
                    exchanges code for JWT
                                  │
                                  ▼
                    CLI validates JWT locally
                    (check signature, expiry)
                                  │
                                  ▼
                    CLI stores encrypted token
                    in ~/.dev-cli/config
                                  │
                                  ▼
                    ┌─────────────────────────┐
                    │ Dev-CLI chat ready! ✅  │
                    └─────────────────────────┘
                                  │
                                  ▼
                    ┌─────────────────────────────────┐
                    │ Making API calls to backend:    │
                    │ ├─ Check Okta group membership │
                    │ ├─ Validate JWT signature      │
                    │ ├─ Check rate limits           │
                    │ └─ Log to CloudWatch           │
                    └─────────────────────────────────┘
```

### Token Refresh Logic

```python
async def get_valid_token():
    """Get valid token, refresh if needed (automatic)"""
    token_data = token_store.load_token()
    
    if not token_data:
        # No token, trigger login
        await initiate_login()
        return await get_valid_token()
    
    expires_at = token_data["expires_at"]
    now = datetime.now()
    time_remaining = expires_at - now
    
    # If < 1 hour remaining, refresh automatically
    if time_remaining < timedelta(hours=1):
        try:
            new_token = await refresh_token(token_data["refresh_token"])
            token_store.save_token(new_token)
            return new_token["access_token"]
        except RefreshError:
            # Refresh failed, trigger login
            await initiate_login()
            return await get_valid_token()
    
    # If already expired, trigger login
    if expires_at < now:
        await initiate_login()
        return await get_valid_token()
    
    return token_data["access_token"]
```

#### Step 1: Trigger Login

```bash
$ dev-cli login

CLI Output:
Opening Okta login in browser...
Waiting for callback on http://localhost:8888/callback
Press Ctrl+C to cancel
```

#### Step 2: Start Callback Server

```python
# src/auth/callback_handler.py
app = FastAPI()
callback_url = "http://localhost:8888/callback"

@app.get("/callback")
async def callback(code: str, state: str):
    # Receive auth code from Okta
    # Validate state for CSRF protection
    # Exchange code for JWT
    # Return HTML: "You can close this window"
```

#### Step 3: Exchange Code for JWT (PKCE)

```python
# src/auth/okta.py
async def exchange_code_for_token(code: str):
    """Exchange Okta auth code for JWT"""
    
    token_endpoint = f"{okta_domain}/oauth2/v1/token"
    
    response = httpx.post(
        token_endpoint,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://localhost:8888/callback",
            "client_id": config.OKTA_CLIENT_ID,
            "client_secret": config.OKTA_CLIENT_SECRET,
            "code_verifier": stored_code_verifier  # PKCE
        }
    )
    
    token_response = response.json()
    access_token = token_response["access_token"]
    id_token = token_response["id_token"]
    expires_in = token_response["expires_in"]  # Usually 3600s (1h)
    
    return {
        "access_token": access_token,
        "id_token": id_token,
        "expires_at": datetime.now() + timedelta(seconds=expires_in)
    }
```

#### Step 4: Validate JWT Locally

```python
# src/auth/jwt_validator.py
from cryptography.hazmat.primitives import serialization
from jose import jwt, JWTError

class JWTValidator:
    def __init__(self, okta_domain: str):
        self.okta_domain = okta_domain
        self.jwk_cache = {}
        self.jwk_cache_ttl = 3600  # 1 hour
    
    async def get_jwk_keys(self):
        """Fetch and cache Okta JWK keys"""
        if self._is_cache_valid():
            return self.jwk_cache
        
        response = httpx.get(
            f"{self.okta_domain}/oauth2/v1/keys"
        )
        self.jwk_cache = response.json()
        self.jwk_cache_time = time.time()
        return self.jwk_cache
    
    async def validate_token(self, token: str):
        """Validate JWT signature and expiry"""
        try:
            # Decode without verification first (to get kid)
            unverified = jwt.get_unverified_header(token)
            kid = unverified["kid"]
            
            # Get JWK keys
            keys = await self.get_jwk_keys()
            key = self._find_key_by_kid(keys, kid)
            
            # Convert JWK to PEM format
            public_key = jwk_to_pem(key)
            
            # Verify signature
            payload = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                audience="your-app-id"
            )
            
            # Check expiry
            if payload["exp"] < time.time():
                raise JWTError("Token expired")
            
            return payload
        except JWTError as e:
            raise JWTError(f"Invalid token: {e}")
```

#### Step 5: Store Token Securely

```python
# src/auth/token_store.py
import json
from cryptography.fernet import Fernet

class SecureTokenStore:
    def __init__(self, config_path: str = "~/.dev-cli/config"):
        self.config_path = Path(config_path).expanduser()
        self.encryption_key = self._get_or_create_key()
    
    def save_token(self, token_data: dict):
        """Save token encrypted to ~/.dev-cli/config"""
        config = self._load_config()
        config["auth"] = {
            "access_token": self._encrypt(token_data["access_token"]),
            "token_expires_at": token_data["expires_at"].isoformat(),
            "refresh_token": self._encrypt(token_data.get("refresh_token", "")),
            "refresh_expires_at": token_data.get("refresh_expires_at")
        }
        self._save_config(config)
    
    def load_token(self) -> dict | None:
        """Load and decrypt token"""
        config = self._load_config()
        if "auth" not in config:
            return None
        
        auth = config["auth"]
        return {
            "access_token": self._decrypt(auth["access_token"]),
            "expires_at": datetime.fromisoformat(auth["token_expires_at"]),
            "refresh_token": self._decrypt(auth.get("refresh_token", ""))
        }
    
    def _encrypt(self, plaintext: str) -> str:
        """Encrypt string"""
        cipher = Fernet(self.encryption_key)
        return cipher.encrypt(plaintext.encode()).decode()
    
    def _decrypt(self, ciphertext: str) -> str:
        """Decrypt string"""
        cipher = Fernet(self.encryption_key)
        return cipher.decrypt(ciphertext.encode()).decode()
```

### Full Login Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ User runs: dev-cli login                                    │
└─────────────────────────────────┬───────────────────────────┘
                                  │
                ┌─────────────────▼─────────────────┐
                │ 1. CLI starts callback server      │
                │    on localhost:8888              │
                └─────────────────┬─────────────────┘
                                  │
                ┌─────────────────▼─────────────────┐
                │ 2. Generate PKCE code_verifier    │
                │    and code_challenge             │
                └─────────────────┬─────────────────┘
                                  │
                ┌─────────────────▼─────────────────┐
                │ 3. Open browser to Okta login:    │
                │    /oauth2/v1/authorize           │
                │    ?client_id=...                 │
                │    &code_challenge=...            │
                │    &redirect_uri=localhost:8888   │
                └─────────────────┬─────────────────┘
                                  │
                ┌─────────────────▼─────────────────┐
                │ 4. User logs into Okta            │
                │    (browser)                      │
                └─────────────────┬─────────────────┘
                                  │
                ┌─────────────────▼─────────────────┐
                │ 5. Okta redirects to:             │
                │    localhost:8888/callback?       │
                │    code=...&state=...             │
                └─────────────────┬─────────────────┘
                                  │
                ┌─────────────────▼─────────────────┐
                │ 6. CLI callback handler           │
                │    receives auth code             │
                └─────────────────┬─────────────────┘
                                  │
                ┌─────────────────▼─────────────────┐
                │ 7. CLI exchanges code for JWT     │
                │    POST /oauth2/v1/token          │
                │    code_verifier=...              │
                └─────────────────┬─────────────────┘
                                  │
                ┌─────────────────▼─────────────────┐
                │ 8. Okta returns JWT               │
                │    (ID token + access token)      │
                └─────────────────┬─────────────────┘
                                  │
                ┌─────────────────▼─────────────────┐
                │ 9. CLI validates JWT locally      │
                │    using cached Okta JWK keys     │
                └─────────────────┬─────────────────┘
                                  │
                ┌─────────────────▼─────────────────┐
                │ 10. CLI stores token encrypted    │
                │    in ~/.dev-cli/config           │
                └─────────────────┬─────────────────┘
                                  │
                ┌─────────────────▼─────────────────┐
                │ 11. Browser shows:                │
                │    "You can close this window"    │
                └─────────────────┬─────────────────┘
                                  │
                ┌─────────────────▼─────────────────┐
                │ 12. CLI displays:                 │
                │    ✓ Authenticated successfully   │
                │    Session valid until: ...       │
                └─────────────────────────────────────┘
```

### Token Refresh Logic

```python
# In cli/commands/chat.py or api_client/client.py

async def get_valid_token():
    """Get valid token, refresh if needed"""
    token_data = token_store.load_token()
    
    if not token_data:
        # No token, trigger login
        await initiate_login()
        return await get_valid_token()
    
    expires_at = token_data["expires_at"]
    now = datetime.now()
    
    # If < 1 hour remaining, refresh
    if expires_at - now < timedelta(hours=1):
        token_data = await refresh_token(token_data["refresh_token"])
        token_store.save_token(token_data)
    
    # If already expired, trigger login
    if expires_at < now:
        await initiate_login()
        return await get_valid_token()
    
    return token_data["access_token"]
```

### Backend Token Validation

```python
# backend/src/auth/jwt_validator.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthCredential

security = HTTPBearer()
jwt_validator = JWTValidator(okta_domain=config.OKTA_DOMAIN)

async def verify_jwt(credentials: HTTPAuthCredential = Depends(security)):
    """FastAPI dependency for JWT validation"""
    token = credentials.credentials
    
    try:
        payload = await jwt_validator.validate_token(token)
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

# Usage in endpoints:
@router.post("/api/v1/chat")
async def chat(
    request: ChatRequest,
    user_payload = Depends(verify_jwt)
):
    user_id = user_payload["sub"]
    email = user_payload["email"]
    # Process request...
```

-----

## Backend API Specification

### Base URL

```
Production: https://api.dev-cli.example.com
Staging: https://staging-api.dev-cli.example.com
```

### Authentication

All requests require JWT in `Authorization` header:

```
Authorization: Bearer <JWT_TOKEN>
```

Backend validates JWT signature locally (no Okta call per request).

### Common Response Format

```json
{
  "success": true,
  "data": { /* ... */ },
  "error": null,
  "request_id": "req_abc123",
  "timestamp": "2025-03-20T14:30:00Z"
}
```

### Error Response Format

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Daily quota exceeded",
    "details": {
      "used": 100,
      "limit": 100,
      "resets_at": "2025-03-21T00:00:00Z"
    }
  },
  "request_id": "req_abc123"
}
```

### Endpoints

#### POST /api/v1/chat

Send a chat message and get response from Bedrock.

**Request:**

```json
{
  "project_path": "/Users/user/my-api",
  "message": "refactor this authentication module",
  "conversation_id": "conv_abc123",
  "context_config": {
    "include_project_manifest": true,
    "include_conversation_history": true,
    "max_history_messages": 10,
    "include_files": ["src/auth.py", "src/models.py"]
  }
}
```

**Response:**

```json
{
  "success": true,
  "data": {
    "message_id": "msg_def456",
    "conversation_id": "conv_abc123",
    "response": "I'll help you refactor the authentication module...",
    "tokens_used": 450,
    "model": "claude-3-sonnet",
    "streaming": false
  },
  "error": null,
  "request_id": "req_xyz789"
}
```

**Query Parameters:**

```
?stream=true     - Stream response (SSE format)
```

**Stream Response Format (text/event-stream):**

```
data: {"type": "token", "content": "I'll"}
data: {"type": "token", "content": " help"}
data: {"type": "usage", "tokens_used": 450}
data: {"type": "done"}
```

#### POST /api/v1/analyze

Analyze project structure (one-shot, no conversation).

**Request:**

```json
{
  "project_path": "/Users/user/my-api"
}
```

**Response:**

```json
{
  "success": true,
  "data": {
    "project_name": "my-api",
    "languages": ["python", "typescript"],
    "frameworks": ["fastapi", "react"],
    "databases": ["postgresql"],
    "key_insights": [
      "Monorepo with FastAPI backend and React frontend",
      "Uses SQLAlchemy ORM with 15 models",
      "3 API endpoints with 80% code coverage"
    ]
  },
  "error": null,
  "request_id": "req_abc123"
}
```

#### POST /api/v1/summarize

Generate a summary of conversation.

**Request:**

```json
{
  "conversation_id": "conv_abc123",
  "message_ids": ["msg_1", "msg_2", ...],
  "summary_type": "auto"
}
```

**Response:**

```json
{
  "success": true,
  "data": {
    "summary": "Discussed database optimization...",
    "key_topics": [
      "Query optimization",
      "Indexing strategy",
      "Performance tuning"
    ],
    "action_items": [
      {
        "description": "Add database index on user_id",
        "priority": "high",
        "completed": false
      }
    ]
  },
  "error": null,
  "request_id": "req_abc123"
}
```

#### GET /api/v1/usage

Get API usage and quota information.

**Request:**

```
GET /api/v1/usage
```

**Response:**

```json
{
  "success": true,
  "data": {
    "user_id": "user_abc123",
    "quota": {
      "daily_limit": 100,
      "used_today": 45,
      "remaining": 55,
      "reset_at": "2025-03-21T00:00:00Z"
    },
    "usage_history": [
      {
        "date": "2025-03-20",
        "requests": 45,
        "tokens_used": 12500
      },
      {
        "date": "2025-03-19",
        "requests": 78,
        "tokens_used": 22300
      }
    ]
  },
  "error": null,
  "request_id": "req_abc123"
}
```

#### POST /api/v1/health

Health check endpoint.

**Response:**

```json
{
  "status": "healthy",
  "timestamp": "2025-03-20T14:30:00Z",
  "bedrock_status": "operational",
  "uptime_seconds": 86400
}
```

-----

## Backend API Specification (Private API Gateway + VPC Endpoint)

### Infrastructure

```
Private API Gateway (VPC Endpoint)
    ↓
Lambda (Backend service)
    ├─ LLM Provider Factory
    ├─ Cost Calculator
    ├─ Rate Limiter
    └─ Audit Logger
    ↓
┌─────────────────────────────┐
│ AWS Services (shared)       │
├─────────────────────────────┤
│ DynamoDB (rate-limits)      │
│ CloudWatch Logs (audit)     │
│ Secrets Manager (API keys)  │
│ AWS Bedrock (day 1)         │
└─────────────────────────────┘
```

### API Endpoints

#### POST /api/v1/chat (Streaming)

**Purpose:** Stream LLM response with project context + AWS CLI data

**Request:**

```json
{
  "message": "Check CloudWatch logs for lambda errors",
  "aws_cli_output": "[Optional: output from aws logs tail ...]",
  "file_contents": {
    "handler.py": "[File content...]",
    "config.yaml": "[File content...]"
  },
  "project_manifest": {
    "languages": ["python", "typescript"],
    "frameworks": ["fastapi", "react"]
  },
  "conversation_history": [
    {
      "role": "user",
      "content": "Previous message"
    },
    {
      "role": "assistant",
      "content": "Previous response"
    }
  ]
}
```

**Headers:**

```
Authorization: Bearer <JWT_TOKEN>
Content-Type: application/json
```

**Response (Streaming - text/event-stream):**

```
data: {"type": "token", "content": "I'll"}
data: {"type": "token", "content": " help"}
data: {"type": "token", "content": " you"}
data: {"type": "usage", "input_tokens": 450, "output_tokens": 50, "total_tokens": 500}
data: {"type": "done"}
```

**Error Response (429 - Rate Limit):**

```json
{
  "success": false,
  "error": {
    "code": "QUOTA_EXCEEDED",
    "message": "Daily token quota exceeded",
    "details": {
      "tokens_used": 100000,
      "tokens_limit": 100000,
      "cost_usd": 10.00,
      "credit_limit": 10.00,
      "reset_at": "2025-03-21T00:00:00Z"
    }
  }
}
```

#### GET /api/v1/usage

**Purpose:** Get user’s current quota and usage stats

**Request:**

```
GET /api/v1/usage
Authorization: Bearer <JWT_TOKEN>
```

**Response:**

```json
{
  "success": true,
  "data": {
    "user_id": "okta_user_123",
    "quota": {
      "daily_token_limit": 100000,
      "tokens_used_today": 45000,
      "tokens_remaining": 55000,
      "daily_credit_limit": 10.00,
      "cost_usd_today": 0.135,
      "credits_remaining": 9.865,
      "reset_at": "2025-03-21T00:00:00Z"
    },
    "usage_history": [
      {
        "date": "2025-03-20",
        "requests": 12,
        "tokens_used": 45000,
        "cost_usd": 0.135,
        "providers_used": ["bedrock"]
      },
      {
        "date": "2025-03-19",
        "requests": 28,
        "tokens_used": 87000,
        "cost_usd": 0.261,
        "providers_used": ["bedrock"]
      }
    ]
  }
}
```

#### GET /api/v1/health

**Purpose:** Health check + provider status

**Response:**

```json
{
  "status": "healthy",
  "timestamp": "2025-03-20T14:30:00Z",
  "services": {
    "api": "operational",
    "dynamodb": "operational",
    "cloudwatch": "operational",
    "bedrock": "operational"
  },
  "primary_provider": "bedrock",
  "fallback_provider": null
}
```

### Backend Implementation Details

#### Authorization Middleware

```python
# backend/src/auth/middleware.py

async def verify_jwt_and_authorize(request: Request, call_next):
    """Middleware to verify JWT and check Okta group"""
    
    # Extract JWT from Authorization header
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse(
            status_code=401,
            content={"error": "Missing or invalid Authorization header"}
        )
    
    token = auth_header[7:]  # Remove "Bearer " prefix
    
    # Validate JWT locally (no Okta API call)
    jwt_validator = JWTValidator(okta_domain=config.OKTA_DOMAIN)
    
    try:
        payload = await jwt_validator.validate_token(token)
    except JWTError as e:
        return JSONResponse(
            status_code=401,
            content={"error": f"Invalid token: {str(e)}"}
        )
    
    # Check Okta group membership
    groups = payload.get("groups", [])
    if "dev-cli-users" not in groups:
        return JSONResponse(
            status_code=403,
            content={"error": "Not in dev-cli-users group"}
        )
    
    # Add user info to request state
    request.state.user_id = payload["sub"]
    request.state.email = payload["email"]
    request.state.groups = groups
    
    response = await call_next(request)
    return response
```

#### Complete Chat Endpoint Implementation

```python
# backend/src/routers/chat.py

@router.post("/api/v1/chat")
async def chat_endpoint(
    request: ChatRequest,
    request_obj: Request  # For accessing request.state.user_id, etc.
):
    """
    Main chat endpoint - routes through LLM provider abstraction
    with comprehensive error handling, rate limiting, and cost tracking
    """
    
    user_id = request_obj.state.user_id
    email = request_obj.state.email
    
    # 1. Check rate limits BEFORE calling LLM
    rate_limiter = RateLimiter(dynamodb_table)
    quota_info = await rate_limiter.check_quota(user_id)
    
    if quota_info["tokens_remaining"] <= 0:
        raise HTTPException(
            status_code=429,
            detail="Daily token quota exceeded",
            headers={
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": quota_info["reset_at"]
            }
        )
    
    # 2. Build system + conversation prompts
    system_prompt = build_system_prompt(request.project_manifest)
    messages = build_messages_from_history(request.conversation_history, request.message)
    
    # 3. Get LLM provider (factory handles provider selection)
    try:
        provider = LLMProviderFactory.get_provider()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    # 4. Stream response from provider
    async def generate_response():
        """Generator function for SSE streaming"""
        
        input_token_count = 0
        output_token_count = 0
        completion_successful = False
        
        try:
            # Count input tokens
            input_token_count = count_tokens(system_prompt + str(messages))
            
            # Stream response tokens
            async for token in await provider.invoke(
                system_prompt=system_prompt,
                messages=messages,
                max_tokens=2048,
                temperature=0.7,
                stream=True
            ):
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                output_token_count += 1
            
            completion_successful = True
            
            # Calculate cost and update quota
            cost_usd = CostCalculator.calculate_cost(
                provider=provider.get_provider_name(),
                model=provider.get_model_id(),
                input_tokens=input_token_count,
                output_tokens=output_token_count
            )
            
            # Update rate limits in DynamoDB
            await rate_limiter.increment_usage(
                user_id=user_id,
                tokens_used=input_token_count + output_token_count,
                cost_usd=cost_usd
            )
            
            # Get updated quota
            updated_quota = await rate_limiter.check_quota(user_id)
            
            # Send usage stats
            yield f"data: {json.dumps({
                'type': 'usage',
                'input_tokens': input_token_count,
                'output_tokens': output_token_count,
                'total_tokens': input_token_count + output_token_count,
                'cost_usd': cost_usd,
                'tokens_remaining': updated_quota['tokens_remaining'],
                'credits_remaining': updated_quota['credits_remaining']
            })}\n\n"
            
            # Log to CloudWatch (success)
            await audit_logger.log({
                "event": "chat_completion_success",
                "user_id": user_id,
                "email": email,
                "provider": provider.get_provider_name(),
                "model": provider.get_model_id(),
                "input_tokens": input_token_count,
                "output_tokens": output_token_count,
                "cost_usd": cost_usd,
                "execution_time_ms": elapsed_ms,
                "timestamp": datetime.now().isoformat()
            })
            
            # Final completion signal
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        
        except Exception as e:
            # Log error
            await audit_logger.log({
                "event": "chat_completion_error",
                "user_id": user_id,
                "email": email,
                "error": str(e),
                "error_type": type(e).__name__,
                "timestamp": datetime.now().isoformat()
            })
            
            # Send error to client
            yield f"data: {json.dumps({
                'type': 'error',
                'message': str(e),
                'code': 'LLM_ERROR'
            })}\n\n"
    
    return StreamingResponse(generate_response(), media_type="text/event-stream")

@router.get("/api/v1/usage")
async def get_usage(request_obj: Request):
    """Get user's quota and usage stats"""
    
    user_id = request_obj.state.user_id
    
    rate_limiter = RateLimiter(dynamodb_table)
    quota = await rate_limiter.get_quota_details(user_id)
    usage_history = await rate_limiter.get_usage_history(user_id, days=7)
    
    return {
        "success": True,
        "data": {
            "user_id": user_id,
            "quota": quota,
            "usage_history": usage_history
        }
    }

@router.get("/api/v1/health")
async def health_check():
    """Health check endpoint"""
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "api": "operational",
            "dynamodb": await check_dynamodb(),
            "cloudwatch": "operational",
            "bedrock": await check_bedrock_availability()
        },
        "primary_provider": config.DEFAULT_LLM_PROVIDER,
        "available_providers": LLMProviderFactory.list_providers()
    }
```

### Terraform: Private API Gateway + Lambda

```hcl
# infrastructure/modules/api/main.tf

# Private API Gateway (VPC Endpoint)
resource "aws_apigatewayv2_api" "dev_cli_api" {
  name          = "dev-cli-api"
  protocol_type = "HTTP"
  
  # Private API - only accessible via VPC Endpoint
  api_key_selection_expression = "$request.header.x-api-key"
  
  cors_configuration {
    allow_origins     = ["*"]
    allow_methods     = ["POST", "GET", "OPTIONS"]
    allow_headers     = ["*"]
    expose_headers    = ["*"]
    max_age           = 300
  }
}

# VPC Endpoint for API Gateway
resource "aws_apigatewayv2_vpc_link" "dev_cli_vpce" {
  name           = "dev-cli-api-endpoint"
  security_group_ids = [aws_security_group.api_endpoint_sg.id]
  subnet_ids     = var.private_subnet_ids
}

# Lambda function for chat endpoint
resource "aws_lambda_function" "chat_handler" {
  filename         = "backend.zip"
  function_name    = "dev-cli-chat-handler"
  role            = aws_iam_role.lambda_role.arn
  handler         = "src.main.lambda_handler"
  runtime         = "python3.11"
  timeout         = 60
  memory_size     = 512
  
  environment {
    variables = {
      LLM_PROVIDER    = "bedrock"
      OKTA_DOMAIN     = var.okta_domain
      DYNAMODB_TABLE  = aws_dynamodb_table.rate_limits.name
    }
  }
  
  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [aws_security_group.lambda_sg.id]
  }
}

# DynamoDB table for rate limiting
resource "aws_dynamodb_table" "rate_limits" {
  name           = "dev-cli-rate-limits"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "user_id"
  range_key      = "date"
  
  attribute {
    name = "user_id"
    type = "S"
  }
  
  attribute {
    name = "date"
    type = "S"
  }
  
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "dev_cli_logs" {
  name              = "/aws/lambda/dev-cli"
  retention_in_days = 90
}

# IAM Role for Lambda
resource "aws_iam_role" "lambda_role" {
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

# IAM Policy: Bedrock access
resource "aws_iam_role_policy" "bedrock_policy" {
  role = aws_iam_role.lambda_role.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = "arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:foundation-model/anthropic.claude-3-*"
      }
    ]
  })
}

# IAM Policy: DynamoDB access
resource "aws_iam_role_policy" "dynamodb_policy" {
  role = aws_iam_role.lambda_role.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = aws_dynamodb_table.rate_limits.arn
      }
    ]
  })
}

# IAM Policy: CloudWatch Logs
resource "aws_iam_role_policy" "logs_policy" {
  role = aws_iam_role.lambda_role.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.dev_cli_logs.arn}:*"
      }
    ]
  })
}
```

**Default Quota:** 100 requests per user per day

**Granularity:** Per user, daily reset at midnight UTC

**Tracking:** DynamoDB table `dev-cli-rate-limits`

### DynamoDB Schema

```
Table: dev-cli-rate-limits

Partition Key: user_id (String)
Sort Key: date (String, format: YYYY-MM-DD)
TTL: expires_at (Number, Unix timestamp, 32 days)

Attributes:
  request_count: Number (default: 0)
  tokens_used: Number (default: 0)
  last_updated: String (ISO 8601)
  daily_limit: Number (configurable per user, default: 100)
  
Example Item:
{
  "user_id": "okta_user_123",
  "date": "2025-03-20",
  "request_count": 45,
  "tokens_used": 12500,
  "last_updated": "2025-03-20T14:30:00Z",
  "daily_limit": 100,
  "expires_at": 1745000000
}
```

### Rate Limit Middleware

```python
# backend/src/auth/rate_limiter.py
from fastapi import HTTPException, status

class RateLimiter:
    def __init__(self, dynamodb_client, table_name="dev-cli-rate-limits"):
        self.client = dynamodb_client
        self.table_name = table_name
    
    async def check_quota(self, user_id: str, daily_limit: int = 100):
        """Check if user has exceeded daily quota"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        response = self.client.get_item(
            TableName=self.table_name,
            Key={
                "user_id": {"S": user_id},
                "date": {"S": today}
            }
        )
        
        if "Item" not in response:
            # First request today
            self.client.put_item(
                TableName=self.table_name,
                Item={
                    "user_id": {"S": user_id},
                    "date": {"S": today},
                    "request_count": {"N": "1"},
                    "tokens_used": {"N": "0"},
                    "daily_limit": {"N": str(daily_limit)},
                    "expires_at": {"N": str(int(time.time()) + 32*86400)}
                }
            )
            return {"used": 1, "remaining": daily_limit - 1, "limit": daily_limit}
        
        item = response["Item"]
        count = int(item["request_count"]["N"])
        limit = int(item["daily_limit"]["N"])
        
        if count >= limit:
            # Quota exceeded
            reset_tomorrow = (datetime.now() + timedelta(days=1)).replace(
                hour=0, minute=0, second=0
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Daily quota exceeded",
                headers={
                    "X-Rate-Limit-Remaining": "0",
                    "X-Rate-Limit-Reset": int(reset_tomorrow.timestamp())
                }
            )
        
        # Increment counter
        self.client.update_item(
            TableName=self.table_name,
            Key={
                "user_id": {"S": user_id},
                "date": {"S": today}
            },
            UpdateExpression="SET request_count = request_count + :inc",
            ExpressionAttributeValues={":inc": {"N": "1"}}
        )
        
        return {
            "used": count + 1,
            "remaining": limit - (count + 1),
            "limit": limit
        }

# Usage in FastAPI middleware:
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/v1/"):
        user_payload = request.state.user  # From JWT validation
        quota = await rate_limiter.check_quota(user_payload["sub"])
        
        response = await call_next(request)
        
        response.headers["X-Rate-Limit-Limit"] = str(quota["limit"])
        response.headers["X-Rate-Limit-Used"] = str(quota["used"])
        response.headers["X-Rate-Limit-Remaining"] = str(quota["remaining"])
        
        return response
    
    return await call_next(request)
```

### Client-Side Quota Display

```bash
$ dev-cli status

API Quota (Today):
  Used: 45 / 100 requests (45%)
  Remaining: 55
  Resets: 2025-03-21 00:00:00 UTC
```

### Soft & Hard Limits

- **Soft Limit (80%):** CLI warns user
  
  ```
  ⚠️  Warning: You've used 80 of 100 requests today.
  Only 20 requests remaining.
  ```
- **Hard Limit (100%):** CLI blocks, shows reset time
  
  ```
  ❌ Error: Daily quota exceeded.
  Your limit resets at 2025-03-21 00:00:00 UTC.
  Contact support if you need to increase your limit.
  ```

-----

## Multi-Language Support

### Language Detection

#### Detection Algorithm

```python
# cli/src/detectors/detector.py

class ProjectDetector:
    """Auto-detect languages, frameworks, and project structure"""
    
    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.manifest = {
            "languages": [],
            "frameworks": [],
            "databases": [],
            "infrastructure": [],
            "structure": {}
        }
    
    async def detect(self) -> dict:
        """Scan project and build manifest"""
        await self._detect_languages()
        await self._detect_frameworks()
        await self._detect_databases()
        await self._detect_infrastructure()
        await self._detect_structure()
        return self.manifest
    
    async def _detect_languages(self):
        """Detect programming languages"""
        # Scan file extensions
        py_files = list(self.project_path.rglob("*.py"))
        ts_files = list(self.project_path.rglob("*.ts"))
        jsx_files = list(self.project_path.rglob("*.jsx"))
        tf_files = list(self.project_path.rglob("*.tf"))
        
        if py_files:
            self.manifest["languages"].append({
                "name": "Python",
                "file_count": len(py_files),
                "version": self._detect_python_version()
            })
        
        if ts_files or jsx_files:
            self.manifest["languages"].append({
                "name": "TypeScript/JavaScript",
                "file_count": len(ts_files) + len(jsx_files),
                "version": self._detect_node_version()
            })
        
        if tf_files:
            self.manifest["languages"].append({
                "name": "HCL (Terraform)",
                "file_count": len(tf_files)
            })
    
    async def _detect_frameworks(self):
        """Detect frameworks"""
        # Python
        if self._file_exists("requirements.txt"):
            reqs = self._parse_requirements()
            if "fastapi" in reqs:
                self.manifest["frameworks"].append("FastAPI")
            if "django" in reqs:
                self.manifest["frameworks"].append("Django")
            if "sqlalchemy" in reqs:
                self.manifest["frameworks"].append("SQLAlchemy")
        
        # JavaScript/TypeScript
        if self._file_exists("package.json"):
            pkg = self._parse_json("package.json")
            deps = pkg.get("dependencies", {})
            if "react" in deps:
                self.manifest["frameworks"].append("React")
            if "express" in deps:
                self.manifest["frameworks"].append("Express")
            if "next" in deps:
                self.manifest["frameworks"].append("Next.js")
```

### Framework-Specific Prompts

```python
# cli/src/prompts/python.py

PYTHON_SYSTEM_PROMPT = """
You are an expert Python developer and code assistant.

You have deep knowledge of:
- Python 3.11+ features (dataclasses, type hints, pattern matching)
- Popular frameworks: FastAPI, Django, Flask, SQLAlchemy
- Testing libraries: pytest, unittest, mock
- Code style: PEP 8, Black formatter, mypy type checking
- Popular packages: pandas, numpy, requests, pydantic
- Virtual environments and dependency management (pip, Poetry, uv)

When reviewing Python code:
1. Suggest type hints for better code clarity
2. Recommend using dataclasses or Pydantic models
3. Suggest async/await where appropriate
4. Recommend proper error handling with custom exceptions
5. Suggest comprehensive unit tests with pytest

When the user mentions refactoring, debugging, or testing, provide concrete code examples.
"""

# cli/src/prompts/terraform.py

TERRAFORM_SYSTEM_PROMPT = """
You are an expert in Infrastructure as Code (IaC) and Terraform.

You have deep knowledge of:
- Terraform 1.0+ syntax and best practices
- AWS, Azure, GCP provider configurations
- Modules, outputs, variables, locals
- State management and remote backends
- Testing Terraform with terratest
- Security best practices (taint, sensitive, vault integration)

When reviewing Terraform code:
1. Check for security issues (overly permissive IAM, exposed secrets)
2. Suggest using modules for reusability
3. Recommend variable validation and defaults
4. Suggest using count or for_each for loops
5. Recommend using DynamoDB for state locking

Provide HCL code examples and explain the reasoning.
"""

# When building prompt for Bedrock:
def build_system_prompt(project_manifest: dict, message: str) -> str:
    """Build system prompt based on detected languages"""
    
    languages = [lang["name"].lower() for lang in project_manifest.get("languages", [])]
    frameworks = [f.lower() for f in project_manifest.get("frameworks", [])]
    
    prompts = []
    
    if "python" in languages:
        prompts.append(PYTHON_SYSTEM_PROMPT)
    
    if "terraform" in languages:
        prompts.append(TERRAFORM_SYSTEM_PROMPT)
    
    if "typescript/javascript" in languages or "react" in frameworks:
        prompts.append(TYPESCRIPT_SYSTEM_PROMPT)
    
    if "postgresql" in [db["name"].lower() for db in project_manifest.get("databases", [])]:
        prompts.append(SQL_SYSTEM_PROMPT)
    
    # Combine prompts
    system_prompt = "\n\n".join(prompts)
    
    # Add context
    system_prompt += f"\n\nProject Context:\n{json.dumps(project_manifest, indent=2)}"
    
    return system_prompt
```

-----

## Agent Loop: Autonomous Tool-Driven Analysis

### Overview: Intelligent Agent Architecture

Instead of the CLI or backend doing dumb pattern matching, **the LLM drives tool usage autonomously**. The LLM:

- 🧠 Understands the user’s intent
- 🔍 Decides what information it needs
- 🛠️ Calls tools to gather data
- ✅ Stops when it has enough info to answer
- 🙋 Asks the user for clarification if needed

```
User: "Why is my Lambda timing out?"
         ↓
LLM thinks: "I need to understand:
  1. What does the Lambda do?
  2. What are the recent errors?
  3. What are the resource limits?
  4. What database queries are happening?"
         ↓
Agent Loop (Iterative):
  Iteration 1: scan_project_structure() → Get Lambda handler
  Iteration 2: read_file(handler.py) → Understand code
  Iteration 3: get_aws_logs() → See error patterns
  Iteration 4: get_lambda_config() → Check timeout/memory
  Iteration 5: get_db_schema() → Understand queries
  Iteration 6: [LLM has enough info]
         ↓
Final Answer: "The timeout is caused by N+1 queries. Fix by..."
```

### Agent Tool Definition Interface

```python
# backend/src/agent/tools/base.py

from abc import ABC, abstractmethod
from typing import Any, Optional
from enum import Enum

class ToolCategory(Enum):
    """Tool categories for grouping and prioritization"""
    FILE_SYSTEM = "file_system"
    CODE_ANALYSIS = "code_analysis"
    AWS = "aws"
    DATABASE = "database"
    INFRASTRUCTURE = "infrastructure"
    GIT = "git"
    BUILD = "build"
    USER_INPUT = "user_input"


class AgentTool(ABC):
    """Base class for all agent tools"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool name (e.g., 'read_file', 'get_aws_logs')"""
        pass
    
    @property
    @abstractmethod
    def category(self) -> ToolCategory:
        """Tool category"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """What this tool does (shown to LLM)"""
        pass
    
    @property
    @abstractmethod
    def parameters(self) -> dict:
        """JSON schema for parameters"""
        pass
    
    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """Execute tool, return result as string"""
        pass


class AgentToolRegistry:
    """Registry of all available tools"""
    
    def __init__(self):
        self.tools: dict[str, AgentTool] = {}
    
    def register(self, tool: AgentTool):
        """Register a tool"""
        self.tools[tool.name] = tool
    
    def get(self, name: str) -> Optional[AgentTool]:
        """Get tool by name"""
        return self.tools.get(name)
    
    def list_tools(self) -> list[AgentTool]:
        """Get all tools"""
        return list(self.tools.values())
    
    def get_tools_schema(self) -> list[dict]:
        """Get tools in Claude format"""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": {
                    "type": "object",
                    "properties": tool.parameters.get("properties", {}),
                    "required": tool.parameters.get("required", [])
                }
            }
            for tool in self.tools.values()
        ]
```

### Comprehensive Tool Set

#### 1. File System & Project Structure Tools

```python
# backend/src/agent/tools/file_system.py

class ScanProjectStructureTool(AgentTool):
    """Scan and cache project structure"""
    
    @property
    def name(self) -> str:
        return "scan_project_structure"
    
    @property
    def category(self) -> ToolCategory:
        return ToolCategory.FILE_SYSTEM
    
    @property
    def description(self) -> str:
        return """Scan project directory structure and file listing.
                 Returns folder tree, file counts, and detected file types.
                 Results are cached locally in .dev-cli/project_structure.json"""
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "max_depth": {
                    "type": "integer",
                    "description": "Max folder depth to scan (default: 3)"
                },
                "exclude_patterns": {
                    "type": "array",
                    "description": "Patterns to exclude (e.g., ['.git', 'node_modules', '__pycache__'])"
                }
            }
        }
    
    async def execute(self, max_depth: int = 3, exclude_patterns: list = None) -> str:
        """
        Scan project structure intelligently
        
        Returns:
        {
          "folders": {
            "src": {
              "python_files": 15,
              "test_files": 5,
              "subfolders": ["models", "handlers", "utils"]
            },
            "tests": {
              "python_files": 20,
              "subfolders": ["unit", "integration"]
            }
          },
          "root_files": ["main.py", "requirements.txt", "setup.py"],
          "detected_languages": ["python", "sql"],
          "cache_file": ".dev-cli/project_structure.json"
        }
        """
        
        # Check if cached (use cached structure, don't re-scan)
        cache_file = Path(self.project_path) / ".dev-cli" / "project_structure.json"
        if cache_file.exists():
            # Use cached structure
            with open(cache_file) as f:
                cached = json.load(f)
            return json.dumps({
                **cached,
                "source": "cache",
                "age_seconds": (time.time() - cached.get("cached_at", 0))
            })
        
        # Scan project
        structure = self._build_structure_tree(self.project_path, max_depth, exclude_patterns)
        
        # Cache result
        cache_file.parent.mkdir(exist_ok=True)
        with open(cache_file, "w") as f:
            json.dump({**structure, "cached_at": time.time()}, f, indent=2)
        
        return json.dumps(structure)
    
    def _build_structure_tree(self, path: Path, depth: int, exclude: list) -> dict:
        """Recursively build folder structure"""
        if depth == 0:
            return {}
        
        structure = {"root_files": [], "folders": {}}
        
        try:
            for item in sorted(path.iterdir()):
                # Skip excluded patterns
                if exclude and any(exc in item.name for exc in exclude):
                    continue
                if item.name.startswith("."):
                    continue
                
                if item.is_dir():
                    structure["folders"][item.name] = self._build_structure_tree(
                        item, depth - 1, exclude
                    )
                else:
                    structure["root_files"].append({
                        "name": item.name,
                        "size": item.stat().st_size,
                        "type": item.suffix
                    })
        except PermissionError:
            pass
        
        return structure


class ReadFileTool(AgentTool):
    """Smart file reading with section extraction"""
    
    @property
    def name(self) -> str:
        return "read_file"
    
    @property
    def description(self) -> str:
        return """Read file contents intelligently.
                 Can read entire file or specific line ranges.
                 For large files, returns summary unless specific lines requested."""
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to file (relative to project root)"
                },
                "line_start": {
                    "type": "integer",
                    "description": "Start line (1-indexed, optional)"
                },
                "line_end": {
                    "type": "integer",
                    "description": "End line (inclusive, optional)"
                },
                "max_lines": {
                    "type": "integer",
                    "description": "Max lines to return (default: 100)"
                }
            },
            "required": ["file_path"]
        }
    
    async def execute(
        self,
        file_path: str,
        line_start: int = None,
        line_end: int = None,
        max_lines: int = 100
    ) -> str:
        """Read file with intelligent truncation"""
        
        full_path = Path(self.project_path) / file_path
        
        if not full_path.exists():
            return f"[Error: File not found: {file_path}]"
        
        if full_path.stat().st_size > 1_000_000:
            return f"[Error: File too large ({full_path.stat().st_size / 1024 / 1024:.1f}MB). Specify line range or use analyze_file_summary.]"
        
        try:
            with open(full_path, "r") as f:
                all_lines = f.readlines()
            
            # Determine which lines to read
            if line_start and line_end:
                # Specific range requested
                lines = all_lines[line_start - 1:line_end]
            else:
                # Return up to max_lines
                lines = all_lines[:max_lines]
                if len(all_lines) > max_lines:
                    lines.append(f"\n... [{len(all_lines) - max_lines} more lines] ...\n")
            
            return "".join(lines)
        
        except Exception as e:
            return f"[Error reading file: {str(e)}]"


class AnalyzeFileStructureTool(AgentTool):
    """Get file summary without reading entire content"""
    
    @property
    def name(self) -> str:
        return "analyze_file_structure"
    
    @property
    def description(self) -> str:
        return """Analyze file structure (functions, classes, imports) without reading full content.
                 Returns summary: imports, functions, classes, line count.
                 Useful for understanding large files before reading specific sections."""
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to file to analyze"
                }
            },
            "required": ["file_path"]
        }
    
    async def execute(self, file_path: str) -> str:
        """Analyze file structure using AST"""
        
        full_path = Path(self.project_path) / file_path
        
        if file_path.endswith(".py"):
            return await self._analyze_python(full_path)
        elif file_path.endswith((".js", ".ts", ".jsx", ".tsx")):
            return await self._analyze_javascript(full_path)
        elif file_path.endswith(".go"):
            return await self._analyze_go(full_path)
        else:
            return f"[File type not analyzed: {file_path}. Use read_file instead.]"
    
    async def _analyze_python(self, path: Path) -> str:
        """Analyze Python file using AST"""
        import ast
        
        try:
            with open(path, "r") as f:
                tree = ast.parse(f.read())
            
            imports = [node.names[0].name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
            
            functions = []
            classes = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    functions.append({
                        "name": node.name,
                        "line": node.lineno,
                        "args": [arg.arg for arg in node.args.args]
                    })
                elif isinstance(node, ast.ClassDef):
                    classes.append({
                        "name": node.name,
                        "line": node.lineno,
                        "methods": [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                    })
            
            return json.dumps({
                "file": str(path),
                "language": "python",
                "imports": imports[:20],
                "functions": functions,
                "classes": classes,
                "total_lines": len(open(path).readlines())
            }, indent=2)
        except Exception as e:
            return f"[Error analyzing Python file: {str(e)}]"


class SearchCodebaseTool(AgentTool):
    """Search for files or patterns in codebase"""
    
    @property
    def name(self) -> str:
        return "search_codebase"
    
    @property
    def description(self) -> str:
        return """Search for files by name or pattern in codebase.
                 Returns matching files with context.
                 Useful for finding handlers, models, tests, etc."""
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term (filename or pattern)"
                },
                "file_type": {
                    "type": "string",
                    "description": "Filter by extension (e.g., '.py', '.js')"
                }
            },
            "required": ["query"]
        }
    
    async def execute(self, query: str, file_type: str = None) -> str:
        """Search codebase for files/patterns"""
        results = []
        
        for root, dirs, files in os.walk(self.project_path):
            # Skip vendor/cache dirs
            dirs[:] = [d for d in dirs if d not in [".git", "node_modules", "__pycache__", ".venv", "venv"]]
            
            for file in files:
                if file_type and not file.endswith(file_type):
                    continue
                
                if query.lower() in file.lower():
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, self.project_path)
                    results.append(rel_path)
        
        return json.dumps({
            "query": query,
            "matches": results[:30],  # Limit to 30
            "total_matches": len(results)
        }, indent=2)
```

#### 2. Code Analysis Tools

```python
# backend/src/agent/tools/code_analysis.py

class GetFunctionSignatureTool(AgentTool):
    """Get function/method signature and docstring"""
    
    @property
    def name(self) -> str:
        return "get_function_signature"
    
    @property
    def description(self) -> str:
        return """Get function signature and docstring without reading entire file.
                 Useful for understanding API/method before diving into implementation."""
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to file containing function"
                },
                "function_name": {
                    "type": "string",
                    "description": "Function/method name to retrieve"
                }
            },
            "required": ["file_path", "function_name"]
        }
    
    async def execute(self, file_path: str, function_name: str) -> str:
        """Get function signature"""
        
        full_path = Path(self.project_path) / file_path
        
        if file_path.endswith(".py"):
            import ast
            try:
                with open(full_path, "r") as f:
                    tree = ast.parse(f.read())
                
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) and node.name == function_name:
                        sig = f"def {node.name}({', '.join([arg.arg for arg in node.args.args])})"
                        docstring = ast.get_docstring(node) or "[No docstring]"
                        return f"{sig}\n\n{docstring}"
            except Exception as e:
                return f"[Error: {str(e)}]"
        
        return "[Function signature extraction not supported for this language]"


class FindDependenciesTool(AgentTool):
    """Extract and analyze project dependencies"""
    
    @property
    def name(self) -> str:
        return "find_dependencies"
    
    @property
    def description(self) -> str:
        return """Extract project dependencies from package files.
                 Supports: requirements.txt, package.json, go.mod, Cargo.toml, etc.
                 Returns versions and analyzes for outdated/security issues."""
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "language": {
                    "type": "string",
                    "description": "Language filter (python, javascript, go, rust, etc.)"
                }
            }
        }
    
    async def execute(self, language: str = None) -> str:
        """Find and parse dependency files"""
        
        dep_files = {
            "python": ["requirements.txt", "setup.py", "pyproject.toml", "Pipfile"],
            "javascript": ["package.json", "yarn.lock", "pnpm-lock.yaml"],
            "go": ["go.mod"],
            "rust": ["Cargo.toml"],
            "java": ["pom.xml", "build.gradle"]
        }
        
        # Scan for dependency files
        found_deps = {}
        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in [".git", "node_modules", "venv"]]
            
            for file in files:
                for lang, patterns in dep_files.items():
                    if language and lang != language:
                        continue
                    
                    if file in patterns:
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, self.project_path)
                        found_deps[rel_path] = self._parse_deps(full_path, lang)
        
        return json.dumps(found_deps, indent=2)
    
    def _parse_deps(self, path: str, lang: str) -> dict:
        """Parse dependency file by language"""
        # Simplified parsing
        try:
            if lang == "python" and path.endswith("requirements.txt"):
                with open(path) as f:
                    return {"type": "python", "packages": [line.strip() for line in f if line.strip()]}
            # Add more parsers as needed
        except:
            pass
        
        return {"type": lang, "status": "parse_error"}
```

#### 3. AWS Tools

```python
# backend/src/agent/tools/aws.py

class ExecuteAwsCliTool(AgentTool):
    """Execute AWS CLI commands safely"""
    
    @property
    def name(self) -> str:
        return "execute_aws_cli"
    
    @property
    def category(self) -> ToolCategory:
        return ToolCategory.AWS
    
    @property
    def description(self) -> str:
        return """Execute AWS CLI commands (read-only operations only).
                 Can retrieve logs, configurations, metrics, resource info.
                 Dangerous operations (delete, modify) are blocked."""
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "AWS CLI command (e.g., 'logs tail /aws/lambda/my-func')"
                },
                "profile": {
                    "type": "string",
                    "description": "AWS profile (default: from CLI context)"
                }
            },
            "required": ["command"]
        }
    
    async def execute(self, command: str, profile: str = None) -> str:
        """Execute AWS CLI with safety checks"""
        
        # Safety: Block dangerous commands
        dangerous = ["delete", "remove", "terminate", "drop", "destroy", "detach"]
        if any(d in command.lower() for d in dangerous):
            return "[BLOCKED: Destructive AWS commands must be confirmed by user. Use ask_user tool.]"
        
        profile = profile or self.aws_profile
        
        try:
            result = subprocess.run(
                f"aws {command} --profile {profile}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.stdout if result.returncode == 0 else f"[AWS Error]: {result.stderr}"
        except subprocess.TimeoutExpired:
            return "[Error: AWS CLI command timeout (30s)]"
        except Exception as e:
            return f"[Error: {str(e)}]"


class GetAwsResourceConfigTool(AgentTool):
    """Get AWS resource configuration"""
    
    @property
    def name(self) -> str:
        return "get_aws_resource_config"
    
    @property
    def description(self) -> str:
        return """Get configuration of AWS resources (Lambda, RDS, DynamoDB, etc.).
                 Returns: environment variables, timeout, memory, database config, etc."""
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "AWS service (lambda, rds, dynamodb, s3, etc.)"
                },
                "resource_name": {
                    "type": "string",
                    "description": "Resource name or ID"
                }
            },
            "required": ["service", "resource_name"]
        }
    
    async def execute(self, service: str, resource_name: str) -> str:
        """Get AWS resource configuration"""
        
        commands = {
            "lambda": f"lambda get-function-configuration --function-name {resource_name}",
            "rds": f"rds describe-db-instances --db-instance-identifier {resource_name}",
            "dynamodb": f"dynamodb describe-table --table-name {resource_name}",
            "s3": f"s3api head-bucket --bucket {resource_name}",
            "ec2": f"ec2 describe-instances --instance-ids {resource_name}"
        }
        
        if service not in commands:
            return f"[Error: Service not supported: {service}]"
        
        return await ExecuteAwsCliTool(self.aws_profile).execute(commands[service])


class GetAwsLogsTool(AgentTool):
    """Get CloudWatch logs for debugging"""
    
    @property
    def name(self) -> str:
        return "get_aws_logs"
    
    @property
    def description(self) -> str:
        return """Get CloudWatch logs from Lambda, ECS, or other AWS services.
                 Returns recent error/warning messages for debugging."""
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "log_group": {
                    "type": "string",
                    "description": "Log group name (e.g., '/aws/lambda/my-func')"
                },
                "filter": {
                    "type": "string",
                    "description": "Log filter pattern (e.g., 'ERROR', 'timeout')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of log lines to return (default: 50)"
                }
            },
            "required": ["log_group"]
        }
    
    async def execute(self, log_group: str, filter: str = None, limit: int = 50) -> str:
        """Get CloudWatch logs"""
        
        cmd = f"logs tail {log_group} --max-items {limit}"
        if filter:
            cmd += f" --filter-pattern '{filter}'"
        
        return await ExecuteAwsCliTool(self.aws_profile).execute(cmd)
```

#### 4. Database Tools

```python
# backend/src/agent/tools/database.py

class GetDbSchemaTool(AgentTool):
    """Get database schema and structure"""
    
    @property
    def name(self) -> str:
        return "get_db_schema"
    
    @property
    def category(self) -> ToolCategory:
        return ToolCategory.DATABASE
    
    @property
    def description(self) -> str:
        return """Get database schema (tables, columns, relationships).
                 Supports: PostgreSQL, MySQL, SQLite, MongoDB, DynamoDB.
                 Returns: table/collection structure without data."""
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "db_type": {
                    "type": "string",
                    "description": "Database type (postgres, mysql, sqlite, mongodb, dynamodb)"
                },
                "connection_string": {
                    "type": "string",
                    "description": "Database connection string (optional if in env)"
                },
                "tables": {
                    "type": "array",
                    "description": "Specific tables to get schema for (optional)"
                }
            },
            "required": ["db_type"]
        }
    
    async def execute(
        self,
        db_type: str,
        connection_string: str = None,
        tables: list = None
    ) -> str:
        """Get database schema"""
        
        # Get connection string from env if not provided
        connection_string = connection_string or await self._get_connection_from_env(db_type)
        
        try:
            if db_type == "postgres":
                return await self._get_postgres_schema(connection_string, tables)
            elif db_type == "sqlite":
                return await self._get_sqlite_schema(connection_string, tables)
            elif db_type == "mongodb":
                return await self._get_mongodb_schema(connection_string, tables)
            else:
                return f"[Database type not yet supported: {db_type}]"
        except Exception as e:
            return f"[Error getting schema: {str(e)}]"
    
    async def _get_postgres_schema(self, conn_str: str, tables: list) -> str:
        """Get PostgreSQL schema"""
        # Implementation would use psycopg2 or sqlalchemy
        # Return JSON schema of tables, columns, types, constraints
        pass


class AnalyzeQueryTool(AgentTool):
    """Analyze SQL query efficiency"""
    
    @property
    def name(self) -> str:
        return "analyze_query"
    
    @property
    def description(self) -> str:
        return """Analyze SQL query for performance issues.
                 Can detect: N+1 queries, missing indexes, inefficient joins.
                 Requires: connection to database."""
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "SQL query to analyze"
                },
                "db_type": {
                    "type": "string",
                    "description": "Database type (postgres, mysql, etc.)"
                }
            },
            "required": ["query"]
        }
    
    async def execute(self, query: str, db_type: str = "postgres") -> str:
        """Analyze query execution plan"""
        # Would execute EXPLAIN ANALYZE and return results
        pass
```

#### 5. Terraform/Infrastructure Tools

```python
# backend/src/agent/tools/infrastructure.py

class AnalyzeTerraformTool(AgentTool):
    """Analyze Terraform files"""
    
    @property
    def name(self) -> str:
        return "analyze_terraform"
    
    @property
    def category(self) -> ToolCategory:
        return ToolCategory.INFRASTRUCTURE
    
    @property
    def description(self) -> str:
        return """Parse and analyze Terraform files (.tf).
                 Returns: resources, variables, outputs, data sources.
                 Can identify: missing variables, resource dependencies."""
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to .tf file"
                }
            },
            "required": ["file_path"]
        }
    
    async def execute(self, file_path: str) -> str:
        """Analyze Terraform file"""
        
        full_path = Path(self.project_path) / file_path
        
        # Simple HCL parsing (real implementation would use hcl2 library)
        try:
            with open(full_path, "r") as f:
                content = f.read()
            
            # Extract resources, variables, outputs
            resources = self._extract_resources(content)
            variables = self._extract_variables(content)
            outputs = self._extract_outputs(content)
            
            return json.dumps({
                "file": file_path,
                "resources": resources,
                "variables": variables,
                "outputs": outputs
            }, indent=2)
        except Exception as e:
            return f"[Error analyzing Terraform: {str(e)}]"
    
    def _extract_resources(self, hcl: str) -> list:
        """Extract resource definitions"""
        import re
        pattern = r'resource\s+"([^"]+)"\s+"([^"]+)"'
        matches = re.findall(pattern, hcl)
        return [{"type": m[0], "name": m[1]} for m in matches]
```

#### 6. User Interaction Tool (Critical)

```python
# backend/src/agent/tools/user_interaction.py

class AskUserTool(AgentTool):
    """Ask user for input/clarification (blocks until response)"""
    
    @property
    def name(self) -> str:
        return "ask_user"
    
    @property
    def category(self) -> ToolCategory:
        return ToolCategory.USER_INPUT
    
    @property
    def description(self) -> str:
        return """Ask the user a question and wait for response.
                 Use when: need clarification, need user confirmation, or ambiguous intent.
                 Example: 'Which Lambda function are you asking about?'
                 Returns user's answer as string."""
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Question to ask user"
                },
                "options": {
                    "type": "array",
                    "description": "Optional: Multiple choice options (e.g., ['option1', 'option2'])"
                }
            },
            "required": ["question"]
        }
    
    async def execute(self, question: str, options: list = None) -> str:
        """Ask user and wait for response"""
        
        # Send question to CLI via WebSocket/SSE
        await self.send_to_cli({
            "type": "ask_user",
            "question": question,
            "options": options
        })
        
        # Wait for user response (blocking)
        # Implementation depends on communication channel (WebSocket, polling, etc.)
        response = await self.wait_for_user_response(timeout=300)  # 5 min timeout
        
        if response is None:
            return "[User did not respond within timeout]"
        
        return response
```

### Agent Loop Orchestrator with Status Streaming

```python
# backend/src/agent/orchestrator.py

class AgentOrchestrator:
    """Main agent orchestrator with agentic loop"""
    
    def __init__(
        self,
        provider: LLMProvider,
        tool_registry: AgentToolRegistry,
        max_iterations: int = 10,
        stream_callback = None  # Function to send status updates to CLI
    ):
        self.provider = provider
        self.tools = tool_registry
        self.max_iterations = max_iterations
        self.stream_callback = stream_callback  # Send realtime status
        self.iteration_count = 0
    
    async def run_agent_loop(
        self,
        user_message: str,
        project_manifest: dict,
        system_prompt: str,
        conversation_history: list = None
    ) -> str:
        """
        Run agentic loop until:
        1. LLM returns final answer (no tool calls)
        2. Max iterations reached
        3. ask_user tool called (user must respond)
        
        Streams status back to CLI as it works.
        """
        
        self.iteration_count = 0
        messages = conversation_history or []
        
        # Enhance system prompt with tool descriptions + project context
        enhanced_system_prompt = self._build_enhanced_system_prompt(system_prompt, project_manifest)
        
        while self.iteration_count < self.max_iterations:
            self.iteration_count += 1
            
            # Stream status: "Thinking (iteration 1/10)..."
            await self._stream_status(f"🤔 Iteration {self.iteration_count}/{self.max_iterations}: Analyzing...")
            
            # Add user message if first iteration
            if self.iteration_count == 1:
                messages.append({
                    "role": "user",
                    "content": user_message
                })
            
            # Call LLM with tools available
            try:
                response = await self.provider.invoke_with_tools(
                    system_prompt=enhanced_system_prompt,
                    messages=messages,
                    tools=self.tools.get_tools_schema(),
                    max_tokens=4096
                )
            except Exception as e:
                await self._stream_status(f"❌ LLM Error: {str(e)}")
                return "[Error calling LLM. Please try again.]"
            
            # Parse response (could be text or tool_use)
            if response["type"] == "text":
                # LLM gave final answer
                await self._stream_status("✅ Analysis complete!")
                return response["content"]
            
            if response["type"] == "tool_use":
                tool_name = response["tool_name"]
                tool_input = response["tool_input"]
                
                # Stream status: "Using tool: read_file(handler.py)..."
                await self._stream_status(f"🔧 Using tool: {tool_name}({list(tool_input.keys())[0] if tool_input else ''}...)")
                
                # Execute tool
                if tool_name not in [t.name for t in self.tools.list_tools()]:
                    tool_result = f"[Error: Unknown tool: {tool_name}]"
                else:
                    try:
                        tool = self.tools.get(tool_name)
                        tool_result = await tool.execute(**tool_input)
                        
                        # Stream status: "Read 150 lines from handler.py"
                        result_preview = tool_result[:100].replace("\n", " ")
                        await self._stream_status(f"✓ {tool_name}: {result_preview}...")
                    except Exception as e:
                        tool_result = f"[Tool error: {str(e)}]"
                        await self._stream_status(f"⚠️  {tool_name} failed: {str(e)}")
                
                # Add assistant response + tool result to messages
                messages.append({
                    "role": "assistant",
                    "content": response["content"]  # LLM's thinking
                })
                
                messages.append({
                    "role": "user",
                    "content": f"[Tool {tool_name} returned]:\n{tool_result}"
                })
                
                # Check if ask_user was called (special handling)
                if tool_name == "ask_user":
                    await self._stream_status("❓ Waiting for user input...")
                    # ask_user blocks internally, so we continue with response
                    continue
        
        # Max iterations reached
        await self._stream_status("⚠️  Max iterations reached")
        return """I've reached the iteration limit while analyzing your project.
        I've gathered the following information but couldn't complete my analysis.
        
        Could you help me by:
        1. Providing more specific details about what you're asking
        2. Narrowing down the problem area
        3. Confirming which files/services are relevant
        
        What additional information would help me understand the issue better?"""
    
    def _build_enhanced_system_prompt(self, base_prompt: str, manifest: dict) -> str:
        """Build enhanced system prompt with tools + context"""
        
        tools_description = self._describe_available_tools()
        project_context = json.dumps(manifest, indent=2)
        
        return f"""{base_prompt}

AVAILABLE TOOLS
===============
{tools_description}

PROJECT CONTEXT
===============
{project_context}

INSTRUCTIONS
============
1. Start by scanning project structure to understand the codebase
2. Read files intelligently: analyze structure first, then read relevant sections
3. Use ask_user tool if you need clarification
4. Stop tool usage when you have enough info to answer
5. If stuck after multiple iterations, ask user for help
6. Be specific and actionable in your final answer"""
    
    def _describe_available_tools(self) -> str:
        """Generate tool descriptions for prompt"""
        descriptions = []
        for tool in self.tools.list_tools():
            descriptions.append(f"- {tool.name}: {tool.description}")
        return "\n".join(descriptions)
    
    async def _stream_status(self, message: str):
        """Stream status update to CLI"""
        if self.stream_callback:
            await self.stream_callback({
                "type": "status",
                "message": message
            })
```

### Streaming Status Updates Back to CLI

```python
# backend/src/routers/chat.py (UPDATED)

@router.post("/api/v1/chat")
async def chat_endpoint_with_agent(
    request: ChatRequest,
    request_obj: Request
):
    """Chat endpoint with agentic loop and status streaming"""
    
    user_id = request_obj.state.user_id
    
    # Check rate limits
    rate_limiter = RateLimiter(dynamodb_table)
    quota_info = await rate_limiter.check_quota(user_id)
    
    if quota_info["tokens_remaining"] <= 0:
        raise HTTPException(status_code=429, detail="Quota exceeded")
    
    # Get LLM provider
    provider = LLMProviderFactory.get_provider()
    
    # Create tool registry
    tool_registry = AgentToolRegistry()
    tool_registry.register(ScanProjectStructureTool(request.project_path))
    tool_registry.register(ReadFileTool(request.project_path))
    tool_registry.register(AnalyzeFileStructureTool(request.project_path))
    tool_registry.register(SearchCodebaseTool(request.project_path))
    tool_registry.register(ExecuteAwsCliTool(request.aws_profile))
    tool_registry.register(GetAwsResourceConfigTool(request.aws_profile))
    tool_registry.register(GetAwsLogsTool(request.aws_profile))
    tool_registry.register(GetDbSchemaTool())
    tool_registry.register(AnalyzeTerraformTool(request.project_path))
    tool_registry.register(AskUserTool())  # For user interaction
    # ... add more tools as needed
    
    # Define status callback
    async def send_status(status_obj):
        """Send status updates to client as SSE"""
        if status_obj["type"] == "status":
            yield f"data: {json.dumps({'type': 'status', 'message': status_obj['message']})}\n\n"
    
    # Create agent orchestrator
    system_prompt = build_system_prompt(request.project_manifest)
    agent = AgentOrchestrator(
        provider=provider,
        tool_registry=tool_registry,
        max_iterations=10,
        stream_callback=send_status
    )
    
    async def generate_response():
        """Main response generator"""
        
        try:
            # Run agent loop
            final_answer = await agent.run_agent_loop(
                user_message=request.message,
                project_manifest=request.project_manifest,
                system_prompt=system_prompt,
                conversation_history=request.conversation_history
            )
            
            # Stream final answer
            yield f"data: {json.dumps({'type': 'response', 'content': final_answer})}\n\n"
            
            # Update costs
            tokens_used = count_tokens(final_answer)
            cost = calculate_cost(provider.get_provider_name(), tokens_used)
            await rate_limiter.increment_usage(user_id, tokens_used, cost)
            
            # Log to CloudWatch
            await audit_logger.log({
                "event": "agent_loop_complete",
                "user_id": user_id,
                "iterations": agent.iteration_count,
                "tokens_used": tokens_used,
                "cost_usd": cost
            })
            
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        
        except Exception as e:
            await audit_logger.log({
                "event": "agent_loop_error",
                "user_id": user_id,
                "error": str(e)
            })
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(generate_response(), media_type="text/event-stream")
```

### CLI: Display Streamed Status Updates

```python
# cli/src/commands/chat.py

async def chat_command(project_path: str, aws_profile: str):
    """Interactive chat with agent loop"""
    
    while True:
        user_input = input("\n> ").strip()
        
        if user_input in ["/exit", "/quit"]:
            break
        
        # Send to backend
        response = await api_client.post(
            "/api/v1/chat",
            json={
                "message": user_input,
                "project_path": project_path,
                "aws_profile": aws_profile,
                "conversation_history": conversation_history
            },
            stream=True  # Get SSE stream
        )
        
        # Display streamed responses
        print("\n🤖 Agent thinking...")
        
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                event = json.loads(line[6:])
                
                if event["type"] == "status":
                    # Show real-time status updates
                    print(f"  {event['message']}")
                
                elif event["type"] == "response":
                    # Show final answer
                    print(f"\n{event['content']}")
                
                elif event["type"] == "error":
                    print(f"❌ {event['message']}")
                
                elif event["type"] == "done":
                    # Save to conversation DB
                    await save_conversation(user_input, final_answer, conversation_history)
```

-----

## Complete Example: Agent Loop in Action

**User:** “Why is my Lambda timing out?”

**Agent Loop Output (Streamed to CLI):**

```
🤖 Agent thinking...
  🤔 Iteration 1/10: Analyzing...
  🔧 Using tool: scan_project_structure()...
  ✓ scan_project_structure: Detected src/, tests/, infra/ folders. Found 45 Python files, 12 test files, Terraform manifests...
  
  🤔 Iteration 2/10: Analyzing...
  🔧 Using tool: search_codebase(lambda)...
  ✓ search_codebase: Found handler.py, lambda_utils.py, tests/test_lambda.py...
  
  🤔 Iteration 3/10: Analyzing...
  🔧 Using tool: read_file(src/handler.py)...
  ✓ read_file: Read 150 lines. Found db_query() call in line 45...
  
  🤔 Iteration 4/10: Analyzing...
  🔧 Using tool: get_aws_logs(/aws/lambda/my-func)...
  ✓ get_aws_logs: Found error pattern: "Query timeout after 30s" (5 occurrences in last hour)...
  
  🤔 Iteration 5/10: Analyzing...
  🔧 Using tool: get_aws_resource_config(lambda, my-func)...
  ✓ get_aws_resource_config: Timeout=30s, Memory=512MB, Duration=28000ms avg...
  
  🤔 Iteration 6/10: Analyzing...
  🔧 Using tool: get_db_schema(postgres)...
  ✓ get_db_schema: Retrieved schema. Found users_orders table with 1M+ rows...
  
  ✅ Analysis complete!

**Your Lambda is timing out due to N+1 queries:**

In `src/handler.py` (line 45-52), you loop through users and query the database 
individually:
```python
for user in users:
    orders = db.query("SELECT * FROM orders WHERE user_id = ?", user.id)
```

With 1M+ users and a 30-second timeout, this will always exceed the limit.

**Fix:**

1. Use a single JOIN query instead of looping
1. Increase Lambda timeout to 60s (quick fix)
1. Increase memory to 1024MB (more concurrent connections)
1. Consider RDS Proxy for connection pooling

Here’s the refactored code:
[code example]

```
---

This is **much more powerful** than the non-agentic approach! The agent:
- ✅ Autonomously gathers information
- ✅ Makes intelligent decisions about what to read
- ✅ Provides real-time status updates
- ✅ Asks users when needed
- ✅ Gracefully handles complexity
- ✅ Falls back to asking for help if stuck

### Overview: Provider-Agnostic Backend

The backend uses an **abstract LLM provider interface**. This allows:
- ✅ Day 1 support for Bedrock (primary)
- ✅ Easy addition of OpenAI, Claude.ai, etc. (without CLI changes)
- ✅ Provider switching via environment variable
- ✅ Centralized cost tracking and rate limiting
- ✅ Unified audit trail
```

CLI → Private API Gateway → Lambda
├─ LLMProviderFactory.get_provider()
│  ├─ Return BedrockProvider (day 1)
│  ├─ Return OpenAIProvider (future)
│  └─ Return FallbackProvider (if primary fails)
└─ provider.invoke(system_prompt, messages, …)
↓
Result (same format regardless of provider)

```
### LLM Provider Interface

```python
# backend/src/llm/provider.py

from abc import ABC, abstractmethod
from typing import AsyncIterator

class LLMProvider(ABC):
    """Abstract base class for LLM providers"""
    
    @abstractmethod
    async def invoke(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        stream: bool = False
    ) -> str | AsyncIterator[str]:
        """
        Invoke the language model
        
        Args:
            system_prompt: System instructions
            messages: Conversation history [{"role": "user"|"assistant", "content": "..."}]
            max_tokens: Max output tokens
            temperature: Creativity (0.0-1.0)
            stream: Return tokens one-by-one (streaming)
        
        Returns:
            Complete response (if not streaming) or token stream (if streaming)
        """
        pass
    
    @abstractmethod
    def get_model_id(self) -> str:
        """Get model identifier for logging"""
        pass
    
    @abstractmethod
    def get_provider_name(self) -> str:
        """Get provider name (bedrock, openai, etc.)"""
        pass
```

### Day 1: Bedrock Provider Implementation

```python
# backend/src/llm/bedrock_provider.py

import boto3
from typing import AsyncIterator

class BedrockProvider(LLMProvider):
    """AWS Bedrock provider (Day 1)"""
    
    def __init__(
        self,
        model_id: str = "anthropic.claude-3-sonnet-20240229-v1:0",
        region: str = "us-west-2"
    ):
        self.model_id = model_id
        self.region = region
        # Backend uses service role (has bedrock:InvokeModel permission)
        self.bedrock = boto3.client("bedrock-runtime", region_name=region)
    
    async def invoke(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        stream: bool = False
    ) -> str | AsyncIterator[str]:
        """Invoke Claude model via AWS Bedrock"""
        
        request_body = {
            "messages": messages,
            "system": system_prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": 0.9
        }
        
        try:
            if stream:
                return self._stream_invoke(request_body)
            else:
                return await self._sync_invoke(request_body)
        except Exception as e:
            if "AccessDenied" in str(e):
                raise LLMError(
                    "Backend Lambda lacks bedrock:InvokeModel permission"
                )
            raise LLMError(f"Bedrock error: {str(e)}")
    
    async def _sync_invoke(self, request_body: dict) -> str:
        """Non-streaming invoke"""
        response = self.bedrock.invoke_model(
            modelId=self.model_id,
            body=json.dumps(request_body),
            contentType="application/json",
            accept="application/json"
        )
        
        result = json.loads(response["body"].read())
        return result["content"][0]["text"]
    
    async def _stream_invoke(self, request_body: dict) -> AsyncIterator[str]:
        """Streaming invoke (tokens one-by-one)"""
        response = self.bedrock.invoke_model_with_response_stream(
            modelId=self.model_id,
            body=json.dumps(request_body),
            contentType="application/json"
        )
        
        for event in response["body"]:
            if "contentBlockDelta" in event:
                delta = event["contentBlockDelta"]["delta"]
                if "text" in delta:
                    yield delta["text"]
    
    def get_model_id(self) -> str:
        return self.model_id
    
    def get_provider_name(self) -> str:
        return "bedrock"
```

### Future: OpenAI Provider (Example)

```python
# backend/src/llm/openai_provider.py (Future - not day 1)

from openai import OpenAI, AsyncOpenAI

class OpenAIProvider(LLMProvider):
    """OpenAI provider (future provider)"""
    
    def __init__(
        self,
        model_id: str = "gpt-4-turbo",
        api_key: str = None
    ):
        self.model_id = model_id
        self.client = AsyncOpenAI(api_key=api_key or config.OPENAI_API_KEY)
    
    async def invoke(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        stream: bool = False
    ) -> str | AsyncIterator[str]:
        """Invoke OpenAI model"""
        
        full_messages = [
            {"role": "system", "content": system_prompt},
            *messages
        ]
        
        response = await self.client.chat.completions.create(
            model=self.model_id,
            messages=full_messages,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=stream
        )
        
        if stream:
            return self._stream_from_response(response)
        else:
            return response.choices[0].message.content
    
    async def _stream_from_response(self, response):
        """Convert OpenAI stream to token iterator"""
        async for chunk in response:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    
    def get_model_id(self) -> str:
        return self.model_id
    
    def get_provider_name(self) -> str:
        return "openai"
```

### Provider Factory Pattern

```python
# backend/src/llm/factory.py

from typing import Dict, Type

class LLMProviderFactory:
    """Factory for creating LLM provider instances"""
    
    _providers: Dict[str, Type[LLMProvider]] = {
        "bedrock": BedrockProvider,
        "openai": OpenAIProvider,
        # Add more providers here as needed
    }
    
    @classmethod
    def get_provider(
        cls,
        provider_name: str = None,
        **kwargs
    ) -> LLMProvider:
        """
        Get an LLM provider instance
        
        Args:
            provider_name: Name of provider (bedrock, openai, etc.)
                          If None, uses config.DEFAULT_LLM_PROVIDER
            **kwargs: Additional arguments for provider (model_id, api_key, etc.)
        
        Returns:
            LLMProvider instance
        """
        
        provider_name = provider_name or config.DEFAULT_LLM_PROVIDER
        
        if provider_name not in cls._providers:
            raise ValueError(
                f"Unknown LLM provider: {provider_name}. "
                f"Available: {list(cls._providers.keys())}"
            )
        
        provider_class = cls._providers[provider_name]
        return provider_class(**kwargs)
    
    @classmethod
    def register_provider(cls, name: str, provider_class: Type[LLMProvider]):
        """Register a new provider (for plugins)"""
        cls._providers[name] = provider_class
    
    @classmethod
    def list_providers(cls) -> list[str]:
        """List all available providers"""
        return list(cls._providers.keys())
```

### Configuration

```python
# backend/config.py

# Day 1: Use Bedrock
DEFAULT_LLM_PROVIDER = "bedrock"  # or env: LLM_PROVIDER

# Provider-specific config
BEDROCK_MODEL_ID = "anthropic.claude-3-sonnet-20240229-v1:0"
BEDROCK_REGION = "us-west-2"

# Future providers
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL_ID = "gpt-4-turbo"

# Fallback strategy (future)
ENABLE_FALLBACK_PROVIDER = False  # Try OpenAI if Bedrock fails
FALLBACK_PROVIDER = "openai"
```

### Backend API Endpoint: Chat

```python
# backend/src/routers/chat.py

@router.post("/api/v1/chat")
async def chat_endpoint(
    request: ChatRequest,
    credentials = Depends(verify_jwt)
):
    """
    Chat endpoint - route through LLM provider abstraction
    """
    
    # 1. Validate JWT + Okta group
    user_id = credentials["sub"]
    email = credentials["email"]
    groups = credentials.get("groups", [])
    
    if "dev-cli-users" not in groups:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # 2. Check rate limits
    rate_limiter = RateLimiter(dynamodb_client)
    quota_info = await rate_limiter.check_quota(user_id)
    
    if quota_info["tokens_remaining"] <= 0:
        raise HTTPException(
            status_code=429,
            detail="Daily token quota exceeded",
            headers={
                "X-Rate-Limit-Remaining": "0",
                "X-Rate-Limit-Reset": quota_info["reset_at"]
            }
        )
    
    # 3. Build system + user prompts
    system_prompt = build_system_prompt(request.project_manifest)
    messages = build_messages(request.conversation_history, request.message)
    
    # 4. Get LLM provider (factory pattern)
    try:
        provider = LLMProviderFactory.get_provider()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    # 5. Invoke provider
    async def generate():
        """Stream responses from provider"""
        input_token_count = 0
        output_token_count = 0
        
        try:
            async for token in provider.invoke(
                system_prompt=system_prompt,
                messages=messages,
                max_tokens=2048,
                temperature=0.7,
                stream=True
            ):
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                output_token_count += 1  # Approximate
            
            # Send usage info
            input_token_count = count_tokens(system_prompt + str(messages))
            total_tokens = input_token_count + output_token_count
            
            yield f"data: {json.dumps({
                'type': 'usage',
                'input_tokens': input_token_count,
                'output_tokens': output_token_count,
                'total_tokens': total_tokens
            })}\n\n"
            
            # 6. Update rate limits + cost
            cost = calculate_cost(
                provider.get_provider_name(),
                input_token_count,
                output_token_count
            )
            
            await rate_limiter.increment_usage(
                user_id=user_id,
                tokens_used=total_tokens,
                cost_usd=cost
            )
            
            # 7. Log to CloudWatch
            await audit_logger.log({
                "event": "chat_completion",
                "user_id": user_id,
                "email": email,
                "provider": provider.get_provider_name(),
                "model": provider.get_model_id(),
                "input_tokens": input_token_count,
                "output_tokens": output_token_count,
                "cost_usd": cost,
                "timestamp": datetime.now().isoformat()
            })
            
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        
        except Exception as e:
            await audit_logger.log({
                "event": "chat_error",
                "user_id": user_id,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")
```

### Cost Calculation

```python
# backend/src/cost/calculator.py

class CostCalculator:
    """Calculate LLM costs based on provider and token count"""
    
    # Pricing per provider/model (USD per 1M tokens)
    PRICING = {
        "bedrock": {
            "anthropic.claude-3-sonnet": {
                "input": 3.00,
                "output": 15.00
            },
            "anthropic.claude-3-opus": {
                "input": 15.00,
                "output": 75.00
            }
        },
        "openai": {
            "gpt-4-turbo": {
                "input": 10.00,
                "output": 30.00
            },
            "gpt-4": {
                "input": 30.00,
                "output": 60.00
            }
        }
    }
    
    @classmethod
    def calculate_cost(
        cls,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int
    ) -> float:
        """Calculate total cost in USD"""
        
        try:
            provider_pricing = cls.PRICING[provider][model]
            
            input_cost = (input_tokens / 1_000_000) * provider_pricing["input"]
            output_cost = (output_tokens / 1_000_000) * provider_pricing["output"]
            
            return round(input_cost + output_cost, 6)
        except KeyError:
            # Default: charge per token ($0.000001)
            return (input_tokens + output_tokens) / 1_000_000
```

### Cost Tracking in DynamoDB

```python
# Table: dev-cli-rate-limits

Item Schema:
{
  "user_id": "okta_user_123",              # PK
  "date": "2025-03-20",                    # SK
  
  # Quota limits
  "daily_token_limit": 100000,             # Max tokens per day
  "daily_credit_limit": 10.00,             # Max $$ per day
  
  # Usage tracking
  "tokens_used": 45000,                    # Total tokens this day
  "cost_usd": 0.135,                       # Total cost this day ($0.135)
  "requests_made": 12,                     # Number of API calls
  
  # Remaining
  "tokens_remaining": 55000,               # 100000 - 45000
  "credits_remaining": 9.865,              # 10.00 - 0.135
  
  # Metadata
  "last_updated": "2025-03-20T14:30:00Z",
  "reset_at": "2025-03-21T00:00:00Z",
  "expires_at": 1745000000,                # TTL: 32 days
  
  # Provider info (for auditing)
  "primary_provider": "bedrock",
  "providers_used": ["bedrock"]
}
```

### Rate Limiting with Cost Tracking

```python
# backend/src/rate_limit/limiter.py

class RateLimiter:
    """Track tokens, costs, and enforce daily limits"""
    
    def __init__(self, dynamodb_table):
        self.table = dynamodb_table
    
    async def check_quota(self, user_id: str) -> dict:
        """Check if user has quota remaining"""
        
        today = datetime.now().strftime("%Y-%m-%d")
        
        try:
            response = self.table.get_item(
                Key={
                    "user_id": user_id,
                    "date": today
                }
            )
        except Exception:
            # First request of the day
            return {
                "tokens_remaining": 100000,
                "credits_remaining": 10.00,
                "reset_at": tomorrow_midnight()
            }
        
        if "Item" not in response:
            # First request of the day
            return {
                "tokens_remaining": 100000,
                "credits_remaining": 10.00,
                "reset_at": tomorrow_midnight()
            }
        
        item = response["Item"]
        tokens_remaining = item["tokens_remaining"]
        credits_remaining = item["credits_remaining"]
        
        return {
            "tokens_remaining": tokens_remaining,
            "credits_remaining": credits_remaining,
            "reset_at": item["reset_at"]
        }
    
    async def increment_usage(
        self,
        user_id: str,
        tokens_used: int,
        cost_usd: float
    ):
        """Update usage after API call"""
        
        today = datetime.now().strftime("%Y-%m-%d")
        
        self.table.update_item(
            Key={"user_id": user_id, "date": today},
            UpdateExpression="""
                SET tokens_used = if_not_exists(tokens_used, :zero) + :tokens,
                    cost_usd = if_not_exists(cost_usd, :zero) + :cost,
                    requests_made = if_not_exists(requests_made, :zero) + :one,
                    tokens_remaining = :token_limit - (if_not_exists(tokens_used, :zero) + :tokens),
                    credits_remaining = :credit_limit - (if_not_exists(cost_usd, :zero) + :cost),
                    last_updated = :now,
                    expires_at = :expires
            """,
            ExpressionAttributeValues={
                ":zero": 0,
                ":one": 1,
                ":tokens": tokens_used,
                ":cost": cost_usd,
                ":token_limit": 100000,
                ":credit_limit": 10.00,
                ":now": datetime.now().isoformat(),
                ":expires": int(time.time()) + 32*86400
            }
        )
```

### Switching Providers (Configuration)

**Day 1 (Bedrock):**

```bash
export LLM_PROVIDER=bedrock
export BEDROCK_MODEL_ID=anthropic.claude-3-sonnet-20240229-v1:0
```

**Future (OpenAI fallback):**

```bash
export LLM_PROVIDER=bedrock
export ENABLE_FALLBACK_PROVIDER=true
export FALLBACK_PROVIDER=openai
export OPENAI_API_KEY=sk-...
```

**For users:** No changes needed! The provider switch is transparent.

```python
# backend/src/bedrock/client.py

import boto3

class BedrockClient:
    def __init__(self, model_id: str = "anthropic.claude-3-sonnet-20240229-v1:0"):
        self.bedrock = boto3.client("bedrock-runtime", region_name="us-west-2")
        self.model_id = model_id
    
    async def invoke(
        self,
        messages: list[dict],
        system_prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        stream: bool = False
    ) -> str | AsyncIterator[str]:
        """Invoke Bedrock model"""
        
        request_body = {
            "messages": messages,
            "system": system_prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": 0.9
        }
        
        if stream:
            return self._stream_invoke(request_body)
        else:
            return await self._sync_invoke(request_body)
    
    async def _sync_invoke(self, request_body: dict) -> str:
        """Non-streaming invoke"""
        response = self.bedrock.invoke_model(
            modelId=self.model_id,
            body=json.dumps(request_body),
            contentType="application/json",
            accept="application/json"
        )
        
        result = json.loads(response["body"].read())
        return result["content"][0]["text"]
    
    async def _stream_invoke(self, request_body: dict) -> AsyncIterator[str]:
        """Streaming invoke (returns tokens one by one)"""
        response = self.bedrock.invoke_model_with_response_stream(
            modelId=self.model_id,
            body=json.dumps(request_body),
            contentType="application/json"
        )
        
        for event in response["body"]:
            if "contentBlockDelta" in event:
                delta = event["contentBlockDelta"]["delta"]
                if "text" in delta:
                    yield delta["text"]
```

### Prompt Engineering

#### System Prompt Template

```python
# backend/src/bedrock/prompt_builder.py

def build_system_prompt(
    project_manifest: dict,
    conversation_context: str = ""
) -> str:
    """Build comprehensive system prompt"""
    
    prompt = f"""
You are an expert software developer and code assistant specializing in helping 
developers understand, debug, refactor, and improve their code.

PROJECT CONTEXT
===============
{json.dumps(project_manifest, indent=2)}

CONVERSATION HISTORY
====================
{conversation_context}

GUIDELINES
==========
1. Provide concrete, actionable advice
2. Include code examples when relevant
3. Explain the reasoning behind recommendations
4. Ask clarifying questions if needed
5. Consider edge cases and potential issues
6. Suggest tests where appropriate

RESPONSE FORMAT
===============
- Use markdown for code blocks with language specification
- Use clear headings and sections
- Keep explanations concise but thorough
- Provide step-by-step instructions when needed
"""
    return prompt
```

#### Example Request

```json
{
  "messages": [
    {
      "role": "user",
      "content": "How do I optimize this database query?"
    }
  ],
  "system": "[system prompt as above]",
  "max_tokens": 2048,
  "temperature": 0.7
}
```

#### Example Response

```
The database query can be optimized in several ways:

1. **Add an index on frequently queried columns**
```python
CREATE INDEX idx_users_email ON users(email);
```

1. **Use EXPLAIN ANALYZE to identify bottlenecks**

```python
EXPLAIN ANALYZE SELECT * FROM users WHERE email = 'user@example.com';
```

1. **Consider denormalization if you have many joins**
   …

```
---

## Build, Test & Deployment

### Development Workflow

#### Local Development Setup

```bash
# 1. Clone repo
git clone https://github.com/your-org/dev-cli.git
cd dev-cli

# 2. Python CLI development
cd cli
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -e ".[dev]"

# 3. Backend development
cd ../backend
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# 4. VS Code Extension development
cd ../extension
npm install
npm run build

# 5. Run tests
pytest cli/tests/
pytest backend/tests/
npm test --prefix extension

# 6. Run locally
dev-cli chat --project-path /path/to/test-project
```

### Testing Strategy

#### Unit Tests

```bash
# CLI tests
pytest cli/tests/unit/ -v

# Backend tests
pytest backend/tests/unit/ -v

# Extension tests
npm test --prefix extension
```

#### Integration Tests

```bash
# Full chat flow (CLI → Backend → Bedrock)
pytest cli/tests/integration/test_chat_flow.py -v

# Auth flow (Okta SSO)
pytest cli/tests/integration/test_okta_flow.py -v

# API endpoints
pytest backend/tests/integration/test_chat_endpoint.py -v
```

#### Test Coverage Target

- CLI: >80% coverage
- Backend: >85% coverage
- Extension: >70% coverage

### CI/CD Pipeline (GitHub Actions)

#### `.github/workflows/test.yml`

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test-cli:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: |
          cd cli
          pip install -e ".[dev]"
          pytest tests/ --cov=src/dev_cli --cov-report=xml
      - uses: codecov/codecov-action@v3

  test-backend:
    runs-on: ubuntu-latest
    services:
      dynamodb:
        image: amazon/dynamodb-local
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: |
          cd backend
          pip install -e ".[dev]"
          pytest tests/ --cov=src/backend --cov-report=xml
      - uses: codecov/codecov-action@v3

  test-extension:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: '18'
      - run: |
          cd extension
          npm install
          npm test
          npm run lint
```

#### `.github/workflows/publish-cli.yml`

```yaml
name: Publish CLI

on:
  push:
    tags:
      - 'v*'

jobs:
  build-and-publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      # Build wheel
      - run: |
          cd cli
          pip install build
          python -m build
      
      # Publish to PyPI
      - uses: pypa/gh-action-pypi-publish@release/v1
        with:
          password: ${{ secrets.PYPI_API_TOKEN }}
          packages-dir: cli/dist/
      
      # Create GitHub release
      - uses: softprops/action-gh-release@v1
        with:
          files: cli/dist/*
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

#### `.github/workflows/publish-extension.yml`

```yaml
name: Publish VS Code Extension

on:
  push:
    tags:
      - 'v*'

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: '18'
      
      - run: |
          cd extension
          npm install
          npm run build
          npm install -g @vscode/vsce
          vsce package
      
      - uses: microsoft/vscode-github-action@v1.6.1
        with:
          pat: ${{ secrets.VSCODE_MARKETPLACE_TOKEN }}
          package-path: extension/*.vsix
```

### Release Process

1. **Semantic Versioning:** `v1.2.3` (MAJOR.MINOR.PATCH)
1. **Create Release Branch:** `git checkout -b release/v1.2.3`
1. **Update Version Files:**
- `cli/src/dev_cli/version.py`: `__version__ = "1.2.3"`
- `extension/package.json`: `"version": "1.2.3"`
- `backend/src/backend/version.py`: `__version__ = "1.2.3"`
1. **Update CHANGELOG.md**
1. **Commit & Push:** `git push origin release/v1.2.3`
1. **Create PR & Merge**
1. **Tag Release:** `git tag v1.2.3 && git push origin v1.2.3`
1. **GitHub Actions Publish:** Automatically publishes to PyPI, Docker Hub, VS Code Marketplace

### Distribution Methods

#### PyPI (Python Package Index)

```bash
# Installation
pip install dev-cli

# Upgrade
pip install --upgrade dev-cli

# Uninstall
pip uninstall dev-cli
```

#### Docker Hub

```bash
# Pull and run
docker run -v $(pwd):/workspace your-org/dev-cli:latest chat --project-path /workspace

# Or with interactive shell
docker run -it -v $(pwd):/workspace your-org/dev-cli:latest bash
```

#### Homebrew (macOS/Linux)

```bash
# Installation (future)
brew install your-org/dev-cli/dev-cli

# Upgrade
brew upgrade dev-cli
```

#### VS Code Marketplace

```
Search for "Dev-CLI" in VS Code Extensions
Click Install
```

#### GitHub Releases

- Binary builds for Linux, macOS, Windows (optional, if we build standalone)
- Available at https://github.com/your-org/dev-cli/releases

-----

## Security & Privacy

### Data Security

#### Token Storage

- **Location:** `~/.dev-cli/config` (user home directory)
- **Encryption:** Fernet (symmetric encryption via `cryptography` lib)
- **OS-Level Security:**
  - File permissions: `0600` (read/write by owner only)
  - Optional: Use OS keyring (Keychain on macOS, Credentials Manager on Windows)

#### Conversation Storage

- **Location:** `.dev-cli/conversation.db` (in project folder)
- **Encryption:** Optional (user can enable in config)
- **Access Control:** File permissions `0600`
- **Git:** Add `.dev-cli/` to `.gitignore` to prevent accidental commits

#### Bedrock Communication

- **Transport:** TLS 1.2+ (all HTTPS)
- **Content:** Project code is sent to Bedrock as needed
- **Retention:** No code stored on backend (unless explicitly cached)

### Privacy by Default

**Philosophy:** Minimize data leaving user’s machine.

1. **Local Context Management** – all conversation history stays in `.dev-cli/`
1. **Explicit Content Sharing** – user controls which files are sent to Bedrock
1. **No Telemetry** – no usage tracking without explicit opt-in
1. **No Logging of Code** – backend logs request metadata, not code content

### GDPR Compliance

#### User Data Requests

**Endpoints for data export/deletion:**

```
GET /api/v1/user/data/export      - Export all user data
POST /api/v1/user/data/delete     - Delete all user data
```

**Exported Data Includes:**

- User profile (email, Okta ID)
- API usage statistics
- Conversation metadata (no code content)
- Rate limit history

**Deletion Policy:**

- All user data deleted within 30 days of request
- Backups retained for 90 days (legal requirement)

### API Security

#### JWT Validation

- All APIs validate JWT signature locally
- JWK keys cached for 1 hour (reduces Okta load)
- Token expiry checked on every request

#### Rate Limiting

- Protects against abuse
- Per-user daily limits
- DynamoDB tracking

#### Input Validation

- All user inputs validated (project path, message length)
- File path traversal prevention (don’t allow `../` paths)
- Message length limits (max 10,000 characters)

#### CORS Policy

```python
# backend/src/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8888",  # CLI callback
        "vscode-webview://*"       # VS Code extension
    ],
    allow_methods=["GET", "POST"],
    allow_credentials=True
)
```

-----

## Development Roadmap

### Phase 1: MVP (Weeks 1-4)

**Goal:** Core CLI functionality with auth and Bedrock integration

**Deliverables:**

1. **Python CLI (Weeks 1-2)**
- Typer-based CLI framework
- `dev-cli init`, `dev-cli login`, `dev-cli chat` commands
- SQLite conversation storage
- Basic project detection (Python, Node.js, Terraform)
1. **Okta Auth (Week 2)**
- PKCE OAuth2 flow
- Local JWT validation
- Token storage in `~/.dev-cli/config`
1. **FastAPI Backend (Weeks 2-3)**
- `/api/v1/chat` endpoint
- Bedrock integration (Claude 3 Sonnet)
- Basic rate limiting (DynamoDB)
- JWT validation middleware
1. **Testing & CI/CD (Week 4)**
- Unit tests for CLI and backend
- GitHub Actions workflows (test, publish to PyPI)
- Documentation (README, API docs)

**Success Criteria:**

- [ ] `pip install dev-cli` works
- [ ] `dev-cli login` → browser auth → token stored
- [ ] `dev-cli chat` → multi-turn conversation works
- [ ] Conversation saved to `.dev-cli/conversation.db`
- [ ] 80% test coverage (CLI), 85% (backend)
- [ ] <5s response time (P95)

### Phase 2: VS Code Extension (Weeks 5-8)

**Goal:** Feature parity with CLI in VS Code

**Deliverables:**

1. **VS Code Extension (Weeks 5-6)**
- TypeScript + React webview
- Chat sidebar panel
- File browser
- Settings panel
1. **Integration (Week 7)**
- Read/write to same `.dev-cli/` folder as CLI
- Share auth token with CLI
- Status bar indicators
1. **Polish & Testing (Week 8)**
- Unit and integration tests
- VS Code Marketplace publish
- Documentation

**Success Criteria:**

- [ ] Extension published to VS Code Marketplace
- [ ] >500 active users
- [ ] Feature parity with CLI
- [ ] 70% test coverage

### Phase 3: Enhanced Features (Weeks 9-12)

**Goal:** Production-grade reliability and advanced features

**Deliverables:**

1. **Multi-Language Support (Week 9)**
- Advanced detectors (Go, Java, C#, Ruby)
- Language-specific system prompts
- Framework detection (Spring Boot, Django, Rails, etc.)
1. **Context Management (Week 10)**
- Auto-summarization after N messages
- Context export (markdown, JSON)
- Conversation search
1. **Advanced Features (Weeks 11-12)**
- Team features (shared context, basic audit logs)
- Custom Bedrock model selection (Opus vs Sonnet)
- Conversation branching (what-if scenarios)
- Admin dashboard (user management, quota config)

**Success Criteria:**

- [ ] Support >10 languages/frameworks
- [ ] Auto-summarization working
- [ ] Team collaboration features
- [ ] Admin dashboard operational

-----

## Future Enhancements

### Post-MVP (Nice-to-Haves)

1. **IDE Integrations**
- JetBrains IDE plugin (IntelliJ, PyCharm, WebStorm)
- Vim/Neovim plugin
- Emacs mode
1. **Local LLM Support**
- Fallback to Ollama (local models)
- Offline capability for basic analysis
1. **Advanced Features**
- Code review bot (auto-comment on PRs)
- CI/CD integration (comment on failed tests)
- Team collaboration (shared context, branching)
- Database schema analysis (infer from migrations)
- Dependency vulnerability scanning
1. **Enterprise Features**
- SSO integration (SAML, OAuth2 beyond Okta)
- Audit logs and compliance reporting
- Custom rate limits per user/team
- API key rotation
- Custom models (bring your own Bedrock setup)

-----

## Conclusion

**Dev-CLI** aims to be the essential tool for modern polyglot developers, providing seamless, conversational code assistance directly in the terminal and VS Code. By combining local-first architecture, Okta SSO, and AWS Bedrock’s Claude models, we deliver a secure, scalable, and delightful developer experience.

-----

**Version:** 1.0  
**Date:** March 20, 2026  
**Status:** Ready for Development  
**Next Step:** Kick off Phase 1 (Week 1: Set up CLI scaffolding + Okta PKCE flow)