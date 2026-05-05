# Sarvam AI — Frontend

A React 18 single-page application for the Sarvam AI offline intranet dashboard. It provides a clean chat interface, an exam generator, knowledge base management, and an admin panel — all communicating with the FastAPI backend over HTTP/SSE.

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Setup & Installation](#setup--installation)
- [Development](#development)
- [Production Build](#production-build)
- [Environment & API URL](#environment--api-url)
- [Components](#components)
- [Routing & Navigation](#routing--navigation)

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
frontend/
├── src/
│   ├── main.jsx               # React app entry point
│   ├── App.jsx                # Root component — auth gate, layout, routing
│   ├── api.js                 # All backend API calls (fetch wrappers)
│   ├── index.css              # Global CSS + Tailwind directives
│   └── components/
│       ├── Sidebar.jsx        # Conversation list + navigation
│       ├── ChatPanel.jsx      # Chat interface with streaming SSE
│       ├── MessageBubble.jsx  # Individual message renderer (markdown)
│       ├── ExamPanel.jsx      # Exam generation interface
│       ├── KnowledgePanel.jsx # Knowledge base document manager
│       ├── AdminPanel.jsx     # User management (admin only)
│       ├── ModelSelector.jsx  # LLM model switcher
│       ├── LoginPage.jsx      # Login / signup form
│       └── AboutPage.jsx      # About / info page
├── build/                     # Production build output (served by FastAPI/Nginx)
├── index.html                 # HTML entry point
├── package.json
├── vite.config.js             # Vite config (dev proxy to backend)
├── tailwind.config.js
└── postcss.config.js
```

---

## Setup & Installation

### Prerequisites

- Node.js 18+ and npm

### Install dependencies

```bash
cd frontend
npm install
```

---

## Development

```bash
npm run dev
```

The dev server starts at `http://localhost:5173`.  
API requests are proxied to the backend at `http://localhost:8000` via Vite's dev proxy (configured in `vite.config.js`).

---

## Production Build

```bash
npm run build
```

Output is placed in `frontend/build/`. FastAPI serves this directory as static files at the root path `/`.

To preview the production build locally:

```bash
npm run preview
```

---

## Environment & API URL

In development, Vite proxies `/api/*` to the backend automatically — no environment variables needed.

For a custom backend URL (e.g., a different host/port), edit the proxy in `vite.config.js`:

```js
server: {
  proxy: {
    '/api': 'http://your-backend-host:8000',
  },
},
```

---

## Components

### `App.jsx`
Root component. Handles JWT auth state (stored in `localStorage`), renders the login page for unauthenticated users, and composes the main layout (Sidebar + active panel).

### `Sidebar.jsx`
Lists conversations grouped by agent type. Supports creating, renaming, and deleting conversations. Includes navigation links to Knowledge Base, Admin Panel, and About.

### `ChatPanel.jsx`
Main chat interface. Sends messages to `/api/chat/stream` and renders tokens as they arrive via SSE. Shows document source citations returned by the RAG pipeline. Supports file attachment uploads.

### `MessageBubble.jsx`
Renders a single chat message. Uses `react-markdown` with GFM (tables, strikethrough, task lists) and `remark-breaks` for line-break handling. Code blocks are syntax-highlighted.

### `ExamPanel.jsx`
Form-driven UI to configure and generate exam papers. Streams the generated paper from the backend and allows downloading as text.

### `KnowledgePanel.jsx`
Displays all uploaded knowledge documents with their indexing status, chunk count, and upload metadata. Supports upload, manual re-index trigger, rename, download, and delete.

### `AdminPanel.jsx`
Admin-only user management table. Create users, assign roles (`admin`/`user`), configure which agents each user can access, reset passwords, activate/deactivate accounts.

### `ModelSelector.jsx`
Dropdown to list and switch the active LLM model loaded in LM Studio without restarting the backend.

### `LoginPage.jsx`
Login and signup forms with JWT token handling. Stores the token in `localStorage` and triggers app re-render on successful auth.

### `AboutPage.jsx`
Project info and version details.

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

The active panel is controlled by the Sidebar via a `setView` callback.
