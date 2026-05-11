import React, { useState, useEffect, useRef } from 'react';
import {
  Send,
  Loader2,
  FileText,
  Upload,
  CheckCircle2,
  XCircle,
  File,
  FileDown,
  Square,
  CheckSquare,
  ChevronDown,
} from 'lucide-react';
import { sendExamStream, getMessages, createConversation, uploadFile, renameConversation } from '../api';
import MessageBubble from '../components/MessageBubble';

const ACCEPT = '.pdf,.docx,.pptx';

// -- Helpers -----------------------------------------------------------------

function escapeHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function renderExamHeader(header = {}) {
  const { subjectName, instructorName, institution, examDate, totalMarks, timeAllowed } = header;
  const hasAny = subjectName || instructorName || institution || examDate || totalMarks || timeAllowed;
  if (!hasAny) return '';
  const cell = (label, value) => value
    ? `<tr>
        <td style="padding:6px 12px;font-weight:600;background:#f3f4f6;color:#374151;width:26%;white-space:nowrap;border:1px solid #d1d5db;">${escapeHtml(label)}</td>
        <td style="padding:6px 12px;border:1px solid #d1d5db;">${escapeHtml(value)}</td>
       </tr>`
    : '';
  const instRow = institution
    ? `<tr><td colspan="2" style="padding:10px 12px;font-size:15px;font-weight:700;text-align:center;background:#f9fafb;border:1px solid #d1d5db;">${escapeHtml(institution)}</td></tr>`
    : '';
  return `<table style="width:100%;border-collapse:collapse;margin-bottom:24px;font-size:13px;">
    ${instRow}
    ${cell('Subject', subjectName)}
    ${cell('Instructor', instructorName)}
    ${cell('Date', examDate)}
    ${cell('Total Marks', totalMarks)}
    ${cell('Time Allowed', timeAllowed)}
  </table>`;
}

function buildPrompt(mcqCount, tfCount, fitbCount, extra, ratios) {
  const parts = [];
  if (mcqCount > 0) parts.push(`${mcqCount} MCQ questions`);
  if (tfCount > 0) parts.push(`${tfCount} True or False questions`);
  if (fitbCount > 0) parts.push(`${fitbCount} Fill in the Blanks questions`);
  const { easy, medium, hard } = ratios;
  const ratioStr = `(Easy ${easy}% / Medium ${medium}% / Hard ${hard}%)`;
  const base = parts.length
    ? `Generate an exam paper ${ratioStr} with ${parts.join(', ')}.`
    : `Generate an exam paper ${ratioStr}.`;
  return extra.trim() ? `${base} Additional instructions: ${extra.trim()}` : base;
}

function renderQuestionsToHtml(questions, includeAnswerKey = true) {
  const sections = { mcq: [], true_false: [], fill_blank: [] };
  questions.forEach((q) => { if (sections[q.type]) sections[q.type].push(q); });

  // Renumber sequentially within each section (Q1, Q2, Q3…) regardless of original numbers
  const numbered = {};
  Object.entries(sections).forEach(([type, qs]) => {
    numbered[type] = qs.map((q, i) => ({ ...q, exportNum: i + 1 }));
  });

  let html = '';
  const sectionLabels = {
    mcq: 'Section A: Multiple Choice Questions',
    true_false: 'Section B: True / False',
    fill_blank: 'Section C: Fill in the Blanks',
  };

  Object.entries(numbered).forEach(([type, qs]) => {
    if (!qs.length) return;
    html += `<h2 style="margin-top:24px;font-size:15px;">${sectionLabels[type]}</h2>`;
    qs.forEach((q) => {
      html += `<p style="margin:10px 0 4px;"><b>Q${q.exportNum}.</b> ${q.text.replace(/</g, '&lt;')}</p>`;
      if (type === 'mcq' && q.options.length) {
        q.options.forEach((opt) => {
          html += `<p style="margin:2px 0 2px 20px;">${opt.replace(/</g, '&lt;')}</p>`;
        });
      }
    });
  });

  if (includeAnswerKey && questions.some((q) => q.answer)) {
    html += `<h2 style="margin-top:28px;font-size:15px;">Answer Key</h2>`;
    ['mcq', 'true_false', 'fill_blank'].forEach((type) => {
      const qs = numbered[type].filter((q) => q.answer);
      if (!qs.length) return;
      const labels = { mcq: 'MCQ', true_false: 'True/False', fill_blank: 'Fill in Blanks' };
      html += `<p style="margin:6px 0;"><b>${labels[type]}:</b> ${qs.map((q) => `${q.exportNum}. ${q.answer}`).join(' | ')}</p>`;
    });
  }
  return html;
}

