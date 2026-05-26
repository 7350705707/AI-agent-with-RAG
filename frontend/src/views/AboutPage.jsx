import React, { useState } from 'react';
import {
  Bot,
  Shield,
  BookOpen,
  FileText,
  MessageSquare,
  Server,
  WifiOff,
  Lock,
  Cpu,
  Database,
  Layers,
  Users,
  ClipboardCheck,
  ChevronDown,
  ChevronRight,
  Info,
} from 'lucide-react';

function Section({ title, children }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="mb-8">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 w-full text-left mb-3 group"
      >
        <span className="text-xs uppercase tracking-wider text-gray-400 group-hover:text-gray-200 transition">{title}</span>
        {open ? <ChevronDown size={13} className="text-gray-500" /> : <ChevronRight size={13} className="text-gray-500" />}
      </button>
      {open && children}
    </div>
  );
}

function FeatureCard({ icon: Icon, color, title, children }) {
  return (
    <div className={`p-5 bg-gray-800/50 border border-gray-800 rounded-xl`}>
      <div className={`w-10 h-10 rounded-lg ${color} flex items-center justify-center mb-3`}>
        <Icon size={18} className="text-white" />
      </div>
      <p className="text-sm font-semibold text-gray-100 mb-2">{title}</p>
      <p className="text-xs text-gray-400 leading-relaxed">{children}</p>
    </div>
  );
}

