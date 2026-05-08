import React from 'react';
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
  Info,
} from 'lucide-react';

const Feature = ({ icon: Icon, title, desc }) => (
  <div className="flex gap-4 p-4 bg-gray-800/50 border border-gray-800 rounded-xl">
    <div className="shrink-0 w-10 h-10 rounded-lg bg-blue-600/20 flex items-center justify-center">
      <Icon size={18} className="text-blue-400" />
    </div>
    <div>
      <p className="text-sm font-medium text-gray-100">{title}</p>
      <p className="text-xs text-gray-500 mt-1">{desc}</p>
    </div>
  </div>
);

export default function AboutPage() {
  return (
    <div className="flex-1 overflow-y-auto px-6 py-8 max-w-3xl mx-auto w-full">
      {/* Hero */}
      <div className="flex items-center gap-4 mb-8">
        <div className="w-14 h-14 rounded-2xl bg-blue-600 flex items-center justify-center shrink-0">
          <Bot size={30} />
        </div>
        <div>
          <h1 className="text-2xl font-bold">Sarvam AI</h1>
          <p className="text-sm text-gray-400">Secure, Offline, Multi-Agent AI Dashboard</p>
        </div>
      </div>

      {/* Description */}
      <p className="text-sm text-gray-400 leading-relaxed mb-8">
        Sarvam AI is a fully offline, privacy-first AI assistant platform designed for secure intranet
        deployments. It runs entirely on your local network — no data ever leaves your organisation.
        Powered by <span className="text-blue-400">LM Studio</span> and open-source language models,
        it provides conversational AI, exam generation, and a searchable knowledge library — all
        without requiring an internet connection.
      </p>

      {/* Agents */}
      <h2 className="text-xs uppercase tracking-wider text-gray-500 mb-3">Agents</h2>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-8">
        <div className="p-4 bg-blue-600/10 border border-blue-600/20 rounded-xl text-center">
          <MessageSquare size={22} className="text-blue-400 mx-auto mb-2" />
          <p className="text-sm font-medium">General AI Chat</p>
          <p className="text-xs text-gray-500 mt-1">Conversational assistant with RAG knowledge retrieval</p>
        </div>
        <div className="p-4 bg-purple-600/10 border border-purple-600/20 rounded-xl text-center">
          <FileText size={22} className="text-purple-400 mx-auto mb-2" />
          <p className="text-sm font-medium">Exam Generator</p>
          <p className="text-xs text-gray-500 mt-1">Auto-generate MCQ, T/F & fill-in-blank exams from documents</p>
        </div>
        <div className="p-4 bg-emerald-600/10 border border-emerald-600/20 rounded-xl text-center">
          <BookOpen size={22} className="text-emerald-400 mx-auto mb-2" />
          <p className="text-sm font-medium">Library Base</p>
          <p className="text-xs text-gray-500 mt-1">Upload & manage reference documents for AI retrieval</p>
        </div>
      </div>

      {/* Features */}
      <h2 className="text-xs uppercase tracking-wider text-gray-500 mb-3">Key Features</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-8">
        <Feature icon={WifiOff} title="100% Offline" desc="Runs entirely on your local network — no internet required." />
        <Feature icon={Lock} title="Secure by Design" desc="JWT authentication, role-based access, and no external API calls." />
        <Feature icon={Cpu} title="LM Studio Integration" desc="Connect any GGUF model via LM Studio's OpenAI-compatible API." />
        <Feature icon={Database} title="FTS5 RAG Search" desc="Full-text search over your documents with BM25 ranking for fast retrieval." />
        <Feature icon={Layers} title="Multi-Agent Architecture" desc="Separate specialised agents for chat, exams, and knowledge management." />
        <Feature icon={Users} title="User Management" desc="Admin panel for creating users, assigning roles, and controlling agent access." />
        <Feature icon={Server} title="FastAPI Backend" desc="Python FastAPI backend with SQLite persistence and streaming SSE responses." />
        <Feature icon={Shield} title="Admin Controls" desc="Full admin panel for user management, model selection, and library control." />
      </div>

      {/* Tech Stack */}
      <h2 className="text-xs uppercase tracking-wider text-gray-500 mb-3">Technology Stack</h2>
      <div className="bg-gray-800/50 border border-gray-800 rounded-xl p-4 mb-8">
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-y-3 gap-x-4 text-sm">
          {[
            ['Frontend', 'React + Vite + Tailwind CSS'],
            ['Backend', 'Python FastAPI'],
            ['Database', 'SQLite (WAL mode)'],
            ['LLM Runtime', 'LM Studio (local GGUF models)'],
            ['AI Framework', 'LangChain'],
            ['Search', 'SQLite FTS5 (BM25)'],
            ['Auth', 'JWT (HS256)'],
            ['Deployment', 'Windows Service / IIS (HTTPS)'],
          ].map(([label, val]) => (
            <div key={label}>
              <p className="text-xs text-gray-500">{label}</p>
              <p className="text-gray-200">{val}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center gap-2 text-xs text-gray-600 border-t border-gray-800 pt-4">
        <Info size={13} />
        <span>Sarvam AI — Built for secure, offline enterprise deployments. Version 1.0.0</span>
      </div>
    </div>
  );
}

