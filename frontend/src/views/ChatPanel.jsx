import React, { useState, useEffect, useRef } from 'react';
import { Send, Loader2, MessageSquare, FileDown, Square, Wrench, Paperclip, X, ChevronDown, ChevronUp } from 'lucide-react';
import { sendAgenticChatStream, getMessages, createConversation, getKnowledgeDocUrl, uploadFile } from '../api';
import MessageBubble from '../components/MessageBubble';

export default function ChatPanel({ conversationId, onNewConversation }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [streamContent, setStreamContent] = useState('');
  const [thinkingStep, setThinkingStep] = useState('');
  const [uploadedFiles, setUploadedFiles] = useState([]); // [{file_id, filename}]
  const [uploading, setUploading] = useState(false);
  const [expandedSnippets, setExpandedSnippets] = useState({});
  const fileInputRef = useRef(null);
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

  // Load messages when conversation changes — abort any ongoing stream
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

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamContent]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;

    let convId = conversationId;
    const fileIds = uploadedFiles.map((f) => f.file_id);

    // Auto-create conversation if none selected
    if (!convId) {
      try {
        const conv = await createConversation('chat', text.slice(0, 60));
        convId = conv.id;
        activeConvRef.current = convId;
        onNewConversation(convId);
      } catch (err) {
        setMessages((prev) => [
          ...prev,
          { id: Date.now().toString(), role: 'assistant', content: `⚠ Error creating conversation: ${err.message}` },
        ]);
        return;
      }
    }

    setInput('');
    setUploadedFiles([]);
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
      let sources = [];
      await sendAgenticChatStream(convId, text, (data) => {
        if (controller.signal.aborted || activeConvRef.current !== targetConvId) return;
        if (data.queued) {
          setStreamContent('\u23F3 Waiting for model to be available\u2026');
          return;
        }
        if (data.error) {
          fullResponse = `\u26A0 Error: ${data.error}`;
          setStreamContent(fullResponse);
          setThinkingStep('');
          return;
        }
        if (data.thinking) {
          setThinkingStep(data.thinking);
          return;
        }
        if (data.sources) {
          sources = data.sources;
        }
        if (data.token) {
          setThinkingStep('');
          if (!fullResponse) setStreamContent('');  // clear queued message
          fullResponse += data.token;
          setStreamContent(fullResponse);
        }
      }, controller.signal, fileIds);

      if (fullResponse && activeConvRef.current === targetConvId) {
        setMessages((prev) => [
          ...prev,
          { id: (Date.now() + 1).toString(), role: 'assistant', content: fullResponse, sources },
        ]);
      }
    } catch (err) {
      if (activeConvRef.current === targetConvId && !controller.signal.aborted) {
        setMessages((prev) => [
          ...prev,
          {
            id: (Date.now() + 1).toString(),
            role: 'assistant',
            content: `⚠ Error: ${err.message}`,
          },
        ]);
      }
    } finally {
      if (activeConvRef.current === targetConvId) {
        setLoading(false);
        setStreamContent('');
        setThinkingStep('');
      }
      abortRef.current = null;
    }
  };

  const handleStop = () => {
    abortRef.current?.abort();
    setThinkingStep('');
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const res = await uploadFile(file, conversationId);
      setUploadedFiles((prev) => [...prev, { file_id: res.file_id, filename: res.filename }]);
    } catch (err) {
      alert(`Upload failed: ${err.message}`);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const removeUploadedFile = (fileId) => {
    setUploadedFiles((prev) => prev.filter((f) => f.file_id !== fileId));
  };

  const toggleSnippet = (key) => {
    setExpandedSnippets((prev) => ({ ...prev, [key]: !prev[key] }));
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
      const srcHtml = m.sources && m.sources.length
        ? `<p class="sources">ðŸ“š Sources: ${m.sources.map((s) => s.filename).join(', ')}</p>`
        : '';
      return `<div class="msg ${m.role}"><strong>${label}:</strong><br/><pre>${m.content.replace(/</g, '&lt;')}</pre>${srcHtml}</div>`;
    }).join('');
    printWindow.document.write(`<!DOCTYPE html><html><head><title>Chat Export</title>
      <style>
        body{font-family:Arial,sans-serif;padding:24px;color:#111;max-width:800px;margin:0 auto;}
        h2{color:#1a1a2e;}
        .msg{margin-bottom:16px;padding:10px 14px;border-radius:8px;}
        .msg.user{background:#dbeafe;text-align:right;}
        .msg.assistant{background:#f3f4f6;}
        pre{white-space:pre-wrap;font-family:inherit;margin:6px 0 0;}
        .sources{font-size:12px;color:#555;margin-top:4px;}
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
          <div className="w-8 h-8 rounded-lg bg-blue-100 flex items-center justify-center">
            <MessageSquare size={16} className="text-blue-600" />
          </div>
          <h1 className="text-base font-semibold text-slate-800">SetuAI Chat</h1>
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
          <div className="flex flex-col items-center justify-center h-full text-gray-600">
            <MessageSquare size={48} strokeWidth={1} />
            <p className="mt-3 text-sm">Start a conversation…</p>
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id}>
            <MessageBubble role={m.role} content={m.content} />
            {m.sources && m.sources.length > 0 && (
              <div className="ml-11 -mt-2 mb-4 flex flex-col gap-1">
                <span className="text-xs text-gray-500">📚 Sources:</span>
                {m.sources.map((s, si) => {
                  const key = `${m.id}-${si}`;
                  return (
                    <div key={key} className="text-xs">
                      <div className="flex items-center gap-1">
                        {s.doc_id ? (
                          <a
                            href={getKnowledgeDocUrl(s.doc_id)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-400 hover:text-blue-300 underline underline-offset-2"
                          >
                            {s.filename}
                          </a>
                        ) : (
                          <span className="text-blue-400">{s.filename}</span>
                        )}
                        {s.snippet && (
                          <button
                            onClick={() => toggleSnippet(key)}
                            className="text-gray-400 hover:text-gray-300 flex items-center gap-0.5"
                            title="Show excerpt"
                          >
                            {expandedSnippets[key] ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
                          </button>
                        )}
                      </div>
                      {s.snippet && expandedSnippets[key] && (
                        <div className="mt-1 ml-2 px-2 py-1.5 bg-slate-50 border border-slate-200 rounded text-gray-600 italic text-xs leading-relaxed max-w-lg">
                          "{s.snippet}…"
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div className="flex flex-col gap-1 mb-4">
            {thinkingStep ? (
              <div className="flex items-center gap-2 text-indigo-500 text-xs bg-indigo-50 border border-indigo-100 rounded-lg px-3 py-2 max-w-xs">
                <Wrench size={13} className="animate-pulse shrink-0" />
                <span className="truncate font-mono">{thinkingStep}</span>
              </div>
            ) : !streamContent ? (
              <div className="flex items-center gap-2 text-gray-500 text-sm">
                <Loader2 size={16} className="animate-spin" />
                Thinking…
              </div>
            ) : null}
          </div>
        )}
        {loading && streamContent && (
          <>
            <MessageBubble role="assistant" content={streamContent} />
            <div className="flex items-center gap-1.5 text-xs text-blue-500 mb-3 ml-1">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
              Answering…
            </div>
          </>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="shrink-0 border-t border-slate-200 px-6 py-4">
        {/* Uploaded file chips */}
        {uploadedFiles.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-2">
            {uploadedFiles.map((f) => (
              <span key={f.file_id} className="flex items-center gap-1 px-2 py-0.5 bg-blue-50 border border-blue-200 rounded-full text-xs text-blue-700">
                <Paperclip size={10} />
                {f.filename}
                <button onClick={() => removeUploadedFile(f.file_id)} className="hover:text-red-500 ml-0.5">
                  <X size={10} />
                </button>
              </span>
            ))}
          </div>
        )}
        <div className="flex items-end gap-2 bg-white rounded-xl px-4 py-2 border border-slate-200 focus-within:border-blue-500 shadow-sm transition">
          <input ref={fileInputRef} type="file" accept=".pdf,.docx,.pptx" className="hidden" onChange={handleFileUpload} />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading || loading}
            title="Attach a file"
            className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600 disabled:opacity-40 transition"
          >
            {uploading ? <Loader2 size={15} className="animate-spin" /> : <Paperclip size={15} />}
          </button>
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
              disabled={loading || !input.trim()}
              className="p-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed transition"
            >
              <Send size={16} className="text-white" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