export default function AboutPage() {
  return (
    <div className="flex-1 overflow-y-auto px-6 py-8 max-w-3xl mx-auto w-full">
      {/* Hero */}
      <div className="flex items-center gap-4 mb-8">
        <div className="w-14 h-14 rounded-2xl overflow-hidden flex items-center justify-center shrink-0 bg-transparent">
          <img
            src="/MCTE_logo.png"
            alt="MCTE"
            className="w-full h-full object-contain"
            onError={(e) => {
              e.currentTarget.style.display = 'none';
              e.currentTarget.nextElementSibling.style.display = 'flex';
            }}
          />
          <div className="hidden w-full h-full rounded-2xl bg-blue-600 items-center justify-center">
            <Bot size={30} />
          </div>
        </div>
        <div>
          <h1 className="text-2xl font-bold">EduQuest Ecosystem</h1>
          <p className="text-sm text-gray-400">Secure, Offline, Multi-Agent AI Platform</p>
        </div>
      </div>

      {/* Description */}
      <p className="text-sm text-gray-400 leading-relaxed mb-8">
        EduQuest Ecosystem is a fully offline, privacy-first AI assistant platform designed for secure intranet
        deployments. It runs entirely on your local network — no data ever leaves your organisation.
        Powered by <span className="text-blue-400">LM Studio</span> and open-source language models,
        it provides conversational AI with document retrieval, exam paper generation with a multi-stage
        approval workflow, and a searchable knowledge library — all without requiring an internet connection.
      </p>

      {/* Core Systems */}
      <Section title="Core Systems">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <FeatureCard icon={MessageSquare} color="bg-blue-600" title="RAG AI Chat">
            Ask questions about your organisation's documents using Retrieval-Augmented Generation (RAG).
            Uploaded files are chunked, embedded with sentence-transformers, and stored in ChromaDB.
            At query time the system combines semantic vector search with BM25 full-text ranking
            (hybrid retrieval) to surface the most relevant passages — which are then passed to the
            language model as grounded context. Answers cite the source documents so you can verify them.
          </FeatureCard>
          <FeatureCard icon={FileText} color="bg-violet-600" title="Exam Paper Generator">
            Automatically generate exam papers from any knowledge-base document or pasted text.
            Supports three question formats: Multiple Choice (MCQ), True / False, and Fill in the Blanks.
            You can control the difficulty level, number of questions per type, subject name, and
            instructor details. The generator produces a clean plain-text paper with a separate answer
            key. Generated papers are saved as conversations so you can retrieve, edit, and re-submit
            them at any time.
          </FeatureCard>
          <FeatureCard icon={ClipboardCheck} color="bg-amber-600" title="Approval System">
            Exam papers follow a configurable multi-stage approval workflow before they are finalised.
            An officer submits a paper; it then passes through one or more approver stages (e.g.,
            Reviewing Officer → Commanding Officer). Each approver can approve the paper (advancing it
            to the next stage) or send it back with remarks — including flagging individual questions
            for revision. Once all stages are approved the paper is locked and can be exported as
            PDF, DOCX (×4 shuffled sets), or JSON. Officers receive a WhatsApp-style badge notification
            when papers are awaiting their review.
          </FeatureCard>
          <FeatureCard icon={BookOpen} color="bg-emerald-600" title="Knowledge Base">
            Upload PDF, DOCX, TXT, and other document formats to build a searchable library.
            Each file is automatically split into overlapping text chunks (configurable size and
            overlap) and indexed into both ChromaDB (for semantic/vector search) and SQLite FTS5
            (for keyword/BM25 search). The hybrid retriever merges results from both engines using
            Reciprocal Rank Fusion. Documents can be tagged, searched, and deleted individually.
            All indexing runs locally — no cloud embedding API is needed.
          </FeatureCard>
        </div>
      </Section>

      {/* Key Features */}
      <Section title="Key Features">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {[
            [WifiOff, '100% Offline', 'Runs entirely on your local network — no internet required. Suitable for air-gapped or high-security environments.'],
            [Lock, 'Secure by Design', 'JWT authentication, role-based access control, account approval workflow, and no external API calls.'],
            [Cpu, 'LM Studio Integration', 'Connect any GGUF model via LM Studio\'s OpenAI-compatible local API. Swap models without restarting the server.'],
            [Database, 'Hybrid RAG Search', 'FTS5 BM25 full-text search fused with ChromaDB vector search via Reciprocal Rank Fusion for best-of-both retrieval.'],
            [Layers, 'Multi-Agent Architecture', 'Separate specialised agents for chat, exam generation, knowledge management, search, analytics, and approvals.'],
            [Users, 'User Management', 'Admin panel with modal UI for creating users, assigning roles and agents, approving new signups, and resetting passwords.'],
            [Server, 'FastAPI Backend', 'Python FastAPI with SQLite (WAL), streaming SSE chat responses, and optional Windows Service deployment.'],
            [Shield, 'Approval Workflow', 'Multi-stage exam paper approval with per-stage officer assignment, send-back with question-level remarks, and export.'],
          ].map(([Icon, title, desc]) => (
            <div key={title} className="flex gap-3 p-4 bg-gray-800/50 border border-gray-800 rounded-xl">
              <div className="shrink-0 w-9 h-9 rounded-lg bg-blue-600/20 flex items-center justify-center">
                <Icon size={16} className="text-blue-400" />
              </div>
              <div>
                <p className="text-sm font-medium text-gray-100">{title}</p>
                <p className="text-xs text-gray-500 mt-1">{desc}</p>
              </div>
            </div>
          ))}
        </div>
      </Section>

      {/* Tech Stack */}
      <Section title="Technology Stack">
        <div className="bg-gray-800/50 border border-gray-800 rounded-xl p-4">
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-y-3 gap-x-4 text-sm">
            {[
              ['Frontend', 'React + Vite + Tailwind CSS'],
              ['Backend', 'Python FastAPI'],
              ['Database', 'SQLite (WAL mode) + FTS5'],
              ['Vector Store', 'ChromaDB (local)'],
              ['LLM Runtime', 'LM Studio (local GGUF models)'],
              ['AI Framework', 'LangChain'],
              ['Search', 'Hybrid: BM25 + Vector (RRF)'],
              ['Auth', 'JWT (HS256) + bcrypt'],
              ['Deployment', 'Windows Service / IIS (HTTPS)'],
              ['Protocols', 'REST + SSE (streaming)'],
            ].map(([label, val]) => (
              <div key={label}>
                <p className="text-xs text-gray-500">{label}</p>
                <p className="text-gray-200 text-sm">{val}</p>
              </div>
            ))}
          </div>
        </div>
      </Section>

      {/* Footer */}

      <div className="flex items-center gap-2 text-xs text-gray-600 border-t border-gray-800 pt-4">
        <Info size={13} />
        <span>Sarvam AI — Built for secure, offline enterprise deployments. Version 1.0.0</span>
      </div>
    </div>
  );
}

