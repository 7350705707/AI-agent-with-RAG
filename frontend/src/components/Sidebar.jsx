import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  FileText,
  Plus,
  Trash2,
  PanelLeftClose,
  PanelLeftOpen,
  Bot,
  Shield,
  LogOut,
  User,
  BookOpen,
  Info,
  Search,
  BarChart2,
  ClipboardCheck,
  Bell,
  UserCircle,
} from 'lucide-react';
import { listConversations, createConversation, deleteConversation, getPendingReviews } from '../api';
import ModelSelector from './ModelSelector';

const ALL_AGENTS = [
  { id: 'chat', label: 'SetuAI Chat', icon: Bot },
  { id: 'exam', label: 'Exam Paper Generator', icon: FileText },
  { id: 'knowledge', label: 'Knowledge Base', icon: BookOpen },
  { id: 'search', label: 'KB Search', icon: Search },
  { id: 'analytics', label: 'Analytics', icon: BarChart2, adminOnly: true },
  { id: 'approval', label: 'Approvals', icon: ClipboardCheck },
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
  onOpenProfile,
}) {
  const [conversations, setConversations] = useState([]);
  const [pendingCount, setPendingCount] = useState(0);

  // user is always logged in — filter agents by assignment
  const agents = ALL_AGENTS.filter((a) => {
    if (a.adminOnly) return user?.role === 'admin';
    if (a.id === 'chat') return true;
    if (a.id === 'approval') return user?.agents?.includes('approval') || user?.agents?.includes('exam');
    return user?.agents?.includes(a.id);
  });

  const isApprover = user?.agents?.includes('approval');

  const refresh = async () => {
    try {
      const data = await listConversations(activeAgent);
      setConversations(data);
    } catch {
      /* backend might be down */
    }
  };

  const refreshPendingCount = useCallback(async () => {
    if (!isApprover) return;
    try {
      const pending = await getPendingReviews();
      setPendingCount(pending.length);
    } catch {
      /* ignore */
    }
  }, [isApprover]);

  useEffect(() => {
    refresh();
  }, [activeAgent, activeConversation]);

  // Poll pending count every 30s for approvers (WhatsApp-style badge)
  useEffect(() => {
    refreshPendingCount();
    if (!isApprover) return;
    const interval = setInterval(refreshPendingCount, 30000);
    return () => clearInterval(interval);
  }, [refreshPendingCount, isApprover]);

  const handleNew = async () => {
    const title = activeAgent === 'exam' ? 'New Exam' : 'New Chat';
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

  const showHistory = activeAgent === 'chat' || activeAgent === 'exam';

  return (
    <aside
      className={`${
        isOpen ? 'w-72' : 'w-12'
      } transition-all duration-200 bg-indigo-950 border-r border-indigo-900 flex flex-col overflow-hidden`}
    >
      {/* Brand + Toggle — always visible */}
      <div className="flex items-center gap-2 px-3 py-3 border-b border-indigo-800/50 shrink-0">
        {isOpen && (
          <>
            <div className="w-8 h-8 rounded-lg bg-white/10 flex items-center justify-center overflow-hidden shrink-0">
              <img
                src="/MCTE_logo.png"
                alt="MCTE"
                className="w-full h-full object-contain p-0.5"
                onError={(e) => {
                  e.currentTarget.style.display = 'none';
                  e.currentTarget.nextElementSibling.style.display = 'flex';
                }}
              />
              <Bot size={18} className="text-indigo-300" style={{ display: 'none' }} />
            </div>
            <span className="font-bold text-sm tracking-wide text-white truncate">EduQuest Ecosystem</span>
          </>
        )}
        <button
          onClick={toggle}
          className={`${isOpen ? 'ml-auto' : 'mx-auto'} p-1.5 rounded-md hover:bg-indigo-800 text-indigo-300 transition shrink-0`}
          title={isOpen ? 'Collapse sidebar' : 'Expand sidebar'}
        >
          {isOpen ? <PanelLeftClose size={18} /> : <PanelLeftOpen size={18} />}
        </button>
      </div>

      {isOpen && (
        <div className="flex flex-col flex-1 min-h-0">

          {/* Pending approval alert for approvers */}
          {isApprover && pendingCount > 0 && (
            <div
              onClick={() => setActiveAgent('approval')}
              className="mx-3 mt-3 flex items-center gap-2 px-3 py-2 bg-amber-500/20 border border-amber-500/40 rounded-lg cursor-pointer hover:bg-amber-500/30 transition shrink-0"
            >
              <Bell size={14} className="text-amber-400 animate-pulse shrink-0" />
              <span className="text-xs text-amber-300 font-medium">
                {pendingCount} paper{pendingCount > 1 ? 's' : ''} awaiting your review
              </span>
              <span className="ml-auto bg-amber-500 text-white text-[10px] font-bold rounded-full w-5 h-5 flex items-center justify-center shrink-0">
                {pendingCount > 9 ? '9+' : pendingCount}
              </span>
            </div>
          )}

          {/* ── Main scrollable area: 50% Agents + 50% History ── */}
          <div className="flex-1 flex flex-col min-h-0">

            {/* Agents section — 50% of flex space */}
            <div className={`${showHistory ? 'flex-[1_1_50%]' : 'flex-1'} flex flex-col min-h-0 overflow-hidden px-3 pt-4 pb-2`}>
              <p className="text-[11px] uppercase tracking-wider text-indigo-400/80 mb-2 px-1 shrink-0">
                Agents
              </p>
              <div className="flex-1 overflow-y-auto space-y-0.5 pr-0.5">
                {agents.map(({ id, label, icon: Icon }) => (
                  <button
                    key={id}
                    onClick={() => setActiveAgent(id)}
                    className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition relative ${
                      activeAgent === id
                        ? 'bg-indigo-500/30 text-white font-medium'
                        : 'hover:bg-indigo-800/60 text-indigo-200'
                    }`}
                  >
                    <Icon size={16} />
                    {label}
                    {id === 'approval' && isApprover && pendingCount > 0 && (
                      <span className="ml-auto bg-amber-500 text-white text-[10px] font-bold rounded-full w-4 h-4 flex items-center justify-center">
                        {pendingCount > 9 ? '9+' : pendingCount}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </div>

            {/* History section — 50% of flex space (only for chat/exam) */}
            {showHistory && (
              <div className="flex-[1_1_50%] flex flex-col min-h-0 overflow-hidden px-3 pt-2 pb-2 border-t border-indigo-800/30">
                <div className="flex items-center justify-between mb-2 px-1 shrink-0">
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
                <div className="flex-1 min-h-0 overflow-y-auto space-y-0.5">
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
          </div>

          {/* Admin button (only for admin users) */}
          {user?.role === 'admin' && (
            <div className="px-3 py-1 shrink-0">
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
          <div className="px-3 py-1 shrink-0">
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
            <div className="flex items-center justify-between">
              <button
                onClick={() => onOpenProfile?.()}
                className="flex items-center gap-2 min-w-0 hover:opacity-80 transition"
                title="View profile"
              >
                <div className="w-7 h-7 rounded-full bg-indigo-600 flex items-center justify-center shrink-0">
                  <User size={14} className="text-indigo-200" />
                </div>
                <div className="min-w-0 text-left">
                  <p className="text-xs text-white font-medium truncate">{user?.username}</p>
                  <p className="text-[10px] text-indigo-300/80 capitalize">{user?.role}</p>
                </div>
              </button>
              <button
                onClick={onLogout}
                className="p-1.5 rounded hover:bg-indigo-800 text-indigo-400 hover:text-red-400 transition"
                title="Sign out"
              >
                <LogOut size={14} />
              </button>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}
