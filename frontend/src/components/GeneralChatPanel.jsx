import React, { useState, useEffect, useRef } from 'react';
import { Send, Loader2, MessageSquare, Square, FileDown } from 'lucide-react';
import { sendGeneralChatStream, getMessages, createConversation } from '../api';
import MessageBubble from './MessageBubble';

export default function GeneralChatPanel({ conversationId, onNewConversation }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [streamContent, setStreamContent] = useState('');
  const abortRef = useRef(null);
  const activeConvRef = useRef(conversationId);
  const bottomRef = useRef(null);
  const textareaRef = useRef(null);

  // Auto-expand textarea height; show scrollbar once it exceeds MAX_H
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    const MAX_H = 160;
    el.style.height = 'auto';
    const newH = Math.min(el.scrollHeight, MAX_H);
    el.style.height = `${newH}px`;
    el.style.overflowY = el.scrollHeight > MAX_H ? 'auto' : 'hidden';
  }, [input]);

  useEffect(() => {
    if (conversationId !== activeConvRef.current) {
      // Conversation switched externally — abort any ongoing stream
      abortRef.current?.abort();
      setLoading(false);
      setStreamContent('');
    }
    activeConvRef.current = conversationId;
    if (!conversationId) {
      setMessages([]);
      return;
    }
    getMessages(conversationId).then(setMessages).catch(() => {});
  }, [conversationId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamContent]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;

    let convId = conversationId;
    if (!convId) {
      try {
        const conv = await createConversation('general', text.slice(0, 60));
        convId = conv.id;
        activeConvRef.current = convId;
        onNewConversation(convId);
      } catch (err) {
        setMessages((prev) => [
          ...prev,
          { id: Date.now().toString(), role: 'assistant', content: `⚠ Error: ${err.message}` },
        ]);
        return;
      }
    }

    setInput('');
    setMessages((prev) => [
      ...prev,
      { id: Date.now().toString(), role: 'user', content: text },
    ]);
    setLoading(true);
    setStreamContent('');

    const controller = new AbortController();
    abortRef.current = controller;
    const targetConvId = convId;

    try {
      let fullResponse = '';
      await sendGeneralChatStream(convId, text, (data) => {
        if (controller.signal.aborted || activeConvRef.current !== targetConvId) return;
        if (data.error) {
          fullResponse = `⚠ Error: ${data.error}`;
          setStreamContent(fullResponse);
          return;
        }
        if (data.token) {
          fullResponse += data.token;
          setStreamContent(fullResponse);
        }
      }, controller.signal);

      if (activeConvRef.current === targetConvId && fullResponse) {
        setMessages((prev) => [
          ...prev,
          { id: (Date.now() + 1).toString(), role: 'assistant', content: fullResponse },
        ]);
      }
    } catch (err) {
      if (!controller.signal.aborted && activeConvRef.current === targetConvId) {
        setMessages((prev) => [
          ...prev,
          { id: (Date.now() + 1).toString(), role: 'assistant', content: `⚠ Error: ${err.message}` },
        ]);
      }
    } finally {
      if (activeConvRef.current === targetConvId) {
        setLoading(false);
        setStreamContent('');
      }
      abortRef.current = null;
    }
  };

  const handleStop = () => {
    abortRef.current?.abort();
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleExportPdf = () => {
    if (!messages.length) return;
    const printWindow = window.open('', '_blank');
    const rows = messages.map((m) => {
      const label = m.role === 'user' ? 'You' : 'AI Assistant';
      return `<div class="msg ${m.role}"><strong>${label}:</strong><br/><pre>${m.content.replace(/</g, '&lt;')}</pre></div>`;
    }).join('');
    printWindow.document.write(`<!DOCTYPE html><html><head><title>Chat Export</title>
      <style>
        body{font-family:Arial,sans-serif;padding:24px;color:#111;max-width:800px;margin:0 auto;}
        h2{color:#1a1a2e;}
        .msg{margin-bottom:16px;padding:10px 14px;border-radius:8px;}
        .msg.user{background:#dbeafe;text-align:right;}
        .msg.assistant{background:#f3f4f6;}
        pre{white-space:pre-wrap;font-family:inherit;margin:6px 0 0;}
        @media print{body{padding:0}}
      </style></head><body>
      <h2>Chat Conversation Export</h2>
      <p style="color:#888;font-size:12px;">Exported on ${new Date().toLocaleString()}</p>
      ${rows}
      </body></html>`);
    printWindow.document.close();
    printWindow.focus();
    setTimeout(() => { printWindow.print(); }, 300);
  };

  return (
    <div className="flex-1 flex flex-col h-full">
      {/* Header */}
      <header className="shrink-0 flex items-center justify-between gap-2 px-6 py-4 border-b border-indigo-100 bg-gradient-to-r from-white to-indigo-50/60">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-violet-100 flex items-center justify-center">
            <MessageSquare size={16} className="text-violet-600" />
          </div>
          <h1 className="text-base font-semibold text-slate-800">General AI Chat</h1>
          <span className="text-[11px] bg-violet-100 text-violet-600 px-2 py-0.5 rounded-full font-medium">No RAG</span>
        </div>
        {messages.length > 0 && (
          <button
            onClick={handleExportPdf}
            title="Export conversation to PDF"
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-indigo-50 hover:bg-indigo-100 text-indigo-600 border border-indigo-200 rounded-lg transition"
          >
            <FileDown size={13} />
            Export PDF
          </button>
        )}
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-gray-500">
            <MessageSquare size={48} strokeWidth={1} />
            <p className="mt-3 text-sm">Ask anything — powered by AI, no documents needed.</p>
          </div>
        )}
        {messages.map((m) => (
          <MessageBubble key={m.id} role={m.role} content={m.content} />
        ))}

        {/* Streaming indicator */}
        {loading && !streamContent && (
          <div className="flex items-center gap-2 text-gray-500 text-sm mb-4">
            <Loader2 size={16} className="animate-spin" />
            Thinking…
          </div>
        )}
        {loading && streamContent && (
          <>
            <MessageBubble role="assistant" content={streamContent} />
            <div className="flex items-center gap-1.5 text-xs text-violet-500 mb-3 ml-1">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-violet-500 animate-pulse" />
              Answering…
            </div>
          </>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="shrink-0 border-t border-slate-200 px-6 py-4">
        <div className="flex items-end gap-2 bg-white rounded-xl px-4 py-2 border border-slate-200 focus-within:border-violet-500 shadow-sm transition">
          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a message…"
            className="flex-1 bg-transparent resize-none outline-none text-sm text-slate-800 placeholder-slate-400 max-h-40 py-1.5"
          />
          {loading ? (
            <button
              onClick={handleStop}
              title="Stop generating"
              className="p-2 rounded-lg bg-red-100 hover:bg-red-200 text-red-600 transition"
            >
              <Square size={16} />
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!input.trim()}
              className="p-2 rounded-lg bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed transition"
            >
              <Send size={16} className="text-white" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
