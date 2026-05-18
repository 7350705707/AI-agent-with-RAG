import React, { useState, useEffect, useRef } from 'react';
import {
  Send,
  Loader2,
  FileText,
  Upload,
  CheckCircle2,
  XCircle,
  File,
  Square,
  CheckSquare,
  X,
  ClipboardCheck,
  ChevronRight,
} from 'lucide-react';
import { sendExamStream, getMessages, createConversation, uploadFile, renameConversation, fetchExamTopics, getApprovalOfficers, submitExamForApproval } from '../api';
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
  const { subjectName, instructorName, courseName, examDate, totalMarks, timeAllowed, studentLevel } = header;
  const hasAny = subjectName || instructorName || courseName || examDate || totalMarks || timeAllowed;
  if (!hasAny) return '';
  const cols = [
    ['Subject', subjectName],
    ['Instructor', instructorName],
    ['Date', examDate],
    ['Course', courseName],
  ].filter(([, v]) => v);
  const meta = [
    totalMarks && `Total Marks: ${escapeHtml(totalMarks)}`,
    timeAllowed && `Time: ${escapeHtml(timeAllowed)}`,
    studentLevel && `Level: ${escapeHtml(studentLevel)}`,
  ].filter(Boolean);
  const colsHtml = cols.length
    ? `<table style="width:100%;border-collapse:collapse;margin-bottom:6px;font-size:12px;">
        <tr>${cols.map(([l, v]) => `<td style="padding:6px 10px;border:1px solid #d1d5db;"><b>${escapeHtml(l)}:</b> ${escapeHtml(v)}</td>`).join('')}</tr>
       </table>`
    : '';
  const metaHtml = meta.length
    ? `<p style="font-size:11px;color:#6b7280;margin:0 0 14px;text-align:center;">${meta.join(' &nbsp;|&nbsp; ')}</p>`
    : '';
  return colsHtml + metaHtml;
}

function buildPrompt(mcqCount, tfCount, fitbCount, extra, ratios, selectedTopics = [], studentLevel = '') {
  const parts = [];
  if (mcqCount > 0) parts.push(`${mcqCount} MCQ questions`);
  if (tfCount > 0) parts.push(`${tfCount} True or False questions`);
  if (fitbCount > 0) parts.push(`${fitbCount} Fill in the Blanks questions`);
  const { easy, medium, hard } = ratios;
  const ratioStr = `(Easy ${easy}% / Medium ${medium}% / Hard ${hard}%)`;
  const levelStr = studentLevel ? ` Target student level: ${studentLevel}.` : '';
  const base = parts.length
    ? `Generate an exam paper ${ratioStr} with ${parts.join(', ')}.${levelStr}`
    : `Generate an exam paper ${ratioStr}.${levelStr}`;
  const checkedTopics = (selectedTopics || []).filter((t) => t.checked);
  const topicsStr = checkedTopics.length
    ? ` Focus on these topics with the given percentage weights: ${checkedTopics.map((t) => `"${t.name}" (${t.weight}%)`).join(', ')}.`
    : '';
  const combined = base + topicsStr;
  return extra.trim() ? `${combined} Additional instructions: ${extra.trim()}` : combined;
}

// ── Question normalization ────────────────────────────────────────────────

function normalizeQuestions(raw) {
  if (!Array.isArray(raw) || !raw.length) return [];
  const VALID_TYPES = new Set(['mcq', 'true_false', 'fill_blank']);
  let n = 1;
  const result = [];
  for (const q of raw) {
    const text = (q.text || q.stem || q.question || '').trim();
    if (!text) continue;
    let type = q.type;
    if (!VALID_TYPES.has(type)) {
      type = (Array.isArray(q.options) && q.options.length >= 2) ? 'mcq' : 'fill_blank';
    }
    // Ensure fill_blank questions contain a blank marker
    let finalText = text;
    if (type === 'fill_blank' && !finalText.includes('_')) {
      finalText = finalText.replace(/\.?\s*$/, '') + ' ______.';
    }
    result.push({
      number: n++,
      type,
      text: finalText,
      options: Array.isArray(q.options) ? q.options : [],
      answer: q.answer || '',
    });
  }
  return result;
}

