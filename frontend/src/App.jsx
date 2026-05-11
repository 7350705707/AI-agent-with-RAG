import React, { useState, useEffect, useRef, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import ChatPanel from './views/ChatPanel';
import ExamPanel from './views/ExamPanel';
import AdminPanel from './views/AdminPanel';
import KnowledgePanel from './views/KnowledgePanel';
import LoginPage from './views/LoginPage';
import AboutPage from './views/AboutPage';
import { getStoredUser, logout as apiLogout, getToken } from './api';

export default function App() {
  const [user, setUser] = useState(() => getStoredUser());
  const [activeAgent, setActiveAgent] = useState('chat');
  const [activeConversation, setActiveConversation] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const isLoggedIn = !!(getToken() && user);

  // ── Session inactivity timeout (30 minutes) ──────────────────────────
  const INACTIVITY_MS = 30 * 60 * 1000;
  const inactivityTimer = useRef(null);

  const resetInactivityTimer = useCallback(() => {
    if (inactivityTimer.current) clearTimeout(inactivityTimer.current);
    if (!isLoggedIn) return;
    inactivityTimer.current = setTimeout(() => {
      apiLogout();
      setUser(null);
      setActiveAgent('chat');
      setActiveConversation(null);
    }, INACTIVITY_MS);
  }, [isLoggedIn]);

  useEffect(() => {
    const events = ['mousemove', 'keydown', 'mousedown', 'touchstart', 'scroll'];
    events.forEach((e) => window.addEventListener(e, resetInactivityTimer, { passive: true }));
    resetInactivityTimer();
    return () => {
      events.forEach((e) => window.removeEventListener(e, resetInactivityTimer));
      if (inactivityTimer.current) clearTimeout(inactivityTimer.current);
    };
  }, [resetInactivityTimer]);

  // All users must be logged in to access the application
  if (!isLoggedIn) {
    return (
      <LoginPage
        onLogin={(u) => { setUser(u); setActiveAgent('chat'); }}
      />
    );
  }

  const allowedAgents = Array.from(new Set(['chat', ...(user.agents || [])]));

  const handleSetAgent = (agent) => {
    setActiveAgent(agent);
    setActiveConversation(null);
  };

  const handleLogout = () => {
    apiLogout();
    setUser(null);
    setActiveAgent('chat');
    setActiveConversation(null);
  };

  const renderPanel = () => {
    if (activeAgent === 'about') {
      return <AboutPage />;
    }
    if (activeAgent === 'admin' && user.role === 'admin') {
      return <AdminPanel />;
    }
    if (activeAgent === 'knowledge' && allowedAgents.includes('knowledge')) {
      return <KnowledgePanel />;
    }
    if (activeAgent === 'exam' && allowedAgents.includes('exam')) {
      return (
        <ExamPanel
          conversationId={activeConversation}
          onNewConversation={setActiveConversation}
        />
      );
    }
    if (activeAgent === 'chat' && allowedAgents.includes('chat')) {
      return (
        <ChatPanel
          conversationId={activeConversation}
          onNewConversation={setActiveConversation}
        />
      );
    }
    return (
      <div className="flex-1 flex items-center justify-center text-gray-600 text-sm">
        No agents assigned. Contact your admin.
      </div>
    );
  };

  return (
    <div className="flex h-screen overflow-hidden bg-indigo-50 text-slate-800">
      <Sidebar
        activeAgent={activeAgent}
        setActiveAgent={handleSetAgent}
        activeConversation={activeConversation}
        setActiveConversation={setActiveConversation}
        isOpen={sidebarOpen}
        toggle={() => setSidebarOpen(!sidebarOpen)}
        user={user}
        onLogout={handleLogout}
      />

      <main className="flex-1 flex flex-col min-w-0">
        {renderPanel()}
      </main>
    </div>
  );
}
