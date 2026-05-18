# Sarvam AI — Offline Intranet AI Dashboard

A full-stack, fully offline AI dashboard designed for secure intranets and air-gapped environments. The **React 18** frontend communicates with a **FastAPI** backend that integrates with **LM Studio** (local LLM inference) and **ChromaDB** (vector store) to deliver RAG-powered conversational agents, an agentic tool-calling loop, an exam generator, a semantic knowledge base search, and usage analytics — all without any external API calls at runtime.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Backend — In-Depth](#backend--in-depth)
  - [Entry Point & App Factory](#entry-point--app-factory)
  - [Configuration](#configuration)
  - [Authentication & Security](#authentication--security)
  - [Database Layer](#database-layer)
  - [LLM Integration](#llm-integration)
  - [Embedding & Vector Store](#embedding--vector-store)
  - [Document Processing](#document-processing)
  - [Agents](#agents)
  - [MCP Server](#mcp-server)
  - [Routers (API Controllers)](#routers-api-controllers)
  - [Utilities](#utilities)
  - [Logging & Audit Trail](#logging--audit-trail)
- [Frontend — In-Depth](#frontend--in-depth)
  - [Entry Point & Root Component](#entry-point--root-component)
  - [Service Layer](#service-layer)
  - [Views](#views)
  - [Shared Components](#shared-components)
  - [Routing & Navigation](#routing--navigation)
  - [Streaming (SSE)](#streaming-sse)
- [API Reference](#api-reference)
- [Setup & Installation](#setup--installation)
- [Configuration Reference](#configuration-reference)
- [Running the Application](#running-the-application)
- [Knowledge Base & RAG Pipeline](#knowledge-base--rag-pipeline)
  - [Part 1 — Document Indexing Pipeline](#part-1--document-indexing-pipeline-shared-by-both-agents)
  - [Part 2 — Classic RAG Chat Workflow](#part-2--classic-rag-chat-workflow-chat_agentpy)
  - [Part 3 — Agentic RAG Chat Workflow](#part-3--agentic-rag-chat-workflow-agentic_ragpy)
  - [Summary Comparison](#summary-comparison)
- [Authentication & Roles](#authentication--roles)
- [Logging](#logging)
- [Docker](#docker)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│               Frontend  (React 18 + Vite)               │
│                                                         │
│  LoginPage  Sidebar  ChatPanel  GeneralChatPanel        │
│  ExamPanel  KnowledgePanel  AdminPanel  SearchPanel     │
│  AnalyticsPanel  ModelSelector  AboutPage               │
└───────────────────────┬─────────────────────────────────┘
          HTTP REST / Server-Sent Events (SSE)
┌───────────────────────▼─────────────────────────────────┐
│              FastAPI  (main.py — app factory)           │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐ │
│  │  Chat Router │  │  Exam Router │  │  Auth Router  │ │
│  └──────┬───────┘  └──────┬───────┘  └───────┬───────┘ │
│         │                 │                   │         │
│  ┌──────▼─────────────────▼───────┐  ┌────────▼──────┐ │
│  │         Agents Layer           │  │  SQLite DB    │ │
│  │  chat_agent.py  (hybrid RAG)   │  │  (users,      │ │
│  │  agentic_rag.py (tool-calling) │  │  convs,       │ │
│  │  exam_agent.py  (exam gen)     │  │  knowledge,   │ │
│  └────────────┬───────────────────┘  │  analytics)   │ │
│               │                      └───────────────┘ │
│  ┌────────────▼───────────────────┐                     │
│  │     LM Studio  (local LLM)     │◄── ChromaDB         │
│  │  http://localhost:1234/v1      │    (vector store)   │
│  └────────────────────────────────┘                     │
│                                                         │
│  MCP Server  ──► Keyword expansion tool                 │
└─────────────────────────────────────────────────────────┘
```

All components run **fully offline** — zero external API calls at runtime.

---

## Features

| Feature | Description |
|---|---|
| **General Chat Agent** | Conversational AI with streaming responses, cross-conversation memory, and hybrid RAG citations |
| **Agentic RAG Chat** | ReAct-style tool-calling loop where the LLM autonomously decides when to search the knowledge base |
| **Exam Generator** | Configurable MCQ / True-False / Fill-in-the-Blank exam papers streamed in real time |
| **KB Semantic Search** | Direct vector search over uploaded documents with ranked, cited results |
| **Knowledge Base** | Upload, index, rename, download, and delete PDF / DOCX / PPTX documents |
| **Analytics Dashboard** | Per-user and platform-wide usage statistics (admin gets full view) |
| **Admin Panel** | Create users, assign roles, configure agent access, reset passwords |
| **User Memory** | The AI remembers personal facts (name, role, location) across sessions |
| **Model Selector** | Switch the active LLM model in LM Studio directly from the UI |
| **JWT Authentication** | Secure login / signup with role-aware UI and session persistence |
| **Audit Log** | Tamper-evident security event log (logins, uploads, admin actions) |
| **Fully Offline** | No internet dependency — ships with offline install scripts |

---

## Tech Stack

### Backend

| Layer | Technology | Version |
|---|---|---|
| Web framework | FastAPI + Uvicorn | 0.136 / 0.44 |
| LLM inference | LM Studio (OpenAI-compatible REST) | any |
| Vector store | ChromaDB | 1.5.8 |
| Embeddings | LM Studio `/v1/embeddings` (or ONNX fallback) | — |
| Relational store | SQLite via `sqlite-utils` | 3.39 |
| LLM orchestration | LangChain + LangChain-Community | 1.2 / 0.4 |
| Document parsing | PyPDF, Docx2txt, python-pptx, unstructured | latest |
| Authentication | PyJWT + bcrypt | 2.12 / 5.0 |
| MCP tooling | mcp[cli] | ≥ 1.27 |
| Data validation | Pydantic | 2.13 |

### Frontend

| Layer | Technology | Version |
|---|---|---|
| UI framework | React | 18.3 |
| Build tool | Vite + @vitejs/plugin-react | 5.4 |
| Styling | Tailwind CSS + Typography plugin | 3.4 |
| Icons | Lucide React | 0.400 |
| Markdown rendering | react-markdown + remark-gfm + remark-breaks + rehype-raw | 9.0 |
| HTTP / Streaming | Native Fetch API + EventSource (SSE) | — |

---

## Project Structure

```
Model-AI/
├── backend/
│   ├── app/
│   │   ├── main.py                 # App factory — middleware, routers, MCP mount
│   │   ├── config.py               # All paths, env vars, limits, JWT secret
│   │   ├── auth.py                 # JWT creation, password hashing, FastAPI deps
│   │   ├── database.py             # SQLite helpers — users, convs, messages, analytics
│   │   ├── chroma_store.py         # ChromaDB vector store — index, search, health check
│   │   ├── llm.py                  # LM Studio client factory + model management
│   │   ├── models.py               # Pydantic request/response schemas
│   │   ├── mcp_server.py           # MCP tool server (keyword expansion)
│   │   ├── agents/
│   │   │   ├── chat_agent.py       # Hybrid RAG chat — memory + history + KB search
│   │   │   ├── agentic_rag.py      # ReAct tool-calling loop (autonomous agent)
│   │   │   └── exam_agent.py       # Structured exam paper generator
│   │   ├── routers/
│   │   │   ├── auth.py             # /api/auth/* — login, signup, /me
│   │   │   ├── chat.py             # /api/chat/* + /api/agentic-chat/*
│   │   │   ├── conversations.py    # /api/conversations/*
│   │   │   ├── exam.py             # /api/exam/*
│   │   │   ├── knowledge.py        # /api/knowledge/*
│   │   │   ├── admin.py            # /api/admin/* (admin-only)
│   │   │   ├── analytics.py        # /api/analytics/*
│   │   │   ├── files.py            # /api/files/* (per-conversation uploads)
│   │   │   └── llm_router.py       # /api/llm/* (model list & switch)
│   │   └── utils/
│   │       ├── document_loader.py  # File-to-chunk conversion for PDF / DOCX / PPTX
│   │       ├── prompts.py          # All LangChain prompt templates
│   │       ├── history_store.py    # Conversation history + BM25 history search
│   │       ├── user_memory.py      # Per-user persistent fact extraction & recall
│   │       ├── analytics.py        # Fire-and-forget analytics event tracker
│   │       ├── audit.py            # Security audit logger (90-day retention)
│   │       ├── logger.py           # Rotating file + console logging setup
│   │       ├── sanitizer.py        # Input sanitization helpers
│   │       └── state.py            # Shared in-process state
│   ├── knowledge_files/            # Permanent uploaded knowledge documents
│   ├── uploads/                    # Temporary per-conversation file uploads
│   ├── chroma_db/                  # ChromaDB persistent vector store
│   ├── history/                    # Chat history markdown files + user_facts/
│   ├── logs/                       # Rotating app logs + audit.log
│   ├── packages/                   # Optional: pip wheels for offline install
│   ├── requirements.txt            # Python dependencies (pinned versions)
│   ├── run.py                      # Uvicorn launcher (entry point)
│   ├── win_service.py              # Windows Service wrapper (NSSM-compatible)
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── main.jsx                # React DOM entry point
│   │   ├── App.jsx                 # Root component — auth gate, layout, navigation
│   │   ├── api.js                  # Legacy API helpers (kept for compatibility)
│   │   ├── index.css               # Global CSS + Tailwind directives
│   │   ├── services/               # Modular API service layer
│   │   │   ├── base.js             # Fetch wrapper, token helpers, error extraction
│   │   │   ├── auth.js             # login(), signup(), getMe()
│   │   │   ├── conversations.js    # CRUD for conversation sessions
│   │   │   ├── chat.js             # sendChat(), sendChatStream(), sendAgenticChatStream()
│   │   │   ├── knowledge.js        # uploadDocument(), listDocuments(), deleteDocument()
│   │   │   ├── admin.js            # listUsers(), createUser(), updateUser(), etc.
│   │   │   ├── analytics.js        # getAnalyticsSummary(), getMyAnalytics()
│   │   │   ├── models.js           # listModels(), setActiveModel()
│   │   │   └── index.js            # Barrel re-export of all services
│   │   ├── views/                  # Full-page view components
│   │   │   ├── GeneralChatPanel.jsx  # Agentic RAG chat interface
│   │   │   ├── ChatPanel.jsx         # Classic hybrid RAG chat
│   │   │   ├── ExamPanel.jsx         # Exam paper generator UI
│   │   │   ├── KnowledgePanel.jsx    # Knowledge base document manager
│   │   │   ├── SearchPanel.jsx       # Direct KB semantic search
│   │   │   ├── AnalyticsPanel.jsx    # Usage analytics dashboard
│   │   │   ├── AdminPanel.jsx        # User management (admin only)
│   │   │   ├── AboutPage.jsx         # Project info and version details
│   │   │   └── LoginPage.jsx         # Login / signup forms
│   │   └── components/             # Shared UI components
│   │       ├── Sidebar.jsx           # Navigation + conversation list
│   │       ├── MessageBubble.jsx     # Markdown message renderer
│   │       └── ModelSelector.jsx     # Active LLM model switcher
│   ├── build/                      # Vite production output (served by FastAPI)
│   ├── index.html                  # HTML shell
│   ├── package.json
│   ├── vite.config.js              # Dev proxy: /api → backend:8000
│   ├── tailwind.config.js
│   └── postcss.config.js
├── docker-compose.yml
├── Dockerfile
├── deploy-offline.ps1              # Windows offline deployment script
├── deploy-offline.sh               # Linux offline deployment script
├── deploy-offline-macos.sh         # macOS offline deployment script
├── export-for-offline.ps1          # Exports pip wheels + npm cache for air-gap
├── DEPLOYMENT.md
└── README.md
```

---

## Backend — In-Depth

### Entry Point & App Factory

**`run.py`** launches Uvicorn programmatically, binding to `0.0.0.0:8000`.

**`app/main.py`** is the FastAPI application factory. It:

- Enables **CORS** with configurable allowed origins (intranet-safe defaults).
- Applies a **global per-IP rate limiter** (120 requests / 60 seconds) using a thread-safe in-process store — protects against accidental or intentional flooding.
- Mounts an **MCP authentication middleware** that requires a Bearer token on `/mcp` when `MCP_SECRET_KEY` is set.
- Registers all domain **routers** (auth, chat, conversations, exam, knowledge, admin, analytics, files, llm).
- Mounts the **MCP server** at `/mcp` for tool calls.
- Serves the **React production build** as static files at `/` so one process serves both the API and the SPA.
- Calls `init_db()` on startup to create all SQLite tables.
- Performs an **embedding health check** on startup to warn if ChromaDB is misconfigured.

**`win_service.py`** wraps the application as a Windows Service using the Python `win32service` API, compatible with NSSM for production deployments.

---

### Configuration

All settings live in **`app/config.py`** and are driven by environment variables with sensible offline defaults.

| Variable | Default | Description |
|---|---|---|
| `LM_STUDIO_BASE_URL` | `http://localhost:1234/v1` | LM Studio OpenAI-compatible endpoint |
| `LLM_MODEL` | `qwen2.5-7b-instruct-1m` | Model ID used for chat / exam generation |
| `EMBEDDING_MODE` | `lmstudio` | `lmstudio` (LM Studio `/v1/embeddings`) or `auto` (ONNX fallback) |
| `EMBEDDING_TIMEOUT` | `120` | Seconds to wait per embedding batch call |
| `EMBEDDING_BATCH_SIZE` | `32` | Number of chunks per embedding request |
| `MODEL_CONTEXT_LENGTH` | `10000` | Token context window passed to LM Studio on load |
| `CORS_ORIGINS` | `http://localhost,...` | Comma-separated allowed origins |
| `MCP_SECRET_KEY` | _(empty)_ | Bearer token to protect the `/mcp` endpoint |
| `DEBUG` | `false` | Enables `/docs` Swagger UI when `true` |
| `JWT_EXPIRE_HOURS` | `24` | JWT token lifetime in hours |

**`JWT_SECRET`** is auto-generated with `secrets.token_hex(32)` on first run and saved to `backend/.jwt_secret` for persistence across restarts.

**Upload limits:** 200 MB max file size; accepted formats: `.pdf`, `.docx`, `.pptx`.

---

### Authentication & Security

**`app/auth.py`** provides:

- **`hash_password(plain)`** — bcrypt hash.
- **`verify_password(plain, hashed)`** — constant-time bcrypt comparison.
- **`create_access_token(data)`** — HS256 JWT with configurable expiry.
- **`get_current_user(token)`** — FastAPI dependency that decodes and validates the JWT, returns the user dict.
- **`require_admin(user)`** — FastAPI dependency that enforces the `admin` role; raises HTTP 403 otherwise.

Security measures in place:
- Passwords are **never stored in plain text** (bcrypt with work factor).
- JWTs are signed with a secret that is **never committed** to version control.
- **Rate limiting** (global, per-IP) prevents brute-force and flooding.
- **CORS** is restricted to intranet origins only.
- All admin endpoints require the `admin` role checked server-side.
- The **audit log** records every login attempt, signup, upload, and admin action with timestamps and IP addresses.
- **Input sanitization** (`utils/sanitizer.py`) is applied to user-supplied text before it enters LLM prompts.

---

### Database Layer

**`app/database.py`** is a thin SQLite helper (no ORM). Tables managed:

| Table | Purpose |
|---|---|
| `users` | Username, bcrypt hash, role, active flag, agent permissions |
| `conversations` | Per-user conversation records with agent type and title |
| `messages` | Individual chat messages linked to conversations |
| `knowledge_documents` | Metadata for uploaded knowledge base files |
| `user_memories` | Per-user AI-extracted personal facts (key/value) |
| `analytics_events` | Usage events (agent type, message length, timestamp) |

`init_db()` creates all tables on first run using `CREATE TABLE IF NOT EXISTS`.

---

### LLM Integration

**`app/llm.py`** manages communication with LM Studio:

- `get_llm()` — returns a `ChatOpenAI` instance pointed at the local LM Studio endpoint.
- `get_llm_streaming()` — returns a streaming-enabled `ChatOpenAI` instance.
- `ensure_model_loaded(model_id)` — calls LM Studio's model-load endpoint and waits for readiness; used on startup and when switching models via the UI.
- `is_no_model_error(exception)` / `is_context_size_error(exception)` — classify LM Studio error responses so agents can surface useful messages to the user.

---

### Embedding & Vector Store

**`app/chroma_store.py`** wraps ChromaDB:

- **`lmstudio` mode** — calls LM Studio's `/v1/embeddings` endpoint in configurable batches (default 32 chunks, 120 s timeout). Produces embeddings consistent with the active model's vector space.
- **`auto` mode** — tries LM Studio first; if unreachable, falls back to ChromaDB's built-in ONNX `all-MiniLM-L6-v2` model. Useful for resilient deployments but risks mixing vector spaces between indexing runs.
- `index_document(chunks, doc_id, filename)` — embeds and upserts document chunks into ChromaDB.
- `search_knowledge(query, n_results, doc_ids)` — hybrid semantic + metadata-filtered search.
- `delete_document(doc_id)` — removes all vectors belonging to a document.
- `check_embedding_health()` — runs a minimal test embed on startup to validate configuration.

---

### Document Processing

**`app/utils/document_loader.py`** converts uploaded files into LangChain `Document` chunks:

- Supports **PDF** (PyPDF), **DOCX** (Docx2txt), and **PPTX** (python-pptx + unstructured).
- Chunks at **1 000 characters** with **200-character overlap** using `RecursiveCharacterTextSplitter`.
- Attaches rich metadata to each chunk: `filename`, `doc_type`, `chunk_index`, `total_chunks`, `heading_hint` (first line of the chunk if it looks like a heading).
- Metadata enables per-document filtering in ChromaDB search.

---

### Agents

#### General Chat Agent (`agents/chat_agent.py`)

A **multi-stage hybrid RAG pipeline** combining personal memory, conversation history, and knowledge base search:

1. **Query analysis** — Determines whether the query is a vague follow-up (`_is_substantive_query`) or a personal identity/history question (`_is_history_meta_query`).
2. **User memory recall** — Fetches stored personal facts (name, role, location, etc.) from `user_memory.py` to personalise the response.
3. **Conversation history** — Retrieves recent turns from the current session. For substantive queries, also performs a **cross-conversation Jaccard search** to pull in relevant turns from older conversations.
4. **Knowledge base search** — Hybrid vector + BM25 keyword-boosted search in ChromaDB retrieves up to 4 000 chars of relevant document context. Skipped if the knowledge base is empty.
5. **Answer generation** — LM Studio LLM produces the final answer using `GENERAL_CHAT_RAG_PROMPT` (with KB context) or `GENERAL_CHAT_PROMPT` (general knowledge only). Document facts are cited by filename; the LLM's general knowledge is clearly labelled.
6. **Background tasks** — After each response, AI-based user memory extraction runs in a background thread to detect and store new personal facts.

Streaming is implemented via LangChain's `astream()` and yielded as SSE `token` events.

#### Agentic RAG Chat (`agents/agentic_rag.py`)

A **ReAct-style autonomous agent** where the LLM decides when and how to search:

- The LLM is bound with two tools: `search_knowledge_base` (hybrid vector + BM25) and `expand_search_keywords`.
- The loop runs up to `MAX_AGENT_ITERATIONS` times. At each step, if the LLM returns tool calls they are executed, results appended as `ToolMessage`, and the LLM called again.
- The frontend receives `("thinking", ...)` events during tool execution (shown as a live "thinking" indicator) and `("token", ...)` events for the final streamed answer.
- Handles follow-up detail patterns (`_FOLLOWUP_DETAIL_PATTERNS`) and explicit search signals (`_EXPLICIT_SEARCH_PATTERNS`) to decide whether to force a KB search even on vague queries.

#### Exam Paper Generator (`agents/exam_agent.py`)

Generates fully structured exam papers from knowledge base documents:

- Accepts per-question-type counts: `mcq_count`, `tf_count` (True/False), `fitb_count` (Fill-in-the-Blank).
- Retrieves relevant KB chunks, then instructs the LLM to produce a formatted exam paper with an answer key.
- Streams the generated paper token-by-token via SSE.

---

### MCP Server

**`app/mcp_server.py`** runs a local **Model Context Protocol** server mounted at `/mcp`. It exposes an `expand_keywords` tool that the Agentic RAG agent calls to generate synonyms and related search terms for a user query — improving recall in the hybrid vector + BM25 search.

---

### Routers (API Controllers)

All routers live in `app/routers/` and are registered with an `/api/` prefix.

| Router | Prefix | Purpose |
|---|---|---|
| `auth.py` | `/api/auth` | Login, signup, current user |
| `chat.py` | `/api/chat`, `/api/agentic-chat` | Classic RAG and agentic streaming chat |
| `conversations.py` | `/api/conversations` | CRUD for conversation sessions and message history |
| `exam.py` | `/api/exam` | Exam paper generation (streaming and non-streaming) |
| `knowledge.py` | `/api/knowledge` | Document upload, indexing, list, delete, download, search |
| `admin.py` | `/api/admin` | User management (admin only) |
| `analytics.py` | `/api/analytics` | Platform summary and per-user usage stats |
| `files.py` | `/api/files` | Per-conversation temporary file uploads |
| `llm_router.py` | `/api/llm` | List models, switch active model in LM Studio |

---

### Utilities

| Module | Purpose |
|---|---|
| `utils/document_loader.py` | File-to-chunk conversion for PDF / DOCX / PPTX |
| `utils/prompts.py` | All LangChain `ChatPromptTemplate` definitions (chat, RAG, exam, query normalisation) |
| `utils/history_store.py` | Save/load conversation history; BM25 tokenisation; cross-conversation Jaccard search |
| `utils/user_memory.py` | Regex + LLM extraction of personal facts; read/write to SQLite `user_memories` |
| `utils/analytics.py` | Fire-and-forget `track_message()` runs in a daemon thread so it never slows a request |
| `utils/audit.py` | Dedicated `audit_log()` function; writes to `logs/audit.log` independently of the main log |
| `utils/sanitizer.py` | Strip or escape potentially dangerous input before it enters LLM prompts |
| `utils/state.py` | Lightweight in-process shared state (e.g. currently-loading-model flag) |
| `utils/logger.py` | Configures rotating file handler + console handler; called once at app startup |

---

### Logging & Audit Trail

Logs are written to `backend/logs/`:

| File | Content | Rotation |
|---|---|---|
| `sarvam.log.YYYY-MM-DD` | General application events (INFO+) | Daily |
| `errors.log.YYYY-MM-DD` | Error-level events only | Daily |
| `audit.log` | Security events: logins, failures, uploads, admin actions | Daily, 90-day retention |

The audit logger (`utils/audit.py`) **does not propagate** to the general logger, ensuring security events are never mixed with debug output.

---

## Frontend — In-Depth

### Entry Point & Root Component

**`src/main.jsx`** — Mounts the React app into `#root` using `ReactDOM.createRoot`.

**`src/App.jsx`** — Root component responsible for:

- Reading the JWT token and current user from `localStorage` on load.
- Rendering `<LoginPage />` for unauthenticated users.
- Rendering the main layout (sidebar + active view) for authenticated users.
- Holding the top-level navigation state (`activeView`).
- Passing `user`, `token`, and navigation callbacks down as props.

---

### Service Layer

All API communication is centralised in `src/services/`. Each module uses the `request()` helper from `base.js` which automatically attaches the `Authorization: Bearer <token>` header and handles 401 session expiry (clears token + reloads the page).

| Service | Key exports |
|---|---|
| `base.js` | `request()`, `authHeaders()`, `getToken()`, `clearToken()`, `extractErrorDetail()` |
| `auth.js` | `login(username, password)`, `signup(username, password)`, `getMe()` |
| `conversations.js` | `listConversations()`, `createConversation(agentType, title)`, `renameConversation()`, `deleteConversation()`, `getMessages(id)` |
| `chat.js` | `sendChat()`, `sendChatStream()`, `sendAgenticChatStream()`, `sendExamStream()`, file upload helpers |
| `knowledge.js` | `uploadDocument(file)`, `listDocuments()`, `deleteDocument(id)`, `reindexDocument(id)`, `searchKnowledge(query, n)` |
| `admin.js` | `listUsers()`, `createUser()`, `updateUser()`, `deleteUser()`, `resetPassword()` |
| `analytics.js` | `getAnalyticsSummary()`, `getMyAnalytics()` |
| `models.js` | `listModels()`, `setActiveModel(modelId)` |

`src/api.js` is retained for backward compatibility with older component imports.

---

### Views

Full-page panels rendered based on the `activeView` state in `App.jsx`:

#### `GeneralChatPanel.jsx`
The primary chat interface using the **Agentic RAG** backend (`/api/agentic-chat/stream`). Features:
- Real-time token streaming via SSE with an AbortController for cancellation.
- **Thinking indicator** — displays live tool-call progress (e.g. "Searching knowledge base…") while the agent is deciding.
- Per-conversation **file attachment** — users can upload files scoped to the current conversation.
- Inline markdown rendering via `MessageBubble`.
- Document source citations displayed below AI responses.
- Conversation history loaded on conversation switch.

#### `ChatPanel.jsx`
Classic hybrid RAG chat using `/api/chat/stream`. Same streaming approach but without the tool-calling loop — useful as a simpler, lower-latency option.

#### `ExamPanel.jsx`
Form-driven exam generation UI:
- Text instruction field for topic / scope.
- Inputs to set MCQ, True-False, and Fill-in-the-Blank question counts.
- Optional file attachment for per-session documents.
- Streams the generated exam paper in real time.
- **Download as `.txt`** button appears once generation is complete.

#### `KnowledgePanel.jsx`
Knowledge base document manager:
- Drag-and-drop or click-to-upload for PDF / DOCX / PPTX (max 200 MB).
- Displays each document's name, upload date, file size, indexing status, and chunk count.
- Per-document actions: re-index, rename, download original, delete.
- Deletion removes both the file from disk and all associated vectors from ChromaDB.

#### `SearchPanel.jsx`
Direct semantic search over the knowledge base:
- Sends queries to `/api/knowledge/search` and displays ranked results.
- Each result shows the matched text chunk, source filename, and relevance score.
- Links to download the source document.
- Returns up to 12 results per query.

#### `AnalyticsPanel.jsx`
Usage analytics dashboard:
- **Admin view**: platform-wide stats — total users, total messages, breakdown by agent type (chat, agentic-chat, exam), and top active users.
- **User view**: personal stats — message count per agent type and activity over time.
- Rendered as stat cards and bar charts built with pure Tailwind CSS (no chart library dependency).

#### `AdminPanel.jsx`
Admin-only user management (requires `admin` role):
- Table of all users with role, active status, and agent permissions.
- Create new users with username, password, and role.
- Update role (`admin` / `user`) and toggle active status.
- Configure per-user agent access (chat, exam, knowledge).
- Reset passwords without knowing the current password.
- Delete users (cannot delete yourself).

#### `LoginPage.jsx`
Login and signup forms:
- Toggles between login and signup mode.
- On success, stores JWT token and user object in `localStorage` and triggers an app re-render.
- Displays validation errors inline.

#### `AboutPage.jsx`
Static information page showing project name, version, tech stack summary, and offline deployment notes.

---

### Shared Components

#### `Sidebar.jsx`
Left navigation panel:
- Lists all conversations for the current user grouped by agent type.
- New conversation button (creates via API and switches view).
- Inline rename (double-click) and delete (trash icon) for each conversation.
- Active view navigation buttons: General Chat, Classic Chat, Exam, Knowledge, Search, Analytics, Admin (admin only), About.
- Displays the logged-in username and a logout button.

#### `MessageBubble.jsx`
Individual message renderer:
- Uses `react-markdown` with `remark-gfm` (tables, strikethrough, task lists), `remark-breaks` (newlines as `<br>`), and `rehype-raw` (safe HTML pass-through).
- Distinguishes user vs AI messages with different bubble colours.
- Renders code blocks with syntax-aware monospace styling.
- Displays source citation badges below AI messages when document references are present.

#### `ModelSelector.jsx`
Dropdown for switching the active LLM model:
- Calls `GET /api/llm/models` to list available models in LM Studio.
- Calls `PUT /api/llm/model` to switch the active model.
- Disabled during model loading to prevent concurrent switches.

---

### Routing & Navigation

There is no client-side router library. Navigation is purely state-based in `App.jsx` via the `activeView` string:

| `activeView` value | Panel rendered |
|---|---|
| `general-chat` | `GeneralChatPanel` — agentic RAG chat |
| `chat` | `ChatPanel` — classic hybrid RAG chat |
| `exam` | `ExamPanel` — exam paper generator |
| `knowledge` | `KnowledgePanel` — document manager |
| `search` | `SearchPanel` — KB semantic search |
| `analytics` | `AnalyticsPanel` — usage stats |
| `admin` | `AdminPanel` — user management (admin only) |
| `about` | `AboutPage` |

This approach keeps the bundle small and avoids router dependencies for an intranet app with a fixed set of views.

---

### Streaming (SSE)

The frontend consumes **Server-Sent Events** for all generative operations. The shared `_readSSEStream()` helper in `services/chat.js`:

1. Opens a `fetch()` POST request with streaming enabled.
2. Reads the `ReadableStream` chunk-by-chunk using a `TextDecoder`.
3. Splits on `\n` and parses each `data: {...}` line as JSON.
4. Calls the `onData` callback for each event.
5. Respects an `AbortSignal` for user-initiated cancellation.

Event types emitted by the backend:

| Type | Payload | Meaning |
|---|---|---|
| `token` | `{ content: "..." }` | New text token — append to the current message |
| `thinking` | `{ content: "..." }` | Agent tool-call progress message (shown in thinking indicator) |
| `sources` | `{ sources: [...] }` | Document citations at end of response |
| `error` | `{ content: "..." }` | Error to display to the user |
| `done` | — | Stream complete |

---

## API Reference

### Auth — `/api/auth`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/login` | None | Returns JWT token on valid credentials |
| POST | `/api/auth/signup` | None | Self-service user registration |
| GET | `/api/auth/me` | Bearer | Return current authenticated user |

### Chat — `/api/chat`, `/api/agentic-chat`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/api/chat` | Bearer | Single-turn hybrid RAG chat (JSON) |
| POST | `/api/chat/stream` | Bearer | Streaming hybrid RAG chat (SSE) |
| POST | `/api/agentic-chat/stream` | Bearer | Streaming agentic tool-calling chat (SSE) |

### Conversations — `/api/conversations`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/api/conversations` | Bearer | List all conversations for the current user |
| POST | `/api/conversations` | Bearer | Create a new conversation |
| PATCH | `/api/conversations/{id}` | Bearer | Rename a conversation |
| DELETE | `/api/conversations/{id}` | Bearer | Delete a conversation and all its messages |
| GET | `/api/conversations/{id}/messages` | Bearer | Load full message history |

### Knowledge Base — `/api/knowledge`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/api/knowledge/upload` | Bearer | Upload a PDF/DOCX/PPTX document |
| GET | `/api/knowledge/documents` | Bearer | List all knowledge documents |
| DELETE | `/api/knowledge/documents/{id}` | Bearer | Remove a document and its vectors |
| POST | `/api/knowledge/documents/{id}/index` | Bearer | Re-index a document in ChromaDB |
| GET | `/api/knowledge/documents/{id}/download` | Bearer | Download the original file |
| GET | `/api/knowledge/search` | Bearer | Semantic search over all documents |
| DELETE | `/api/knowledge/clear` | Admin | Wipe the entire knowledge base |

### Exam — `/api/exam`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/api/exam` | Bearer | Generate exam paper (full JSON response) |
| POST | `/api/exam/stream` | Bearer | Stream exam generation (SSE) |

### Admin — `/api/admin`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/api/admin/users` | Admin | List all users |
| POST | `/api/admin/users` | Admin | Create a new user |
| PUT | `/api/admin/users/{id}` | Admin | Update role, active status, or agent permissions |
| PUT | `/api/admin/users/{id}/password` | Admin | Reset a user's password |
| DELETE | `/api/admin/users/{id}` | Admin | Delete a user |

### Analytics — `/api/analytics`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/api/analytics/summary` | Admin | Platform-wide usage statistics |
| GET | `/api/analytics/me` | Bearer | Usage statistics for the current user |

### LLM Model — `/api/llm`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/api/llm/models` | Bearer | List models available in LM Studio |
| PUT | `/api/llm/model` | Bearer | Switch the active model |

### Files — `/api/files`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/api/files/upload` | Bearer | Upload a temporary file for a conversation |
| GET | `/api/files/{file_id}` | Bearer | Download a conversation-scoped file |

---

## Setup & Installation

### Prerequisites

- **Python 3.11+**
- **Node.js 18+** and npm
- **[LM Studio](https://lmstudio.ai/)** running locally on `http://localhost:1234` with a model loaded
- A model loaded in LM Studio (default: `qwen2.5-7b-instruct-1m`)

---

### Backend Setup

#### Online install

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS / Linux
pip install -r requirements.txt
```

#### Offline / air-gapped install

```bash
# On a machine WITH internet access:
pip download -r requirements.txt -d ./packages

# Copy the entire backend/ folder to the target machine, then:
pip install --no-index --find-links=./packages -r requirements.txt
```

The `export-for-offline.ps1` script automates the export step on Windows.

---

### Frontend Setup

#### Online install

```bash
cd frontend
npm install
```

#### Production build

```bash
cd frontend
npm run build
# Output: frontend/build/  — served automatically by FastAPI at /
```

---

## Configuration Reference

Edit `backend/app/config.py` or set environment variables before launching:

```bash
# Windows PowerShell
$env:LM_STUDIO_BASE_URL = "http://192.168.1.100:1234/v1"
$env:LLM_MODEL           = "qwen2.5-7b-instruct-1m"
$env:EMBEDDING_MODE      = "lmstudio"
$env:CORS_ORIGINS        = "http://192.168.1.0,http://192.168.1.1"
$env:DEBUG               = "true"   # enables /docs Swagger UI
```

```bash
# Linux / macOS
export LM_STUDIO_BASE_URL="http://localhost:1234/v1"
export LLM_MODEL="qwen2.5-7b-instruct-1m"
export EMBEDDING_MODE="lmstudio"
export DEBUG="false"
```

For the frontend dev proxy, edit `frontend/vite.config.js`:

```js
server: {
  proxy: {
    '/api': 'http://your-backend-host:8000',
  },
},
```

---

## Running the Application

### Backend

```bash
cd backend
venv\Scripts\activate        # Windows
python run.py
```

- API available at `http://localhost:8000`
- Swagger UI (debug mode only): `http://localhost:8000/docs`

### Frontend — development

```bash
cd frontend
npm run dev
```

Dev server at `http://localhost:5173` with HMR and `/api` proxy to `http://localhost:8000`.

### Frontend — production

```bash
cd frontend
npm run build
```

FastAPI serves `frontend/build/` as static files at `/`. Only the backend process is needed in production.

### Windows Service (production)

```bash
# Install NSSM, then:
nssm install SarvamAI "C:\path\to\python.exe" "C:\Model-AI\backend\win_service.py"
nssm start SarvamAI
```

---

## Knowledge Base & RAG Pipeline

RAG stands for **Retrieval-Augmented Generation**. In plain terms: instead of relying only on what the AI model already knows (which may be outdated or incorrect), the system first *searches* your uploaded documents for relevant facts, then *gives those facts to the AI* so it can answer accurately and cite its sources.

There are two separate RAG workflows in this application — one for the **Classic Chat** agent and one for the **Agentic Chat** agent. Both share the same document indexing pipeline but differ in how they decide *when* and *what* to search.

---

### Part 1 — Document Indexing Pipeline (shared by both agents)

This pipeline runs **once when you upload a document** and stores the result in ChromaDB so it can be searched instantly later.

```
PDF / DOCX / PPTX
      │
      ▼
  [1] PARSE          Extract raw text with PyPDF / Docx2txt / python-pptx
      │
      ▼
  [2] CHUNK          Split into 1 000-char pieces, 200-char overlap
      │
      ▼
  [3] EMBED          LM Studio /v1/embeddings converts text → float vector
      │
      ▼
  [4] INDEX          ChromaDB stores (vector + text + metadata) on disk
```

#### Step 1 — Parse

**Simple:** The system reads your file and converts it into raw text, like copying all the words out of a PDF.

**Technical:** `utils/document_loader.py` dispatches to the appropriate library based on the file extension:
- `.pdf` → `PyPDF` (page-by-page text extraction)
- `.docx` → `Docx2txt` (paragraph-level extraction preserving structure)
- `.pptx` → `python-pptx` + `unstructured` (slide text + notes)

The first line of each extracted block is examined as a potential `heading_hint` — if it looks like a heading (short, title-cased, no sentence punctuation) it is stored as metadata to help the LLM understand document structure.

#### Step 2 — Chunk

**Simple:** Long documents are cut into small, overlapping pieces so the AI can read and compare each piece individually. The overlap means no idea gets accidentally cut in half at a boundary.

**Technical:** LangChain's `RecursiveCharacterTextSplitter` splits on `\n\n`, `\n`, and space in that priority order. Each chunk is **1 000 characters** with a **200-character overlap**. Each chunk carries rich metadata:

| Metadata field | Value |
|---|---|
| `filename` | Original file name |
| `doc_id` | UUID assigned at upload |
| `chunk_index` | Position of this chunk in the document |
| `total_chunks` | Total number of chunks |
| `doc_type` | `pdf`, `docx`, or `pptx` |
| `heading_hint` | First line if it resembles a heading |
| `position` | `beginning`, `middle`, or `end` |

#### Step 3 — Embed

**Simple:** Each piece of text is converted into a long list of numbers (a "vector") that captures the *meaning* of the text. Two pieces that talk about the same topic will produce similar lists of numbers, even if they use different words.

**Technical:** `chroma_store.py` calls LM Studio's `/v1/embeddings` endpoint (OpenAI-compatible) in batches of 32 chunks, with a 120-second timeout per batch. The same model that handles chat also handles embeddings, so the vector space is consistent. If LM Studio is unreachable and `EMBEDDING_MODE=auto`, it falls back to ChromaDB's built-in ONNX `all-MiniLM-L6-v2` model.

> **Important:** Always use the same embedding model for indexing and searching. Mixing models produces incompatible vectors and degraded search quality. Re-index all documents after switching models.

#### Step 4 — Index

**Simple:** All the number-lists (vectors) are saved to a database on disk, tagged with which document and which piece of the document they came from. From this point the document is "in the knowledge base" and can be searched instantly.

**Technical:** ChromaDB upserts each chunk as a record containing the embedding vector, the raw text content, and the metadata dict. Upsert semantics mean the same chunk can be re-indexed without duplication — existing records are overwritten by document ID + chunk index. The SQLite-backed ChromaDB store persists to `backend/chroma_db/`.

---

### Part 2 — Classic RAG Chat Workflow (`chat_agent.py`)

This is the **General Chat** panel (also the Classic Chat panel). The agent runs a deterministic 6-stage pipeline for every user message.

```
User message
      │
      ▼
  [1] QUERY ANALYSIS        Substantive? Follow-up? Identity/history question?
      │
      ▼
  [2] USER MEMORY RECALL    Load personal facts (name, role, location, …)
      │
      ▼
  [3] HISTORY RETRIEVAL     Recent turns + cross-conversation Jaccard search
      │
      ▼
  [4] KNOWLEDGE BASE SEARCH Hybrid vector + BM25 search → relevance filter
      │
      ▼
  [5] LLM GENERATION        Prompt = system + memory + history + KB context + query
      │
      ▼
  [6] BACKGROUND TASKS      Memory extraction in a daemon thread
      │
      ▼
  Streamed answer + source citations
```

#### Stage 1 — Query Analysis

**Simple:** Before searching anything, the system asks: "Is this a real question, a vague follow-up ('tell me more'), or a question about the user's own past ('what did I say before')?" The answer changes what gets searched.

**Technical:** Two classifiers run on the raw user text:

- **`_is_substantive_query(query)`** — tokenizes the query with the same stop-word list used by BM25, then additionally removes follow-up meta-words (`give`, `explain`, `details`, `tell`, `more`, `please`, etc.). If **≥ 2 genuine topic tokens** survive, the query is substantive and cross-conversation search is enabled. Vague inputs like *"give me in details"* → 0 topic tokens → only recent turns are used.

- **`_is_history_meta_query(query)`** — regex matches identity/recall phrases: *"what is my name"*, *"what did we discuss"*, *"previous task"*, *"remind me"*, etc. When matched, the most recent exchanges across ALL the user's conversations are loaded (not just the current one), so the AI can answer continuity questions across sessions.

- **`_build_rag_search_query()`** — builds the actual ChromaDB query. For vague follow-ups it substitutes the last substantive user question. For KB-grounded conversations (where a recent AI reply included document sources) it combines the current query with the previous substantive question to widen recall.

#### Stage 2 — User Memory Recall

**Simple:** The system checks if it has stored any personal facts about you from previous conversations (your name, job, location, etc.) and includes them in the prompt so the AI can personalise its response.

**Technical:** `utils/user_memory.py` reads the `user_memories` SQLite table for the current user, returning key/value pairs extracted in past sessions. `format_user_facts()` serialises them into a compact natural-language string that is injected into the system prompt. Example: *"You know the following about this user: name=Alex, role=Army Officer, location=Shillong."*

#### Stage 3 — History Retrieval

**Simple:** The AI reads the recent back-and-forth of the conversation so it knows what has been said already. For specific topics it also digs into older conversations to find relevant past discussions.

**Technical:** `_build_history()` applies a two-tier retrieval strategy:

| Query type | Strategy |
|---|---|
| **History/identity** | Last 4 turns of current conversation **+** 5 most recent turns across ALL the user's conversations |
| **Substantive** | Last 4 turns of current conversation **+** Jaccard similarity search across past conversations (top-K matches) |
| **Vague follow-up** | Last 4 turns of current conversation only |

**Jaccard search** (`search_history_for_user`) tokenizes both the query and each stored exchange using the BM25 stop-word list, computes token set intersection / union, and ranks by overlap score. This is purely in-memory (no vector DB call) and runs in milliseconds. Each injected history message is capped at 800 characters to conserve context window space.

#### Stage 4 — Knowledge Base Search

**Simple:** The system converts your question into a vector, searches the document database for the most similar pieces of text, filters out anything that doesn't match well enough, and puts the best results into the AI's prompt.

**Technical:** `_get_rag_context()` runs a multi-step retrieval process:

1. **Chunk count check** — if the knowledge base is empty, search is skipped entirely.
2. **Vector search** — `search_knowledge(query, limit=6)` embeds the enriched query and calls ChromaDB's cosine-similarity search, returning the top-6 chunks with their scores.
3. **Spell-correction retry** — if the initial search returns zero results and the original query is available, `_normalize_query()` asks the LLM to fix typos (e.g. *"assam rifiles act"* → *"assam rifles act"*) and retries once.
4. **Relevance threshold filter** — chunks with cosine similarity score **< 0.50** are discarded. This prevents weakly-related document content from polluting the answer (e.g. "Operation Sindoor" chunks appearing for a "Kargil War" query just because both mention India and military operations).
5. **Context assembly** — surviving chunks are assembled into a single context string (max 2 000 characters) with source attribution: `[Source: filename.pdf, middle of document]\nSection: heading\ncontent…`

If the search produces results, `GENERAL_CHAT_RAG_PROMPT` is used (instructs the LLM to answer from documents and cite sources). If no results, `GENERAL_CHAT_PROMPT` is used (instructs the LLM to answer from general knowledge and explicitly say so).

#### Stage 5 — LLM Generation (Streaming)

**Simple:** All the gathered information — personal facts, conversation history, document excerpts, and the user's question — is assembled into one big prompt and sent to the AI. The AI's response is streamed back word-by-word so you see it appearing in real time.

**Technical:** The final messages list is:

```
[SystemMessage(prompt + user_facts)]
[HumanMessage(history[0])]
[AIMessage(history[1])]
...
[HumanMessage(user_query + kb_context)]
```

LangChain's `astream()` is called on the `ChatOpenAI` instance pointed at `http://localhost:1234/v1`. Each streamed `AIMessageChunk` is yielded as an SSE `token` event to the frontend. After all tokens are emitted, a `sources` event carries the list of cited filenames and document IDs.

#### Stage 6 — Background Memory Extraction

**Simple:** After answering, the system quietly checks if the conversation contained any new personal facts about you (like you mentioned your name or job) and saves them for future conversations — without slowing down the response.

**Technical:** A background daemon thread calls `extract_and_save_user_facts(user_id, conversation_text)` from `utils/user_memory.py`. This first runs a regex pass (fast path) for obvious patterns like *"my name is …"*, *"I am a …"*, *"I work at …"*. If the regex finds nothing, a lightweight LLM call extracts structured facts from the conversation. Results are stored as key/value rows in the `user_memories` SQLite table and recalled in Stage 2 of the next request.

---

### Part 3 — Agentic RAG Chat Workflow (`agentic_rag.py`)

The **Agentic Chat** panel uses a fundamentally different approach: instead of the system deciding when to search, the **LLM itself decides** — and it may search multiple times, with different queries, before producing a final answer.

```
User message
      │
      ▼
  Build messages: [system + memory + history + user_query]
      │
      ▼
  ┌───────────────────────────────────────────┐
  │           REACT LOOP (max 3 iterations)   │
  │                                           │
  │   LLM responds with tool_calls?           │
  │        YES → execute tools                │
  │              append ToolMessage results   │
  │              emit ("thinking", …) to UI   │
  │              loop again                   │
  │        NO  → plain text answer            │
  │              stream tokens to UI          │
  └───────────────────────────────────────────┘
      │
      ▼
  Streamed answer + source citations
```

#### Tool: `search_knowledge_base`

**Simple:** The AI searches your uploaded documents for relevant content. It can call this multiple times with different search phrases to get a comprehensive answer.

**Technical:** The tool implementation in `_tool_search_knowledge_base()`:
1. **Auto-expands** the query by calling `_tool_expand_search_keywords()` first — this uses the LLM (or MCP server) to generate synonyms and related domain terms (e.g. *"assam rifles"* → *"paramilitary, northeast India, border security, AFSPA"*).
2. Combines the original query + expanded keywords into one broader combined query.
3. Calls `search_knowledge(combined_query, limit)` in ChromaDB.
4. Falls back to the original query if the expanded search returns nothing.
5. Returns formatted results: `[filename, position]\nSection: heading\ncontent…` separated by `---`.

Maximum context returned per tool call: **3 000 characters**.

#### Tool: `expand_search_keywords`

**Simple:** Generates related words and synonyms for the search term. This helps find relevant documents even when they use different wording than the user's question.

**Technical:** Calls the MCP server's `expand_keywords` tool at `/mcp`. The MCP server uses the active LLM to produce a comma-separated list of synonyms and related domain terms. These are automatically prepended to every `search_knowledge_base` call.

#### Tool: `search_conversation_history`

**Simple:** Searches the user's past conversations for relevant discussions. Useful when the user asks "what did we cover last time about X?"

**Technical:** Calls `search_history_for_user()` with Jaccard tokenisation to find the most topically similar past exchanges. Results are injected as `ToolMessage` content so the LLM can reference past discussions in its answer.

#### Tool: `save_memory`

**Simple:** When the user mentions something personal (their name, job, location, a goal), the AI can save it permanently so it remembers in future conversations.

**Technical:** Directly calls `save_user_fact(user_id, key, value, category)` from `utils/user_memory.py`. Categories: `personal`, `preference`, `goal`, `note`, `task`.

#### Force-search overrides

**Simple:** Even if the LLM would naturally just answer from its training data, the system can force it to search the knowledge base first when it detects follow-up patterns or explicit search requests.

**Technical:** Before the ReAct loop starts, two regex checks modify the system prompt:

- **`_FOLLOWUP_DETAIL_PATTERNS`** — matches phrases like *"tell me more"*, *"give me more details"*, *"elaborate on this"*. When matched, the system prompt instructs the LLM to call `search_knowledge_base` before answering.
- **`_EXPLICIT_SEARCH_PATTERNS`** — matches explicit search commands like *"search in the database"*, *"find from the document"*, *"based on the uploaded file"*. When matched, same override applies.

#### Thinking events

During tool calls the backend emits `("thinking", "Searching knowledge base for: <query>…")` SSE events. The frontend `GeneralChatPanel.jsx` displays these as a live animated thinking indicator, giving the user visibility into what the agent is doing while they wait for the final answer.

---

### Summary Comparison

| Aspect | Classic RAG Chat | Agentic RAG Chat |
|---|---|---|
| **Who decides to search** | Always (pipeline stage 4) | The LLM (tool calling) |
| **Number of searches** | One per message | Up to 3 per message |
| **Query expansion** | Manual query enrichment | Automatic via `expand_keywords` tool |
| **Spell correction** | Yes — LLM retry on empty result | Included in auto-expansion |
| **Thinking indicator** | No | Yes — live tool-call progress |
| **Memory saving** | Background thread (post-response) | In-loop tool call (`save_memory`) |
| **Latency** | Lower (deterministic pipeline) | Higher (iterative LLM calls) |
| **Best for** | Fast factual Q&A, follow-ups | Complex multi-step research |

Documents can be re-indexed at any time (e.g. after switching embedding models) via `POST /api/knowledge/documents/{id}/index`.

---

## Authentication & Roles

| Role | Permissions |
|---|---|
| `admin` | Full access — user management, knowledge base clear, analytics summary, all agents |
| `user` | Chat agents, exam agent, file uploads, view/search knowledge documents, personal analytics |

- Tokens expire after **24 hours** (configurable via `JWT_EXPIRE_HOURS`).
- Role is enforced **server-side** on every protected endpoint — the frontend role check is only for UI presentation.
- Inactive users (deactivated by admin) cannot log in even with valid credentials.

---

## Logging

| Log file | Content | Retention |
|---|---|---|
| `logs/sarvam.log.YYYY-MM-DD` | All INFO+ application events | 30 days |
| `logs/errors.log.YYYY-MM-DD` | ERROR-level events only | 30 days |
| `logs/audit.log` | Security events (login, signup, upload, admin actions) | 90 days |

The audit logger is isolated from the general logger (`propagate = False`) to prevent security events from leaking into debug output.

---

## Docker

### Single container

```bash
# Build
docker build -t sarvam-backend ./backend

# Run
docker run -p 8000:8000 \
  -e LM_STUDIO_BASE_URL=http://host.docker.internal:1234/v1 \
  -v $(pwd)/backend/knowledge_files:/app/knowledge_files \
  -v $(pwd)/backend/chroma_db:/app/chroma_db \
  sarvam-backend
```

### Docker Compose (recommended)

```bash
docker-compose up --build
```

The included `docker-compose.yml` wires `host.docker.internal` so the container can reach LM Studio running on the host machine on both Docker Desktop (Windows / macOS) and Linux Docker Engine.

Volumes are configured to persist `knowledge_files/`, `chroma_db/`, and `logs/` across container restarts.