// -- Exam Configuration Modal ─────────────────────────────────────────────

function ExamConfigModal({
  open, onClose, onGenerate,
  subjectName, setSubjectName, instructorName, setInstructorName,
  institution, setInstitution, courseName, setCourseName, examDate, setExamDate,
  totalMarks, setTotalMarks, timeAllowed, setTimeAllowed,
  studentLevel, setStudentLevel,
  mcqCount, setMcqCount, tfCount, setTfCount, fitbCount, setFitbCount,
  easyRatio, setEasyRatio, mediumRatio, setMediumRatio, hardRatio, setHardRatio,
  extraInput, setExtraInput,
  rawTopics, topicsLoading, topicsError,
}) {
  const [topicSel, setTopicSel] = useState([]);

  useEffect(() => {
    if (!rawTopics || !rawTopics.length) { setTopicSel([]); return; }
    const w = Math.floor(100 / rawTopics.length);
    const rem = 100 - w * rawTopics.length;
    setTopicSel(
      rawTopics.map((t, i) => ({ name: t, checked: true, weight: i === 0 ? w + rem : w }))
    );
  }, [rawTopics]);

  const toggleTopic = (i) =>
    setTopicSel((prev) => prev.map((t, j) => (j === i ? { ...t, checked: !t.checked } : t)));

  const setWeight = (i, val) =>
    setTopicSel((prev) =>
      prev.map((t, j) =>
        j === i ? { ...t, weight: Math.max(0, Math.min(100, parseInt(val) || 0)) } : t
      )
    );

  const checkedWeightSum = topicSel.filter((t) => t.checked).reduce((s, t) => s + t.weight, 0);
  const canGenerate = mcqCount > 0 || tfCount > 0 || fitbCount > 0;

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-xl flex flex-col max-h-[92vh]">

        {/* Modal header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 shrink-0">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-emerald-100 flex items-center justify-center">
              <FileText size={13} className="text-emerald-600" />
            </div>
            <h2 className="text-sm font-semibold text-slate-800">Configure Exam Paper</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition"
          >
            <X size={15} />
          </button>
        </div>

        {/* Scrollable body */}
        <div className="overflow-y-auto flex-1 px-6 py-5 space-y-6">

          <div>
            <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-3">Exam Paper Header</p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[11px] text-slate-400 mb-1">Subject</label>
                <input type="text" value={subjectName} onChange={(e) => setSubjectName(e.target.value)}
                  placeholder="Subject name"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 outline-none focus:border-emerald-500 transition" />
              </div>
              <div>
                <label className="block text-[11px] text-slate-400 mb-1">Instructor</label>
                <input type="text" value={instructorName} onChange={(e) => setInstructorName(e.target.value)}
                  placeholder="Instructor name"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 outline-none focus:border-emerald-500 transition" />
              </div>
              <div>
                <label className="block text-[11px] text-slate-400 mb-1">Course Name</label>
                <input type="text" value={courseName} onChange={(e) => setCourseName(e.target.value)}
                  placeholder="e.g. Advanced Mathematics"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 outline-none focus:border-emerald-500 transition" />
              </div>
              <div>
                <label className="block text-[11px] text-slate-400 mb-1">Exam Date</label>
                <input type="date" value={examDate} onChange={(e) => setExamDate(e.target.value)}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 outline-none focus:border-emerald-500 transition" />
              </div>
              <div>
                <label className="block text-[11px] text-slate-400 mb-1">Total Marks</label>
                <input type="number" value={totalMarks} onChange={(e) => setTotalMarks(e.target.value)}
                  placeholder="e.g. 100"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 outline-none focus:border-emerald-500 transition" />
              </div>
              <div>
                <label className="block text-[11px] text-slate-400 mb-1">Time Allowed</label>
                <input type="text" value={timeAllowed} onChange={(e) => setTimeAllowed(e.target.value)}
                  placeholder="e.g. 90 min"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 outline-none focus:border-emerald-500 transition" />
              </div>
            </div>
            {/* Student Level */}
            <div className="mt-3">
              <label className="block text-[11px] text-slate-400 mb-2">Student Level</label>
              <div className="flex gap-2">
                {['Basic', 'Advanced Beginner', 'Competent'].map((lvl) => (
                  <button
                    key={lvl}
                    type="button"
                    onClick={() => setStudentLevel(lvl)}
                    className={`px-3 py-1.5 rounded-lg text-xs border transition ${
                      studentLevel === lvl
                        ? 'bg-emerald-500 text-white border-emerald-500'
                        : 'bg-white text-slate-600 border-slate-200 hover:border-emerald-300'
                    }`}
                  >
                    {lvl}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* — Question Counts — */}
          <div>
            <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-3">Number of Questions</p>
            <div className="grid grid-cols-3 gap-3">
              {[
                { label: 'MCQ', val: mcqCount, set: setMcqCount },
                { label: 'True / False', val: tfCount, set: setTfCount },
                { label: 'Fill in Blanks', val: fitbCount, set: setFitbCount },
              ].map(({ label, val, set }) => (
                <div key={label}>
                  <label className="block text-[11px] text-slate-400 mb-1">{label}</label>
                  <input type="number" min={0} max={100} value={val}
                    onChange={(e) => set(Math.max(0, Math.min(100, parseInt(e.target.value) || 0)))}
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-center text-slate-700 outline-none focus:border-emerald-500 transition" />
                </div>
              ))}
            </div>
          </div>

          {/* — Difficulty — */}
          <div>
            <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-3">Difficulty Distribution</p>
            <div className="grid grid-cols-3 gap-3">
              {[
                { label: 'Easy %', val: easyRatio, set: setEasyRatio },
                { label: 'Medium %', val: mediumRatio, set: setMediumRatio },
                { label: 'Hard %', val: hardRatio, set: setHardRatio },
              ].map(({ label, val, set }) => (
                <div key={label}>
                  <label className="block text-[11px] text-slate-400 mb-1">{label}</label>
                  <input type="number" min={0} max={100} value={val}
                    onChange={(e) => set(Math.max(0, Math.min(100, parseInt(e.target.value) || 0)))}
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-center text-slate-700 outline-none focus:border-emerald-500 transition" />
                </div>
              ))}
            </div>
            {easyRatio + mediumRatio + hardRatio !== 100 && (
              <p className="mt-1.5 text-[11px] text-red-400">
                Ratios must sum to 100% (current: {easyRatio + mediumRatio + hardRatio}%)
              </p>
            )}
          </div>

          {/* — Topics — */}
          <div>
            <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
              Topics
              {topicsLoading && (
                <span className="flex items-center gap-1 text-emerald-500 font-normal normal-case text-[11px]">
                  <Loader2 size={11} className="animate-spin" /> Extracting from document…
                </span>
              )}
            </p>

            {topicsLoading && !topicSel.length && (
              <div className="flex items-center gap-3 py-3 px-4 rounded-lg bg-emerald-50 border border-emerald-100 text-sm text-emerald-600">
                <Loader2 size={15} className="animate-spin shrink-0" />
                Analyzing your document to identify topics…
              </div>
            )}

            {topicsError && !topicsLoading && !topicSel.length && (
              <div className="rounded-lg bg-amber-50 border border-amber-200 px-4 py-3 text-sm text-amber-700">
                Topics could not be extracted automatically. You can still generate the exam without topic selection.
              </div>
            )}

            {topicSel.length > 0 && (
              <div>
                <p className="text-[11px] text-slate-400 mb-2">
                  Check topics to include and set a percentage weight for each.
                  {topicSel.some((t) => t.checked) && checkedWeightSum !== 100 && (
                    <span className="text-amber-500 ml-1">(Weights sum: {checkedWeightSum}%)</span>
                  )}
                </p>
                <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                  {topicSel.map((t, i) => (
                    <div
                      key={i}
                      onClick={() => toggleTopic(i)}
                      className={`flex items-center gap-3 px-3 py-2 rounded-lg border cursor-pointer transition ${
                        t.checked
                          ? 'border-emerald-200 bg-emerald-50/70'
                          : 'border-slate-100 bg-white hover:bg-slate-50'
                      }`}
                    >
                      <div className="shrink-0">
                        {t.checked
                          ? <CheckSquare size={14} className="text-emerald-500" />
                          : <Square size={14} className="text-slate-300" />}
                      </div>
                      <span className={`flex-1 text-sm truncate ${t.checked ? 'text-slate-700 font-medium' : 'text-slate-400'}`}>
                        {t.name}
                      </span>
                      {t.checked && (
                        <div
                          className="flex items-center gap-1 shrink-0"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <input
                            type="number" min={0} max={100} value={t.weight}
                            onChange={(e) => setWeight(i, e.target.value)}
                            className="w-14 border border-emerald-200 rounded-md px-1.5 py-0.5 text-xs text-center text-slate-700 outline-none focus:border-emerald-500 bg-white transition"
                          />
                          <span className="text-xs text-slate-400">%</span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* — Additional Instructions — */}
          <div>
            <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-3">Additional Instructions (Optional)</p>
            <textarea
              rows={2}
              value={extraInput}
              onChange={(e) => setExtraInput(e.target.value)}
              placeholder="e.g. Focus on Chapter 3, avoid formula-heavy questions, use simple language…"
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 outline-none focus:border-emerald-500 resize-none transition"
            />
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-100 shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition"
          >
            Cancel
          </button>
          <button
            onClick={() => onGenerate({ topicSel })}
            disabled={!canGenerate}
            className="flex items-center gap-2 px-5 py-2 text-sm font-medium bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg disabled:opacity-40 disabled:cursor-not-allowed transition shadow-sm"
          >
            <Send size={13} />
            Generate Exam
          </button>
        </div>
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
  // Exam paper header fields (used for export)
  const [subjectName, setSubjectName] = useState('');
  const [instructorName, setInstructorName] = useState('');
  const [institution, setInstitution] = useState('');
  const [courseName, setCourseName] = useState('');
  const [examDate, setExamDate] = useState(new Date().toISOString().slice(0, 10));
  const [totalMarks, setTotalMarks] = useState('');
  const [timeAllowed, setTimeAllowed] = useState('');
  const [studentLevel, setStudentLevel] = useState('Basic');
  const [lastTopicSel, setLastTopicSel] = useState([]);
  // Modal state
  const [showModal, setShowModal] = useState(false);
  const [rawTopics, setRawTopics] = useState([]);
  const [topicsLoading, setTopicsLoading] = useState(false);
  const [topicsError, setTopicsError] = useState(null);
  // Approval submit modal state
  const [showApprovalModal, setShowApprovalModal] = useState(false);
  const [approvalOfficers, setApprovalOfficers] = useState([]);
  const [approvalOfficersLoading, setApprovalOfficersLoading] = useState(false);
  const [approvalTitle, setApprovalTitle] = useState('');
  const [approvalStages, setApprovalStages] = useState([{ officer_id: '' }]);
  const [approvalSubmitting, setApprovalSubmitting] = useState(false);
  const [approvalError, setApprovalError] = useState('');
  const [approvalSuccess, setApprovalSuccess] = useState(false);
  const [approvalStep, setApprovalStep] = useState(1);
  const [approvalSelectedQs, setApprovalSelectedQs] = useState(new Set());
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
      return;
    }
    getMessages(conversationId).then(setMessages).catch(() => {});
    // Restore saved structured questions from localStorage
    try {
      const saved = localStorage.getItem(`exam_sq_${conversationId}`);
      if (saved) {
        setStructuredQuestions(JSON.parse(saved));
      } else {
        setStructuredQuestions(null);
      }
    } catch {
      setStructuredQuestions(null);
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

  // ── Core streaming executor ───────────────────────────────────────────────
  const _executeStream = async (prompt, fileIds, convId) => {
    const targetConvId = convId;
    setLoading(true);
    setStreamContent('');
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      let finalContent = '';
      await sendExamStream(
        convId,
        prompt,
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
            const normalized = normalizeQuestions(questions);
            if (normalized.length > 0) {
              setStructuredQuestions(normalized);
              try { localStorage.setItem(`exam_sq_${targetConvId}`, JSON.stringify(normalized)); } catch {}
            }
            return;
          }
          if (content) { setStreamContent(content); finalContent = content; }
        },
        { mcq_count: mcqCount, tf_count: tfCount, fitb_count: fitbCount },
        controller.signal,
      );
      if (finalContent && activeConvRef.current === targetConvId) {
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

  // ── Open configuration modal (called on first-message Send) ───────────────
  const handleOpenModal = () => {
    const doneFiles = files.filter((f) => f.status === 'done');
    if (!doneFiles.length) return;
    setRawTopics([]);
    setTopicsLoading(true);
    setTopicsError(null);
    setShowModal(true);

    fetchExamTopics(doneFiles.map((f) => f.fileId))
      .then((data) => { setRawTopics(data.topics || []); setTopicsLoading(false); })
      .catch((err) => { setTopicsError(err.message || 'Failed to extract topics'); setTopicsLoading(false); });
  };

  // ── Modal "Generate Exam" confirm ─────────────────────────────────────────
  const handleGenerate = async ({ topicSel }) => {
    setShowModal(false);
    setLastTopicSel(topicSel || []);
    if (loading) return;

    const doneFiles = files.filter((f) => f.status === 'done');
    const fileIds = doneFiles.map((f) => f.fileId);
    const fileTitle = doneFiles.map((f) => f.file.name.replace(/\.[^.]+$/, '')).join(', ');

    const ratios = { easy: easyRatio, medium: mediumRatio, hard: hardRatio };
    const prompt = buildPrompt(mcqCount, tfCount, fitbCount, input, ratios, topicSel, studentLevel);

    let convId = conversationId;
    if (!convId) {
      const title = fileTitle || prompt.slice(0, 60);
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
    setMessages((prev) => [
      ...prev,
      { id: Date.now().toString(), role: 'user', content: prompt },
    ]);
    await _executeStream(prompt, fileIds, convId);
  };

  // ── Send (routes to modal for first message, direct for follow-ups) ────────
  const handleSend = async () => {
    if (loading) return;

    if (messages.length === 0) {
      handleOpenModal();
      return;
    }

    // Follow-up message
    const prompt = input.trim() || 'Continue the exam paper.';
    setInput('');
    setStructuredQuestions(null);
    setMessages((prev) => [
      ...prev,
      { id: Date.now().toString(), role: 'user', content: prompt },
    ]);
    await _executeStream(prompt, [], conversationId);
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

        {/* Send to Approval button — shown after questions are generated */}
        {structuredQuestions && structuredQuestions.length > 0 && (
          <div className="my-3">
            <button
              onClick={async () => {
                setApprovalStep(1);
                setApprovalSelectedQs(new Set((structuredQuestions || []).map((q) => q.number)));
                setApprovalTitle(subjectName || 'Exam Paper');
                setApprovalStages([{ officer_id: '' }]);
                setApprovalError('');
                setApprovalSuccess(false);
                setShowApprovalModal(true);
                setApprovalOfficersLoading(true);
                try {
                  const officers = await getApprovalOfficers();
                  setApprovalOfficers(officers);
                } catch {
                  setApprovalOfficers([]);
                } finally {
                  setApprovalOfficersLoading(false);
                }
              }}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium transition shadow-sm"
            >
              <ClipboardCheck size={15} />
              Send to Approval
            </button>
          </div>
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
        {/* Textarea + send */}
        <div className="flex items-end gap-2 bg-white rounded-xl px-4 py-2 border border-slate-200 focus-within:border-emerald-500 shadow-sm transition">
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading || loading}
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
            placeholder={
              messages.length === 0
                ? 'Upload a document, then click Send to configure and generate the exam…'
                : 'Add instructions to refine the exam…'
            }
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
              disabled={messages.length === 0 && !files.some((f) => f.status === 'done')}
              title={
                messages.length === 0 && !files.some((f) => f.status === 'done')
                  ? 'Upload a file to enable exam generation'
                  : messages.length === 0 ? 'Configure and generate exam' : 'Send follow-up'
              }
              className="p-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed transition"
            >
              <Send size={16} className="text-white" />
            </button>
          )}
        </div>
        <p className="text-[11px] text-slate-400 px-1">
          {messages.length === 0
            ? 'Upload source material and click Send — a configuration panel will open to set headers, question counts, difficulty, and topics.'
            : 'Add follow-up instructions to refine the generated exam.'}
        </p>
      </div>

      {/* Exam Configuration Modal */}
      <ExamConfigModal
        open={showModal}
        onClose={() => setShowModal(false)}
        onGenerate={handleGenerate}
        subjectName={subjectName} setSubjectName={setSubjectName}
        instructorName={instructorName} setInstructorName={setInstructorName}
        institution={institution} setInstitution={setInstitution}
        courseName={courseName} setCourseName={setCourseName}
        examDate={examDate} setExamDate={setExamDate}
        totalMarks={totalMarks} setTotalMarks={setTotalMarks}
        timeAllowed={timeAllowed} setTimeAllowed={setTimeAllowed}
        studentLevel={studentLevel} setStudentLevel={setStudentLevel}
        mcqCount={mcqCount} setMcqCount={setMcqCount}
        tfCount={tfCount} setTfCount={setTfCount}
        fitbCount={fitbCount} setFitbCount={setFitbCount}
        easyRatio={easyRatio} setEasyRatio={setEasyRatio}
        mediumRatio={mediumRatio} setMediumRatio={setMediumRatio}
        hardRatio={hardRatio} setHardRatio={setHardRatio}
        extraInput={input} setExtraInput={setInput}
        rawTopics={rawTopics} topicsLoading={topicsLoading} topicsError={topicsError}
      />

      {/* ── Approval submit modal (2-step: question select → stage config) ── */}
      {showApprovalModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg flex flex-col max-h-[90vh]">

            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 shrink-0">
              <h2 className="text-base font-semibold text-slate-800 flex items-center gap-2">
                <ClipboardCheck size={17} className="text-blue-500" />
                {approvalSuccess ? 'Submitted!' : approvalStep === 1 ? 'Select Questions' : 'Configure Approval'}
              </h2>
              <div className="flex items-center gap-3">
                {!approvalSuccess && (
                  <span className="text-xs text-slate-400 bg-slate-100 rounded-full px-2.5 py-0.5">
                    Step {approvalStep} of 2
                  </span>
                )}
                <button onClick={() => setShowApprovalModal(false)} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500 transition">
                  <X size={16} />
                </button>
              </div>
            </div>

            {/* Scrollable body */}
            <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
              {approvalSuccess ? (
                <div className="flex flex-col items-center gap-3 py-8">
                  <CheckCircle2 size={40} className="text-emerald-500" />
                  <p className="text-slate-700 font-medium">Submitted for approval!</p>
                  <p className="text-xs text-slate-500">Track the status in the Approvals panel.</p>
                  <button
                    onClick={() => setShowApprovalModal(false)}
                    className="mt-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm transition"
                  >
                    Close
                  </button>
                </div>
              ) : approvalStep === 1 ? (
                /* ── Step 1: Question selection ── */
                <div className="space-y-4">
                  <p className="text-sm text-slate-500">
                    Choose which questions to include in this submission.{' '}
                    <span className="font-medium text-blue-600">{approvalSelectedQs.size} selected</span>
                  </p>
                  {['mcq', 'true_false', 'fill_blank'].map((type) => {
                    const qs = (structuredQuestions || []).filter((q) => q.type === type);
                    if (!qs.length) return null;
                    const typeLabels = { mcq: 'Multiple Choice', true_false: 'True / False', fill_blank: 'Fill in the Blanks' };
                    const allChecked = qs.every((q) => approvalSelectedQs.has(q.number));
                    return (
                      <div key={type}>
                        <div className="flex items-center justify-between mb-2">
                          <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">{typeLabels[type]}</p>
                          <button
                            onClick={() => {
                              const nums = qs.map((q) => q.number);
                              setApprovalSelectedQs((prev) => {
                                const next = new Set(prev);
                                if (allChecked) nums.forEach((n) => next.delete(n));
                                else nums.forEach((n) => next.add(n));
                                return next;
                              });
                            }}
                            className="text-xs text-blue-600 hover:text-blue-800 transition"
                          >
                            {allChecked ? 'Deselect all' : 'Select all'}
                          </button>
                        </div>
                        <div className="space-y-1.5">
                          {qs.map((q) => (
                            <div
                              key={q.number}
                              onClick={() => setApprovalSelectedQs((prev) => {
                                const next = new Set(prev);
                                next.has(q.number) ? next.delete(q.number) : next.add(q.number);
                                return next;
                              })}
                              className={`flex gap-2.5 px-3 py-2 rounded-lg border cursor-pointer transition ${
                                approvalSelectedQs.has(q.number)
                                  ? 'border-blue-200 bg-blue-50'
                                  : 'border-slate-100 bg-white hover:border-slate-200 hover:bg-slate-50'
                              }`}
                            >
                              <div className="shrink-0 mt-0.5">
                                {approvalSelectedQs.has(q.number)
                                  ? <CheckSquare size={14} className="text-blue-500" />
                                  : <Square size={14} className="text-slate-300" />}
                              </div>
                              <div className="flex-1 min-w-0">
                                <span className="font-medium text-slate-400 mr-1 text-xs">Q{q.number}.</span>
                                <span className="text-sm text-slate-700">{q.text}</span>
                                {q.type === 'mcq' && q.options?.length > 0 && (
                                  <div className="mt-1.5 grid grid-cols-2 gap-x-3 gap-y-0.5">
                                    {q.options.map((opt, i) => (
                                      <p key={i} className="text-xs text-slate-400 truncate">{opt}</p>
                                    ))}
                                  </div>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                /* ── Step 2: Stage configuration ── */
                <>
                  <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1">Exam Title</label>
                    <input
                      type="text"
                      value={approvalTitle}
                      onChange={(e) => setApprovalTitle(e.target.value)}
                      className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-sm text-slate-800 outline-none focus:border-blue-400 placeholder-slate-400"
                      placeholder="e.g. Mid-term Exam 2025"
                    />
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <label className="text-xs font-medium text-slate-600">Approval Stages (max 3)</label>
                      {approvalStages.length < 3 && (
                        <button
                          onClick={() => setApprovalStages((s) => [...s, { officer_id: '' }])}
                          className="text-xs text-blue-600 hover:text-blue-800 transition"
                        >
                          + Add Stage
                        </button>
                      )}
                    </div>
                    <div className="space-y-2">
                      {approvalStages.map((stage, idx) => (
                        <div key={idx} className="flex items-center gap-2">
                          <div className="w-6 h-6 rounded-full bg-blue-100 text-blue-700 text-xs font-bold flex items-center justify-center shrink-0">
                            {idx + 1}
                          </div>
                          {approvalOfficersLoading ? (
                            <div className="flex items-center gap-2 text-xs text-slate-400">
                              <Loader2 size={13} className="animate-spin" /> Loading officers…
                            </div>
                          ) : (
                            <select
                              value={stage.officer_id}
                              onChange={(e) => {
                                const val = e.target.value;
                                setApprovalStages((prev) => prev.map((s, i) => i === idx ? { ...s, officer_id: val } : s));
                              }}
                              className="flex-1 bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-sm text-slate-800 outline-none focus:border-blue-400"
                            >
                              <option value="">— Select Officer —</option>
                              {approvalOfficers.map((o) => (
                                <option key={o.id} value={o.id}>{o.username}</option>
                              ))}
                            </select>
                          )}
                          {approvalStages.length > 1 && (
                            <button
                              onClick={() => setApprovalStages((s) => s.filter((_, i) => i !== idx))}
                              className="p-1.5 rounded-lg hover:bg-red-50 text-red-400 transition"
                            >
                              <X size={13} />
                            </button>
                          )}
                        </div>
                      ))}
                    </div>
                    {approvalOfficers.length === 0 && !approvalOfficersLoading && (
                      <p className="text-xs text-amber-600 mt-2">
                        No approval officers found. Ask an admin to assign the &ldquo;approval&rdquo; agent to a user.
                      </p>
                    )}
                  </div>

                  {approvalError && (
                    <div className="flex items-center gap-2 text-red-500 text-xs bg-red-50 rounded-lg px-3 py-2">
                      <XCircle size={13} /> {approvalError}
                    </div>
                  )}
                </>
              )}
            </div>

            {/* Footer navigation */}
            {!approvalSuccess && (
              <div className="shrink-0 px-6 py-4 border-t border-slate-100 flex items-center justify-between gap-3">
                {approvalStep === 1 ? (
                  <>
                    <span className="text-xs text-slate-400">
                      {approvalSelectedQs.size} of {(structuredQuestions || []).length} questions selected
                    </span>
                    <button
                      onClick={() => setApprovalStep(2)}
                      disabled={approvalSelectedQs.size === 0}
                      className="flex items-center gap-1.5 px-5 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium transition"
                    >
                      Next <ChevronRight size={14} />
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      onClick={() => { setApprovalError(''); setApprovalStep(1); }}
                      className="flex items-center gap-1.5 px-4 py-2 text-sm text-slate-600 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition"
                    >
                      ← Back
                    </button>
                    <button
                      onClick={async () => {
                        if (!approvalTitle.trim()) { setApprovalError('Please enter a title.'); return; }
                        if (approvalStages.some((s) => !s.officer_id)) { setApprovalError('Please assign an officer to every stage.'); return; }
                        setApprovalSubmitting(true);
                        setApprovalError('');
                        try {
                          await submitExamForApproval({
                            conversation_id: conversationId || '',
                            title: approvalTitle.trim(),
                            questions: (structuredQuestions || []).filter((q) => approvalSelectedQs.has(q.number)),
                            header: {
                              subjectName, instructorName, courseName, examDate, totalMarks, timeAllowed,
                              studentLevel,
                              topics: (lastTopicSel || []).filter((t) => t.checked).map((t) => ({ name: t.name, weight: t.weight })),
                            },
                            raw_text: '',
                            stages: approvalStages.map((s) => ({ officer_id: s.officer_id })),
                          });
                          setApprovalSuccess(true);
                        } catch (err) {
                          setApprovalError(err.message || 'Submission failed. Please try again.');
                        } finally {
                          setApprovalSubmitting(false);
                        }
                      }}
                      disabled={approvalSubmitting}
                      className="flex items-center gap-2 px-5 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition"
                    >
                      {approvalSubmitting ? <Loader2 size={15} className="animate-spin" /> : <ClipboardCheck size={15} />}
                      Submit for Approval
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

