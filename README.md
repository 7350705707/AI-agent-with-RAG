# Sarvam AI — Offline Intranet AI Dashboard

A full-stack, fully offline AI dashboard for secure intranets. The **React 18** frontend communicates with a **FastAPI** backend that integrates with **LM Studio** (local LLM) and **ChromaDB** (vector store) to deliver RAG-powered conversational agents, an exam generator, and a knowledge base management system.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Setup & Installation](#setup--installation)
  - [Backend](#backend-setup)
  - [Frontend](#frontend-setup)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [API Reference](#api-reference)
- [Agents](#agents)
- [Knowledge Base & RAG Pipeline](#knowledge-base--rag-pipeline)
- [Authentication & Roles](#authentication--roles)
- [Frontend Components](#frontend-components)
- [Routing & Navigation](#routing--navigation)
- [Logging](#logging)
- [Docker](#docker)

---

## Architecture Overview

```
Frontend (React 18 + Vite)
      │  HTTP / SSE
      ▼
FastAPI (main.py)
      │
      ├── Chat Agent  ──► LM Studio (LLM)  ◄── ChromaDB (vector RAG)
      ├── Exam Agent  ──► LM Studio (LLM)  ◄── ChromaDB (vector RAG)
      ├── Auth        ──► SQLite (users / JWT)
      ├── Knowledge   ──► SQLite (metadata) + ChromaDB (embeddings)
      └── MCP Server  ──► Keyword expansion tool
```

All components run **fully offline** — no external API calls are made at runtime.

---

## Features

- **General Chat Agent** — Conversational AI with real-time streaming responses, conversation history, and RAG-sourced document citations.
- **Exam Generator** — Upload documents and generate structured exam papers (MCQ, short-answer, essay) on demand.
- **Knowledge Base** — Upload, view, index, and delete PDF/DOCX/PPTX documents that power the RAG pipeline.
- **Admin Panel** — Manage users, roles, and agent permissions.
- **Authentication** — JWT-based login/signup with role-aware UI.
- **Model Selector** — Switch the active LLM model in LM Studio from the UI.
- **Markdown Rendering** — Full GFM markdown, tables, and code blocks in chat.
- **Dark/Light responsive UI** — Built with Tailwind CSS.

---

## Tech Stack

### Backend

| Layer | Technology |
|---|---|
| Web framework | FastAPI 0.136 + Uvicorn |
| LLM backend | LM Studio (OpenAI-compatible REST) |
| Vector store | ChromaDB 1.5 |
| Embeddings | Ollama (local) via ChromaDB |
| Relational store | SQLite (via `sqlite-utils`) |
| Document parsing | PyPDF, Docx2txt, python-pptx |
| LLM orchestration | LangChain + LangChain-Community |
| Auth | JWT (PyJWT) + bcrypt |
| MCP tools | mcp[cli] |

### Frontend

| Layer | Technology |
|---|---|
| Framework | React 18 |
| Build tool | Vite 5 |
| Styling | Tailwind CSS 3 + Typography plugin |
| Icons | Lucide React |
| Markdown | react-markdown + remark-gfm + remark-breaks |
| HTTP | Native Fetch API + EventSource (SSE) |

---

## Project Structure

```
Model-AI/
├── backend/
│   ├── app/
│   │   ├── main.py            # All FastAPI routes
│   │   ├── config.py          # Paths, env vars, limits
│   │   ├── auth.py            # JWT creation, password hashing, dependencies
│   │   ├── database.py        # SQLite helpers (conversations, users, knowledge docs)
│   │   ├── chroma_store.py    # ChromaDB vector store helpers
│   │   ├── document_loader.py # PDF / DOCX / PPTX → LangChain Document chunks
│   │   ├── llm.py             # LM Studio LLM factory + model management
│   │   ├── logger.py          # Rotating file + console logging setup
│   │   ├── models.py          # Pydantic request/response models
│   │   ├── prompts.py         # All LangChain prompt templates
│   │   ├── mcp_server.py      # MCP tool server (keyword expansion)
│   │   └── agents/
│   │       ├── chat_agent.py  # General chat — 3-step hybrid RAG pipeline
│   │       └── exam_agent.py  # Exam paper generator agent
│   ├── knowledge_files/       # Permanently stored uploaded knowledge documents
│   ├── uploads/               # Temporary per-conversation file uploads
│   ├── chroma_db/             # ChromaDB persistent storage
│   ├── logs/                  # Rotating application logs
│   ├── requirements.txt       # Python dependencies
│   ├── run.py                 # Entry point (uvicorn launcher)
│   ├── Dockerfile             # Container image definition
│   └── win_service.py         # Windows Service wrapper (NSSM-compatible)
├── frontend/
│   ├── src/
│   │   ├── main.jsx               # React app entry point
│   │   ├── App.jsx                # Root component — auth gate, layout, routing
│   │   ├── api.js                 # All backend API calls (fetch wrappers)
│   │   ├── index.css              # Global CSS + Tailwind directives
│   │   └── components/
│   │       ├── Sidebar.jsx        # Conversation list + navigation
│   │       ├── ChatPanel.jsx      # Chat interface with streaming SSE
│   │       ├── MessageBubble.jsx  # Individual message renderer (markdown)
│   │       ├── ExamPanel.jsx      # Exam generation interface
│   │       ├── KnowledgePanel.jsx # Knowledge base document manager
│   │       ├── AdminPanel.jsx     # User management (admin only)
│   │       ├── ModelSelector.jsx  # LLM model switcher
│   │       ├── LoginPage.jsx      # Login / signup form
│   │       └── AboutPage.jsx      # About / info page
│   ├── build/                     # Production build output (served by FastAPI/Nginx)
│   ├── index.html                 # HTML entry point
│   ├── package.json
│   ├── vite.config.js             # Vite config (dev proxy to backend)
│   ├── tailwind.config.js
│   └── postcss.config.js
├── docker-compose.yml
├── .gitignore
└── README.md
```

---

## Setup & Installation

### Prerequisites

- Python 3.11+
- Node.js 18+ and npm
- [LM Studio](https://lmstudio.ai/) running locally on `http://localhost:1234`
- A model loaded in LM Studio (default: `nemotron-3-nano-4b`)

---

### Backend Setup

#### Install (online)

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

#### Install (offline / air-gapped)

```bash
# On a machine with internet access:
pip download -r requirements.txt -d ./packages

# On the target machine:
pip install --no-index --find-links=./packages -r requirements.txt
```

---

### Frontend Setup

```bash
cd frontend
npm install
```

---

## Configuration

All backend settings are controlled via **environment variables** or fall back to sensible defaults:

| Variable | Default | Description |
|---|---|---|
| `LM_STUDIO_BASE_URL` | `http://localhost:1234/v1` | LM Studio OpenAI-compatible endpoint |
| `LLM_MODEL` | `nemotron-3-nano-4b` | Model ID to use in LM Studio |
| `CORS_ORIGINS` | `http://localhost,...` | Comma-separated allowed origins |

A `JWT_SECRET` is auto-generated on first run and persisted to `.jwt_secret`.

For frontend API URL in development, Vite proxies `/api/*` to the backend automatically — no environment variables needed. For a custom backend URL, edit the proxy in `vite.config.js`:

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
venv\Scripts\activate
python run.py
```

The API will be available at `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

### Frontend (development)

```bash
cd frontend
npm run dev
```

The dev server starts at `http://localhost:5173`.

### Frontend (production build)

```bash
cd frontend
npm run build
```

Output is placed in `frontend/build/`. FastAPI serves this directory as static files at the root path `/`.

---

## API Reference

### Auth

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/login` | Login, returns JWT token |
| POST | `/api/auth/signup` | Self-service registration |
| GET | `/api/auth/me` | Return current user info |

### Chat

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/chat` | Single-turn chat (JSON response) |
| POST | `/api/chat/stream` | Streaming chat (SSE) |

### Conversations

| Method | Endpoint | Description |
|---|---|---|
| GET/POST | `/api/conversations` | List / create conversations |
| PATCH/DELETE | `/api/conversations/{id}` | Rename / delete |
| GET | `/api/conversations/{id}/messages` | Load message history |

### Knowledge Base

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/knowledge/upload` | Upload a document (PDF/DOCX/PPTX) |
| GET | `/api/knowledge/documents` | List all knowledge documents |
| DELETE | `/api/knowledge/documents/{id}` | Remove a document |
| POST | `/api/knowledge/documents/{id}/index` | Manually trigger indexing |
| GET | `/api/knowledge/documents/{id}/download` | Download original file |
| DELETE | `/api/knowledge/clear` | Wipe entire knowledge base (admin) |

### Exam Generator

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/exam` | Generate a full exam paper |
| POST | `/api/exam/stream` | Stream exam generation |

### Admin

| Method | Endpoint | Description |
|---|---|---|
| GET/POST | `/api/admin/users` | List / create users |
| PUT | `/api/admin/users/{id}` | Update role / agents |
| PUT | `/api/admin/users/{id}/password` | Reset password |
| DELETE | `/api/admin/users/{id}` | Delete user |

---

## Agents

### General Chat Agent (`agents/chat_agent.py`)

A 3-step hybrid RAG pipeline:

1. **Keyword Expansion** — MCP tool generates related search terms from the user query.
2. **Hybrid Retrieval** — Combines vector (semantic) search + BM25 keyword boosting in ChromaDB to find the most relevant knowledge base chunks (up to 4 000 chars of context).
3. **Answer Generation** — LM Studio LLM generates the final answer, combining document evidence with its own background knowledge. Document facts are cited by filename; supplementary knowledge is clearly labelled.

If the knowledge base is empty, the agent answers directly from the LLM's general knowledge.

### Exam Paper Generator (`agents/exam_agent.py`)

Generates structured exam papers from knowledge base documents with configurable MCQ, short-answer, and essay sections.

---

## Knowledge Base & RAG Pipeline

- Documents (PDF, DOCX, PPTX) are uploaded via `/api/knowledge/upload`.
- They are **chunked** (1 000 chars, 200 overlap) by `document_loader.py` with rich metadata (filename, doc_type, position, heading hint).
- Chunks are embedded and stored in **ChromaDB**.
- At query time, hybrid search retrieves relevant chunks that are injected as context into the LLM prompt.

---

## Authentication & Roles

| Role | Permissions |
|---|---|
| `admin` | Full access — user management, knowledge base clear, all agents |
| `user` | Chat and exam agents; upload files; view knowledge documents |

Tokens expire after **24 hours** (configurable via `JWT_EXPIRE_HOURS`).

---

## Frontend Components

| Component | Description |
|---|---|
| `App.jsx` | Root component. Handles JWT auth state (stored in `localStorage`), renders login page for unauthenticated users, composes the main layout. |
| `Sidebar.jsx` | Lists conversations grouped by agent type. Supports creating, renaming, and deleting conversations. |
| `ChatPanel.jsx` | Main chat interface. Sends messages to `/api/chat/stream` and renders tokens as they arrive via SSE. Shows document source citations. |
| `MessageBubble.jsx` | Renders a single chat message using `react-markdown` with GFM and `remark-breaks`. |
| `ExamPanel.jsx` | Form-driven UI to configure and generate exam papers. Streams the generated paper and allows downloading as text. |
| `KnowledgePanel.jsx` | Displays all uploaded knowledge documents with indexing status, chunk count, and upload metadata. Supports upload, re-index, rename, download, and delete. |
| `AdminPanel.jsx` | Admin-only user management table. Create users, assign roles, configure agent access, reset passwords, activate/deactivate accounts. |
| `ModelSelector.jsx` | Dropdown to list and switch the active LLM model loaded in LM Studio. |
| `LoginPage.jsx` | Login and signup forms with JWT token handling. |
| `AboutPage.jsx` | Project info and version details. |

---

## Routing & Navigation

There is no client-side router. Navigation is state-based in `App.jsx`:

| State value | Panel shown |
|---|---|
| `chat` | ChatPanel (general chat agent) |
| `exam` | ExamPanel (exam generator) |
| `knowledge` | KnowledgePanel |
| `admin` | AdminPanel (admin role required) |
| `about` | AboutPage |

---

## Logging

Logs are written to `backend/logs/` with daily rotation:

- `servam.log.YYYY-MM-DD` — general application logs
- `errors.log.YYYY-MM-DD` — error-level logs only

---

## Docker

```bash
# Build
docker build -t sarvam-backend ./backend

# Run
docker run -p 8000:8000 \
  -e LM_STUDIO_BASE_URL=http://host.docker.internal:1234/v1 \
  sarvam-backend
```

Or use the included `docker-compose.yml` at the repo root:

```bash
docker-compose up --build
```