function exportSelectedPdf(questions, title, header = {}) {
  const win = window.open('', '_blank');
  const headerHtml = renderExamHeader(header);
  const bodyHtml = renderQuestionsToHtml(questions, false);
  win.document.write(`<!DOCTYPE html><html><head><title>${title}</title>
    <style>
      body{font-family:Arial,sans-serif;padding:32px;color:#111;max-width:860px;margin:0 auto;line-height:1.6;}
      h1{font-size:18px;margin-bottom:4px;}h2{font-size:15px;}
      .meta{color:#888;font-size:12px;margin-bottom:24px;}
      @media print{body{padding:0}}
    </style></head><body>
    <h1>${title}</h1>
    ${headerHtml}
    ${bodyHtml}
    </body></html>`);
  win.document.close();
  win.focus();
  setTimeout(() => { win.print(); }, 300);
}

function exportSelectedJson(questions, title, header = {}) {
  const sections = { mcq: [], true_false: [], fill_blank: [] };
  questions.forEach((q) => { if (sections[q.type]) sections[q.type].push(q); });
  const data = {
    title,
    header,
    exported_at: new Date().toISOString(),
    sections: Object.fromEntries(
      Object.entries(sections).map(([type, qs]) => [
        type,
        qs.map((q, i) => ({
          number: i + 1,
          original_number: q.number,
          text: q.text,
          ...(q.options && q.options.length ? { options: q.options } : {}),
          ...(q.answer ? { answer: q.answer } : {}),
        })),
      ])
    ),
  };
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${title.replace(/\s+/g, '_')}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function exportSelectedDoc(questions, title, header = {}) {
  const headerHtml = renderExamHeader(header);
  const bodyHtml = renderQuestionsToHtml(questions);
  const html = `<html xmlns:o='urn:schemas-microsoft-com:office:office'
    xmlns:w='urn:schemas-microsoft-com:office:word'
    xmlns='http://www.w3.org/TR/REC-html40'>
    <head><meta charset='utf-8'><title>${title}</title>
    <style>body{font-family:Arial,sans-serif;padding:32px;line-height:1.6;}</style></head>
    <body><h1>${title}</h1>
    ${headerHtml}
    ${bodyHtml}
    </body></html>`;
  const blob = new Blob(['\ufeff', html], { type: 'application/msword' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${title}.doc`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// -- Structured Questions Panel -----------------------------------------------

function QuestionCard({ q, checked, onToggle }) {
  return (
    <div
      className={`flex gap-3 px-4 py-3 rounded-lg border cursor-pointer transition ${
        checked
          ? 'border-emerald-300 bg-emerald-50'
          : 'border-indigo-100 bg-white hover:border-indigo-200 hover:bg-indigo-50/40'
      }`}
      onClick={onToggle}
    >
      <div className="mt-0.5 shrink-0">
        {checked
          ? <CheckSquare size={16} className="text-emerald-500" />
          : <Square size={16} className="text-slate-300" />}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-slate-700">
          <span className="font-medium text-slate-400 mr-1">Q{q.number}.</span>
          {q.text}
        </p>
        {q.type === 'mcq' && q.options.length > 0 && (
          <div className="mt-1.5 grid grid-cols-2 gap-x-4 gap-y-0.5">
            {q.options.map((opt, i) => (
              <p key={i} className="text-xs text-slate-400">{opt}</p>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function StructuredExamView({ questions, onExportPdf, onExportDoc, onExportJson }) {
  const [selected, setSelected] = useState(() => new Set(questions.map((q) => q.number)));

  const sections = [
    { type: 'mcq', label: 'Section A: Multiple Choice Questions' },
    { type: 'true_false', label: 'Section B: True / False' },
    { type: 'fill_blank', label: 'Section C: Fill in the Blanks' },
  ];

  const toggle = (num) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(num) ? next.delete(num) : next.add(num);
      return next;
    });
  };

  const toggleSection = (type) => {
    const nums = questions.filter((q) => q.type === type).map((q) => q.number);
    const allChecked = nums.every((n) => selected.has(n));
    setSelected((prev) => {
      const next = new Set(prev);
      nums.forEach((n) => (allChecked ? next.delete(n) : next.add(n)));
      return next;
    });
  };

  const selectedQuestions = questions.filter((q) => selected.has(q.number));

  return (
    <div className="mt-4 rounded-xl border border-emerald-200 bg-white overflow-hidden shadow-sm">
      <div className="flex items-center justify-between gap-3 px-5 py-3 bg-emerald-50 border-b border-emerald-100">
        <div className="flex items-center gap-2">
          <CheckSquare size={15} className="text-emerald-500" />
          <span className="text-sm font-medium text-emerald-700">
            Select questions to export ({selected.size}/{questions.length})
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => onExportPdf(selectedQuestions)}
            disabled={!selected.size}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-emerald-50 hover:bg-emerald-100 text-emerald-600 border border-emerald-200 rounded-lg transition disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <FileDown size={12} /> PDF
          </button>
          <button
            onClick={() => onExportDoc(selectedQuestions)}
            disabled={!selected.size}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-blue-50 hover:bg-blue-100 text-blue-600 border border-blue-200 rounded-lg transition disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <FileDown size={12} /> DOC
          </button>
          <button
            onClick={() => onExportJson(selectedQuestions)}
            disabled={!selected.size}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-violet-50 hover:bg-violet-100 text-violet-600 border border-violet-200 rounded-lg transition disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <FileDown size={12} /> JSON
          </button>
        </div>
      </div>

      <div className="px-5 py-4 space-y-6 max-h-[60vh] overflow-y-auto">
        {sections.map(({ type, label }) => {
          const qs = questions.filter((q) => q.type === type);
          if (!qs.length) return null;
          const sectionNums = qs.map((q) => q.number);
          const allChecked = sectionNums.every((n) => selected.has(n));
          return (
            <div key={type}>
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs uppercase tracking-wider text-slate-500 font-semibold">{label}</p>
                <button
                  onClick={() => toggleSection(type)}
                  className="text-xs text-emerald-600 hover:text-emerald-800 transition"
                >
                  {allChecked ? 'Deselect all' : 'Select all'}
                </button>
              </div>
              <div className="space-y-2">
                {qs.map((q) => (
                  <QuestionCard
                    key={q.number}
                    q={q}
                    checked={selected.has(q.number)}
                    onToggle={() => toggle(q.number)}
                  />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// -- Main Component -----------------------------------------------------------

export default function ExamPanel({ conversationId, onNewConversation }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [mcqCount, setMcqCount] = useState(10);
  const [tfCount, setTfCount] = useState(10);
  const [fitbCount, setFitbCount] = useState(10);
  const [easyRatio, setEasyRatio] = useState(50);
  const [mediumRatio, setMediumRatio] = useState(30);
  const [hardRatio, setHardRatio] = useState(20);
  const [loading, setLoading] = useState(false);
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [streamContent, setStreamContent] = useState('');
  const [structuredQuestions, setStructuredQuestions] = useState(null);
  const [showExportPanel, setShowExportPanel] = useState(false);
  // Exam paper header fields
  const [subjectName, setSubjectName] = useState('');
  const [instructorName, setInstructorName] = useState('');
  const [institution, setInstitution] = useState('');
  const [examDate, setExamDate] = useState(new Date().toISOString().slice(0, 10));
  const [totalMarks, setTotalMarks] = useState('');
  const [timeAllowed, setTimeAllowed] = useState('');
  const [showHeaderForm, setShowHeaderForm] = useState(false);
  const abortRef = useRef(null);
  const activeConvRef = useRef(conversationId);
  const bottomRef = useRef(null);
  const fileInputRef = useRef(null);
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
      setInput('');
      setStructuredQuestions(null);
      setShowExportPanel(false);
      return;
    }
    getMessages(conversationId).then(setMessages).catch(() => {});
    // Restore saved structured questions from localStorage
    try {
      const saved = localStorage.getItem(`exam_sq_${conversationId}`);
      if (saved) {
        setStructuredQuestions(JSON.parse(saved));
        setShowExportPanel(false);
      } else {
        setStructuredQuestions(null);
        setShowExportPanel(false);
      }
    } catch {
      setStructuredQuestions(null);
      setShowExportPanel(false);
    }
  }, [conversationId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamContent, structuredQuestions]);

  const handleFileSelect = async (e) => {
    const selected = Array.from(e.target.files);
    if (!selected.length) return;
    setUploading(true);
    for (const file of selected) {
      setFiles((prev) => [...prev, { file, status: 'uploading', fileId: null, error: null }]);
      try {
        const result = await uploadFile(file);
        setFiles((prev) =>
          prev.map((f) => f.file === file ? { ...f, status: 'done', fileId: result.file_id } : f)
        );
      } catch (err) {
        setFiles((prev) =>
          prev.map((f) => f.file === file ? { ...f, status: 'error', error: err.message } : f)
        );
      }
    }
    setUploading(false);
    e.target.value = '';
  };

  const removeFile = (index) => setFiles((prev) => prev.filter((_, i) => i !== index));

  const handleSend = async () => {
    if (loading) return;

    const doneFiles = files.filter((f) => f.status === 'done');
    const fileIds = doneFiles.map((f) => f.fileId);
    const fileTitle = doneFiles.length > 0
      ? doneFiles.map((f) => f.file.name.replace(/\.[^.]+$/, '')).join(', ')
      : '';

    // First message: include question counts + difficulty. Follow-up: send user text only.
    const isFirstMessage = messages.length === 0;
    const ratios = { easy: easyRatio, medium: mediumRatio, hard: hardRatio };
    const combinedPrompt = isFirstMessage
      ? buildPrompt(mcqCount, tfCount, fitbCount, input, ratios)
      : (input.trim() || 'Continue the exam paper.');

    let convId = conversationId;
    if (!convId) {
      const title = fileTitle || combinedPrompt.slice(0, 60);
      try {
        const conv = await createConversation('exam', title);
        convId = conv.id;
        activeConvRef.current = conv.id;
        onNewConversation(convId);
      } catch (err) {
        setMessages((prev) => [
          ...prev,
          { id: Date.now().toString(), role: 'assistant', content: `⚠ Error creating conversation: ${err.message}` },
        ]);
        return;
      }
    } else if (fileTitle) {
      renameConversation(convId, fileTitle).catch(() => {});
    }

    setInput('');
    setFiles([]);
    setStructuredQuestions(null);
    setShowExportPanel(false);
    setMessages((prev) => [
      ...prev,
      { id: Date.now().toString(), role: 'user', content: combinedPrompt },
    ]);
    setLoading(true);
    setStreamContent('');

    const controller = new AbortController();
    abortRef.current = controller;
    const targetConvId = convId;

    try {
      let finalContent = '';
      await sendExamStream(
        convId,
        combinedPrompt,
        fileIds,
        (data) => {
          if (controller.signal.aborted) return;
          if (activeConvRef.current !== targetConvId) return;

          const { step, label, content, questions } = data;

          if (step === 'queued' || data.queued) {
            setStreamContent('\u23F3 Waiting for model to be available\u2026');
            return;
          }

          if (step === 'error') {
            setStreamContent('');
            setMessages((prev) => [
              ...prev,
              { id: (Date.now() + 1).toString(), role: 'assistant', content: `⚠ Error: ${label}` },
            ]);
            return;
          }

          if (step === 'structured' && questions && questions.length) {
            setStructuredQuestions(questions);
            // Persist so it survives page reload
            try { localStorage.setItem(`exam_sq_${targetConvId}`, JSON.stringify(questions)); } catch {}
            return;
          }

          if (content) {
            setStreamContent(content);
            finalContent = content;
          }
        },
        { mcq_count: mcqCount, tf_count: tfCount, fitb_count: fitbCount },
        controller.signal,
      );

      if (finalContent && !controller.signal.aborted && activeConvRef.current === targetConvId) {
        setMessages((prev) => [
          ...prev,
          { id: (Date.now() + 1).toString(), role: 'assistant', content: finalContent },
        ]);
      } else if (controller.signal.aborted && finalContent && activeConvRef.current === targetConvId) {
        setMessages((prev) => [
          ...prev,
          { id: (Date.now() + 1).toString(), role: 'assistant', content: finalContent },
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

  const exportAllPdf = () => {
    const assistantMsgs = messages.filter((m) => m.role === 'assistant');
    if (!assistantMsgs.length) return;
    const win = window.open('', '_blank');
    const headerHtml = renderExamHeader({ subjectName, instructorName, institution, examDate, totalMarks, timeAllowed });
    const sections = assistantMsgs.map((m, i) =>
      `<h2>Exam Paper ${i + 1}</h2><pre>${m.content.replace(/</g, '&lt;')}</pre>`
    ).join('<hr/>');
    win.document.write(`<!DOCTYPE html><html><head><title>Exam Papers</title>
      <style>body{font-family:Arial,sans-serif;padding:32px;max-width:860px;margin:0 auto;line-height:1.6;}
      h2{font-size:16px;}pre{white-space:pre-wrap;font-size:14px;}hr{border-top:1px solid #ddd;margin:24px 0;}
      .meta{color:#888;font-size:12px;margin-bottom:24px;}@media print{body{padding:0}}</style></head><body>
      <h1>Exam Papers Export</h1>${headerHtml}
      ${sections}</body></html>`);
    win.document.close();
    win.focus();
    setTimeout(() => { win.print(); }, 300);
  };

  const exportAllDoc = () => {
    const assistantMsgs = messages.filter((m) => m.role === 'assistant');
    if (!assistantMsgs.length) return;
    const headerHtml = renderExamHeader({ subjectName, instructorName, institution, examDate, totalMarks, timeAllowed });
    const sections = assistantMsgs.map((m, i) =>
      `<h2>Exam Paper ${i + 1}</h2><pre>${m.content.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre><hr/>`
    ).join('');
    const html = `<html xmlns:o='urn:schemas-microsoft-com:office:office'
      xmlns:w='urn:schemas-microsoft-com:office:word'
      xmlns='http://www.w3.org/TR/REC-html40'>
      <head><meta charset='utf-8'><title>Exam Papers</title>
      <style>body{font-family:Arial,sans-serif;padding:32px;line-height:1.6;}pre{white-space:pre-wrap;font-size:13pt;}hr{border:1px solid #ccc;margin:24px 0;}</style></head>
      <body><h1>Exam Papers Export</h1>${headerHtml}
      ${sections}</body></html>`;
    const blob = new Blob(['\ufeff', html], { type: 'application/msword' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `Exam_Papers_${new Date().toISOString().slice(0, 10)}.doc`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const hasAssistantMessages = messages.some((m) => m.role === 'assistant');

  return (
    <div className="flex-1 flex flex-col h-full">
      {/* Header */}
      <header className="shrink-0 flex items-center justify-between gap-2 px-6 py-4 border-b border-emerald-100 bg-gradient-to-r from-white to-emerald-50/60">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-emerald-100 flex items-center justify-center">
            <FileText size={16} className="text-emerald-600" />
          </div>
          <h1 className="text-base font-semibold text-slate-800">Exam Paper Generator</h1>
        </div>
        {hasAssistantMessages && (
          <div className="flex items-center gap-2">
            <button
              onClick={exportAllPdf}
              title="Export all exam papers to PDF"
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-emerald-50 hover:bg-emerald-100 text-emerald-600 border border-emerald-200 rounded-lg transition"
            >
              <FileDown size={13} /> PDF
            </button>
            <button
              onClick={exportAllDoc}
              title="Download all exam papers as Word document"
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-blue-50 hover:bg-blue-100 text-blue-600 border border-blue-200 rounded-lg transition"
            >
              <FileDown size={13} /> DOC
            </button>
          </div>
        )}
      </header>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-gray-600">
            <FileText size={48} strokeWidth={1} />
            <p className="mt-3 text-sm">Upload documents and set your exam format below.</p>
          </div>
        )}

        {messages.map((m) => (
          <div key={m.id}>
            <MessageBubble role={m.role} content={m.content} />
          </div>
        ))}

        {/* Structured question export button — shown after questions are generated */}
        {structuredQuestions && structuredQuestions.length > 0 && (
          <div className="my-3">
            <button
              onClick={() => setShowExportPanel((v) => !v)}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium transition shadow-sm"
            >
              <FileDown size={15} />
              {showExportPanel ? 'Hide Export' : 'Export Questions'}
            </button>
          </div>
        )}

        {/* Structured question selector — only visible after clicking Export */}
        {structuredQuestions && structuredQuestions.length > 0 && showExportPanel && (
          <StructuredExamView
            key={structuredQuestions.length}
            questions={structuredQuestions}
            onExportPdf={(qs) => exportSelectedPdf(qs, 'Exam Paper', { subjectName, instructorName, institution, examDate, totalMarks, timeAllowed })}
            onExportDoc={(qs) => exportSelectedDoc(qs, 'Exam Paper', { subjectName, instructorName, institution, examDate, totalMarks, timeAllowed })}
            onExportJson={(qs) => exportSelectedJson(qs, 'Exam Paper', { subjectName, instructorName, institution, examDate, totalMarks, timeAllowed })}
          />
        )}

        {loading && (
          <div className="mb-4 bg-emerald-50 rounded-xl px-5 py-4 border border-emerald-200">
            <div className="flex items-center gap-3 text-sm">
              <Loader2 size={16} className="animate-spin text-emerald-500 shrink-0" />
              <span className="text-emerald-700">Generating exam paper…</span>
            </div>
          </div>
        )}
        {loading && streamContent && (
          <>
            <MessageBubble role="assistant" content={streamContent} />
            <div className="flex items-center gap-1.5 text-xs text-emerald-600 mb-3 ml-1">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              Answering…
            </div>
          </>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Uploaded files bar */}
      {files.length > 0 && (
        <div className="shrink-0 border-t border-gray-800 px-6 py-2 flex flex-wrap gap-2">
          {files.map((f, i) => (
            <div key={i} className="flex items-center gap-1.5 bg-gray-800 rounded-lg px-3 py-1.5 text-xs">
              {f.status === 'uploading' && <Loader2 size={12} className="animate-spin text-blue-400" />}
              {f.status === 'done' && <CheckCircle2 size={12} className="text-emerald-400" />}
              {f.status === 'error' && <XCircle size={12} className="text-red-400" />}
              <File size={12} className="text-gray-500" />
              <span className="truncate max-w-[140px]">{f.file.name}</span>
              <button onClick={() => removeFile(i)} className="ml-1 text-gray-500 hover:text-red-400">x</button>
            </div>
          ))}
        </div>
      )}

      {/* Input area */}
      <div className="shrink-0 border-t border-slate-200 px-6 py-4 space-y-3">
        {/* Exam Paper Header Form */}
        <div className="rounded-xl border border-slate-200 bg-slate-50 overflow-hidden">
          <button
            onClick={() => setShowHeaderForm((v) => !v)}
            className="w-full flex items-center justify-between px-4 py-2.5 text-xs font-medium text-slate-600 hover:bg-slate-100 transition"
          >
            <span>Exam Paper Header (optional)</span>
            <ChevronDown size={14} className={`transition-transform ${showHeaderForm ? 'rotate-180' : ''}`} />
          </button>
          {showHeaderForm && (
            <div className="grid grid-cols-2 gap-3 px-4 pb-4 pt-1">
              {[
                { label: 'Institution', value: institution, set: setInstitution, colSpan: true },
                { label: 'Subject', value: subjectName, set: setSubjectName },
                { label: 'Instructor', value: instructorName, set: setInstructorName },
                { label: 'Date', value: examDate, set: setExamDate, type: 'date' },
                { label: 'Total Marks', value: totalMarks, set: setTotalMarks, type: 'number' },
                { label: 'Time Allowed', value: timeAllowed, set: setTimeAllowed, placeholder: 'e.g. 90 min' },
              ].map(({ label, value, set, colSpan, type, placeholder }) => (
                <div key={label} className={colSpan ? 'col-span-2' : ''}>
                  <label className="block text-[11px] text-slate-400 mb-1">{label}</label>
                  <input
                    type={type || 'text'}
                    value={value}
                    onChange={(e) => set(e.target.value)}
                    placeholder={placeholder || label}
                    className="w-full bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-sm text-slate-700 outline-none focus:border-emerald-500 transition"
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Question-count inputs + difficulty selector */}
        <div className="flex items-center gap-4 flex-wrap">
          <label className="flex items-center gap-2 text-xs text-slate-500">
            <span className="whitespace-nowrap">MCQ</span>
            <input
              type="number"
              min={0}
              max={100}
              value={mcqCount}
              onChange={(e) => setMcqCount(Math.max(0, Math.min(100, parseInt(e.target.value) || 0)))}
              className="w-16 bg-white border border-slate-300 rounded-lg px-2 py-1 text-center text-sm text-slate-800 outline-none focus:border-emerald-500 transition"
            />
          </label>
          <label className="flex items-center gap-2 text-xs text-slate-500">
            <span className="whitespace-nowrap">True / False</span>
            <input
              type="number"
              min={0}
              max={100}
              value={tfCount}
              onChange={(e) => setTfCount(Math.max(0, Math.min(100, parseInt(e.target.value) || 0)))}
              className="w-16 bg-white border border-slate-300 rounded-lg px-2 py-1 text-center text-sm text-slate-800 outline-none focus:border-emerald-500 transition"
            />
          </label>
          <label className="flex items-center gap-2 text-xs text-slate-500">
            <span className="whitespace-nowrap">Fill in Blanks</span>
            <input
              type="number"
              min={0}
              max={100}
              value={fitbCount}
              onChange={(e) => setFitbCount(Math.max(0, Math.min(100, parseInt(e.target.value) || 0)))}
              className="w-16 bg-white border border-slate-300 rounded-lg px-2 py-1 text-center text-sm text-slate-800 outline-none focus:border-emerald-500 transition"
            />
          </label>
          {/* Difficulty ratio inputs */}
          <div className="flex items-center gap-2 ml-auto flex-wrap justify-end">
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] text-slate-400 whitespace-nowrap">Difficulty Ratio (E/M/H %):</span>
              {[
                { label: 'E', val: easyRatio, set: setEasyRatio, color: 'focus:border-emerald-500' },
                { label: 'M', val: mediumRatio, set: setMediumRatio, color: 'focus:border-amber-500' },
                { label: 'H', val: hardRatio, set: setHardRatio, color: 'focus:border-red-500' },
              ].map(({ label, val, set, color }) => (
                <label key={label} className="flex items-center gap-0.5 text-[11px] text-slate-500">
                  <span>{label}</span>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={val}
                    onChange={(e) => set(Math.max(0, Math.min(100, parseInt(e.target.value) || 0)))}
                    className={`w-12 bg-white border border-slate-300 rounded px-1 py-0.5 text-center text-xs text-slate-800 outline-none ${color} transition`}
                  />
                  <span>%</span>
                </label>
              ))}
              {easyRatio + mediumRatio + hardRatio !== 100 && (
                <span className="text-[11px] text-red-400 ml-1">
                  ≠ 100%
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Textarea + send */}
        <div className="flex items-end gap-2 bg-white rounded-xl px-4 py-2 border border-slate-200 focus-within:border-emerald-500 shadow-sm transition">
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="p-2 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-emerald-500 disabled:opacity-40 transition"
            title="Upload PDF, DOCX, or PPTX"
          >
            <Upload size={16} />
          </button>
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileSelect}
            accept={ACCEPT}
            multiple
            className="hidden"
          />
          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Additional instructions (optional) — e.g. focus on Chapter 3, use simple language…"
            className="flex-1 bg-transparent resize-none outline-none text-sm text-slate-700 placeholder-slate-400 max-h-40 py-1.5"
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
              disabled={messages.length === 0 && mcqCount === 0 && tfCount === 0 && fitbCount === 0}
              className="p-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed transition"
            >
              <Send size={16} className="text-white" />
            </button>
          )}
        </div>
        <p className="text-[11px] text-slate-400 px-1">
          Set question counts, choose difficulty, upload source material, then click Send.
        </p>
      </div>
    </div>
  );
}

