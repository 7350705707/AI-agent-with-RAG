import React, { useEffect, useState } from 'react';
import {
  MessageSquare,
  FileText,
  Plus,
  Trash2,
  PanelLeftClose,
  PanelLeftOpen,
  Bot,
  Shield,
  LogOut,
  LogIn,
  User,
  BookOpen,
  Info,
} from 'lucide-react';
import { listConversations, createConversation, deleteConversation } from '../api';
import ModelSelector from './ModelSelector';

const ALL_AGENTS = [
  { id: 'general', label: 'General AI Chat', icon: MessageSquare },
  { id: 'chat', label: 'RAG AI Chat', icon: Bot },
  { id: 'exam', label: 'Exam Paper Generator', icon: FileText },
  { id: 'knowledge', label: 'Library Base', icon: BookOpen },
];

export default function Sidebar({
  activeAgent,
  setActiveAgent,
  activeConversation,
  setActiveConversation,
  isOpen,
  toggle,
  user,
  onLogout,
  onShowAuth,
}) {
  const [conversations, setConversations] = useState([]);

  // 'general' is always visible; other agents filtered by user assignment
  const agents = user
    ? ALL_AGENTS.filter((a) => a.id === 'general' || user.agents?.includes(a.id))
    : ALL_AGENTS.filter((a) => a.id === 'general');

  const refresh = async () => {
    try {
      const data = await listConversations(activeAgent);
      setConversations(data);
    } catch {
      /* backend might be down */
    }
  };

  useEffect(() => {
    refresh();
  }, [activeAgent, activeConversation]);

  const handleNew = async () => {
    const title =
      activeAgent === 'exam' ? 'New Exam' : 'New Chat';
    const conv = await createConversation(activeAgent, title);
    setConversations((prev) => [conv, ...prev]);
    setActiveConversation(conv.id);
  };

  const handleDelete = async (e, id) => {
    e.stopPropagation();
    await deleteConversation(id);
    setConversations((prev) => prev.filter((c) => c.id !== id));
    if (activeConversation === id) setActiveConversation(null);
  };

  return (
    <aside
      className={`${
        isOpen ? 'w-72' : 'w-0'
      } transition-all duration-200 bg-indigo-950 border-r border-indigo-900 flex flex-col overflow-hidden`}
    >
      {/* Toggle button (always visible) */}
      <button
        onClick={toggle}
        className="absolute top-3 left-3 z-50 p-1.5 rounded-md hover:bg-indigo-800 text-indigo-300 transition"
        title={isOpen ? 'Collapse sidebar' : 'Expand sidebar'}
      >
        {isOpen ? <PanelLeftClose size={18} /> : <PanelLeftOpen size={18} />}
      </button>

      {isOpen && (
        <>
          {/* Brand */}
          <div className="flex items-center gap-2 px-4 pt-14 pb-4 border-b border-indigo-800/50">
            <div className="w-8 h-8 rounded-lg bg-indigo-500/30 flex items-center justify-center">
              <Bot size={18} className="text-indigo-300" />
            </div>
            <span className="font-bold text-sm tracking-wide text-white">Sarvam AI</span>
          </div>

          {/* Agent selector */}
          <div className="px-3 pt-4 pb-2">
            <p className="text-[11px] uppercase tracking-wider text-indigo-400/80 mb-2 px-1">
              Agents
            </p>
            {agents.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => setActiveAgent(id)}
                className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm mb-1 transition ${
                  activeAgent === id
                    ? 'bg-indigo-500/30 text-white font-medium'
                    : 'hover:bg-indigo-800/60 text-indigo-200'
                }`}
              >
                <Icon size={16} />
                {label}
              </button>
            ))}
          </div>

          {/* Conversations (hide for non-conversation agents) */}
          {activeAgent !== 'knowledge' && activeAgent !== 'admin' && (
          <div className="flex-1 flex flex-col overflow-hidden px-3 pt-2">
            <div className="flex items-center justify-between mb-2 px-1">
              <p className="text-[11px] uppercase tracking-wider text-indigo-400/80">
                History
              </p>
              <button
                onClick={handleNew}
                className="p-1 rounded hover:bg-indigo-800 text-indigo-300 transition"
                title="New conversation"
              >
                <Plus size={15} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto space-y-0.5">
              {conversations.map((c) => (
                <button
                  key={c.id}
                  onClick={() => setActiveConversation(c.id)}
                  className={`w-full group flex items-center justify-between px-3 py-2 rounded-lg text-sm transition ${
                    activeConversation === c.id
                      ? 'bg-indigo-500/40 text-white font-medium'
                      : 'hover:bg-indigo-800/50 text-indigo-200'
                  }`}
                >
                  <span className="truncate">{c.title}</span>
                  <Trash2
                    size={14}
                    className="opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-300 shrink-0"
                    onClick={(e) => handleDelete(e, c.id)}
                  />
                </button>
              ))}
              {conversations.length === 0 && (
                <p className="text-xs text-indigo-400/70 px-1 pt-2">
                  No conversations yet.
                </p>
              )}
            </div>
          </div>
          )}

          {/* Admin button (only for admin users) */}
          {user?.role === 'admin' && (
            <div className="px-3 py-2">
              <button
                onClick={() => setActiveAgent('admin')}
                className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition ${
                  activeAgent === 'admin'
                    ? 'bg-amber-500/20 text-amber-300'
                    : 'hover:bg-indigo-800/60 text-indigo-200'
                }`}
              >
                <Shield size={16} />
                Admin Panel
              </button>
            </div>
          )}

          {/* Model selector */}
          <div className="shrink-0 px-3 py-2 border-t border-indigo-900/60">
            <p className="text-[11px] uppercase tracking-wider text-indigo-400/70 mb-2 px-1">
              Model
            </p>
            <ModelSelector />
          </div>

          {/* About button */}
          <div className="px-3 py-1">
            <button
              onClick={() => setActiveAgent('about')}
              className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition ${
                activeAgent === 'about'
                  ? 'bg-indigo-500/30 text-white'
                  : 'hover:bg-indigo-800/60 text-indigo-200'
              }`}
            >
              <Info size={16} />
              About
            </button>
          </div>

          {/* Bottom section */}
          <div className="shrink-0 border-t border-indigo-900/60 px-3 py-3">
            {user ? (
              /* Logged-in: show user info & logout */
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 min-w-0">
                  <div className="w-7 h-7 rounded-full bg-indigo-600 flex items-center justify-center shrink-0">
                    <User size={14} className="text-indigo-200" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs text-white font-medium truncate">{user.username}</p>
                    <p className="text-[10px] text-indigo-300/80 capitalize">{user.role}</p>
                  </div>
                </div>
                <button
                  onClick={onLogout}
                  className="p-1.5 rounded hover:bg-indigo-800 text-indigo-400 hover:text-red-400 transition"
                  title="Sign out"
                >
                  <LogOut size={14} />
                </button>
              </div>
            ) : (
              /* Guest: show sign in / sign up button */
              <button
                onClick={onShowAuth}
                className="w-full flex items-center justify-center gap-2 px-3 py-2.5 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-medium transition"
              >
                <LogIn size={14} />
                Sign In / Sign Up
              </button>
            )}
          </div>
        </>
      )}
    </aside>
  );
}
