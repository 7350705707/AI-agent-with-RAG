import React, { useState, useEffect, useCallback } from 'react';
import {
  ClipboardList,
  Clock,
  CheckCircle,
  XCircle,
  ChevronRight,
  Loader2,
  AlertCircle,
  X,
  FileDown,
  RefreshCw,
  MessageSquare,
  CheckSquare,
  ArrowRight,
  Filter,
  Trash2,
} from 'lucide-react';
import {
  getMySubmissions,
  getPendingReviews,
  getApprovalHistory,
  getSubmission,
  submitApprovalAction,
} from '../api';

// ── Helpers ────────────────────────────────────────────────────────────────

function fmt(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function StatusBadge({ status, currentStage, totalStages }) {
  const base = 'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium';
  if (status === 'approved')
    return <span className={`${base} bg-emerald-100 text-emerald-700`}><CheckCircle size={11} /> Approved</span>;
  if (status === 'sent_back')
    return <span className={`${base} bg-red-100 text-red-600`}><XCircle size={11} /> Sent Back</span>;
  return (
    <span className={`${base} bg-amber-100 text-amber-700`}>
      <Clock size={11} /> Awaiting Stage {currentStage}/{totalStages}
    </span>
  );
}

function StageProgress({ stages, currentStage, status }) {
  return (
    <div className="flex items-center gap-1 flex-wrap">
      {stages.map((s, i) => {
        let cls = 'flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold border';
        if (s.status === 'approve') cls += ' bg-emerald-100 border-emerald-400 text-emerald-700';
        else if (s.status === 'send_back') cls += ' bg-red-100 border-red-400 text-red-600';
        else if (s.stage_number === currentStage && status === 'pending')
          cls += ' bg-amber-100 border-amber-400 text-amber-700 animate-pulse';
        else cls += ' bg-slate-100 border-slate-300 text-slate-400';
        return (
          <React.Fragment key={s.id}>
            {i > 0 && <ArrowRight size={10} className="text-slate-300" />}
            <div className={cls} title={`Stage ${s.stage_number}: ${s.officer_name || 'Officer'}`}>
              {s.stage_number}
            </div>
          </React.Fragment>
        );
      })}
    </div>
  );
}

// ── Export helpers (4 shuffled sets: PDF / DOCX / JSON) ──────────────────

function escHtml(str) {
  return String(str ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function shuffleArr(arr) {
  const r = [...arr];
  for (let i = r.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [r[i], r[j]] = [r[j], r[i]];
  }
  return r;
}

function shuffleByType(questions) {
  const s = { mcq: [], true_false: [], fill_blank: [] };
  questions.forEach((q) => { if (s[q.type]) s[q.type].push(q); });
  return [...shuffleArr(s.mcq), ...shuffleArr(s.true_false), ...shuffleArr(s.fill_blank)];
}

const EXPORT_SETS = ['A', 'B', 'C', 'D'];

function renderQsHtml(questions) {
  const sections = { mcq: [], true_false: [], fill_blank: [] };
  questions.forEach((q) => { if (sections[q.type]) sections[q.type].push(q); });
  const sLabels = {
    mcq: 'Section A: Multiple Choice Questions',
    true_false: 'Section B: True / False',
    fill_blank: 'Section C: Fill in the Blanks',
  };
  let html = '';
  Object.entries(sections).forEach(([type, qs]) => {
    if (!qs.length) return;
    html += `<h2 style="margin-top:24px;font-size:15px;">${sLabels[type]}</h2>`;
    qs.forEach((q, i) => {
      const text = q.text || q.stem || q.question || '';
      html += `<p style="margin:10px 0 4px;"><b>Q${i + 1}.</b> ${escHtml(text)}</p>`;
      if (type === 'mcq' && (q.options || []).length) {
        q.options.forEach((opt) => { html += `<p style="margin:2px 0 2px 20px;">${escHtml(opt)}</p>`; });
      }
    });
  });
  return html;
}

function renderHeaderHtml(header = {}) {
  const { subjectName, instructorName, courseName, examDate, totalMarks, timeAllowed, studentLevel } = header;
  if (!Object.values(header).some(Boolean)) return '';
  const cols = [
    ['Subject', subjectName], ['Instructor', instructorName],
    ['Date', examDate], ['Course', courseName],
  ].filter(([, v]) => v);
  if (!cols.length && !totalMarks && !timeAllowed && !studentLevel) return '';
  const colsHtml = cols.map(([l, v]) =>
    `<td style="padding:6px 10px;border:1px solid #d1d5db;width:${Math.floor(100 / cols.length)}%"><span style="display:block;font-size:11px;color:#6b7280;">${escHtml(l)}</span><strong>${escHtml(v)}</strong></td>`
  ).join('');
  const meta = [
    totalMarks && `Total Marks: ${escHtml(String(totalMarks))}`,
    timeAllowed && `Time: ${escHtml(timeAllowed)}`,
    studentLevel && `Level: ${escHtml(studentLevel)}`,
  ].filter(Boolean);
  const metaRow = meta.length
    ? `<tr><td colspan="${cols.length || 1}" style="padding:4px 10px;font-size:11px;color:#6b7280;border:1px solid #d1d5db;">${meta.join(' &nbsp;|&nbsp; ')}</td></tr>`
    : '';
  return `<table style="width:100%;border-collapse:collapse;margin-bottom:20px;font-size:13px;"><tr>${colsHtml}</tr>${metaRow}</table>`;
}

function exportApprovalPdf(questions, title, header = {}) {
  const win = window.open('', '_blank');
  if (!win) return;
  const headerHtml = renderHeaderHtml(header);
  const allSetsHtml = EXPORT_SETS.map((label, idx) => {
    const body = renderQsHtml(shuffleByType(questions));
    return `<div${idx > 0 ? ' class="pb"' : ''}><h1>${escHtml(title)} — Set ${label}</h1>${headerHtml}${body}</div>`;
  }).join('');
  win.document.write(`<!DOCTYPE html><html><head><title>${escHtml(title)}</title>
    <style>body{font-family:Arial,sans-serif;padding:32px;color:#111;max-width:860px;margin:0 auto;line-height:1.6;}
    h1{font-size:18px;margin-bottom:4px;}.pb{page-break-before:always;padding-top:32px;}
    @media print{body{padding:0}.pb{page-break-before:always;}}</style></head>
    <body>${allSetsHtml}</body></html>`);
  win.document.close();
  win.focus();
  setTimeout(() => { win.print(); }, 300);
}

function exportApprovalDoc(questions, title, header = {}) {
  const headerHtml = renderHeaderHtml(header);
  EXPORT_SETS.forEach((label, idx) => {
    const body = renderQsHtml(shuffleByType(questions));
    const setTitle = `${title} - Set ${label}`;
    const html = `<html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word' xmlns='http://www.w3.org/TR/REC-html40'>
      <head><meta charset='utf-8'><title>${escHtml(setTitle)}</title>
      <style>body{font-family:Arial,sans-serif;padding:32px;line-height:1.6;}</style></head>
      <body><h1>${escHtml(setTitle)}</h1>${headerHtml}${body}</body></html>`;
    setTimeout(() => {
      const blob = new Blob(['\ufeff', html], { type: 'application/msword' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${title.replace(/\s+/g, '_')}_Set_${label}.doc`;
      document.body.appendChild(a); a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }, idx * 400);
  });
}

function exportApprovalJson(questions, title, header = {}) {
  const base = title.replace(/\s+/g, '_');
  EXPORT_SETS.forEach((label, idx) => {
    const qs = shuffleByType(questions);
    const sections = { mcq: [], true_false: [], fill_blank: [] };
    qs.forEach((q) => { if (sections[q.type]) sections[q.type].push(q); });
    const data = {
      title: `${title} - Set ${label}`, set: label, header,
      exported_at: new Date().toISOString(),
      sections: Object.fromEntries(
        Object.entries(sections).map(([type, qlist]) => [
          type,
          qlist.map((q, i) => ({
            number: i + 1,
            text: q.text || q.stem || q.question || '',
            ...(q.options?.length ? { options: q.options } : {}),
            ...(q.answer ? { answer: q.answer } : {}),
          })),
        ])
      ),
    };
    setTimeout(() => {
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${base}_Set_${label}.json`;
      document.body.appendChild(a); a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }, idx * 400);
  });
}

// ── Submission Detail / Review Modal ─────────────────────────────────────

function SubmissionModal({ submission, isOfficer, onClose, onAction }) {
  const [action, setAction] = useState('');
  const [remark, setRemark] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  // question-level rejection: set of question numbers officer wants to flag
  const [rejectedQs, setRejectedQs] = useState(new Set());

  const toggleQReject = (num) => {
    setRejectedQs((prev) => {
      const next = new Set(prev);
      next.has(num) ? next.delete(num) : next.add(num);
      return next;
    });
  };

  const handleSubmit = async () => {
    if (!action) return;
    setSaving(true);
    setError('');
    try {
      // Append rejected question numbers to remark
      let finalRemark = remark;
      if (action === 'send_back' && rejectedQs.size > 0) {
        const nums = Array.from(rejectedQs).sort((a, b) => a - b).join(', ');
        finalRemark = `${remark ? remark + '\n' : ''}Rejected questions: ${nums}`;
      }
      await onAction(submission.id, action, finalRemark);
      onClose();
    } catch (err) {
      setError(err.message || 'Action failed');
    } finally {
      setSaving(false);
    }
  };

  const { questions = [], header = {}, stages = [] } = submission;
  const isFullyApproved = submission.status === 'approved';
  const isPending = submission.status === 'pending';
  const isSentBack = submission.status === 'sent_back';

  // Can this user take action? They must be the current stage's officer and status=pending
  const currentStageData = stages.find((s) => s.stage_number === submission.current_stage);
  const canAct = isOfficer && isPending && currentStageData?.status === 'pending';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-3xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
          <div>
            <h2 className="text-base font-semibold text-slate-800">{submission.title}</h2>
            <p className="text-xs text-slate-500 mt-0.5">Submitted {fmt(submission.created_at)}</p>
          </div>
          <div className="flex items-center gap-3">
            <StatusBadge
              status={submission.status}
              currentStage={submission.current_stage}
              totalStages={submission.total_stages}
            />
            <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500 transition">
              <X size={16} />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-5">
          {/* Exam Header Info */}
          {Object.keys(header).some((k) => header[k]) && (
            <div className="bg-slate-50 rounded-xl p-4 grid grid-cols-2 gap-2 text-sm">
              {header.subjectName && <div><span className="text-slate-500">Subject: </span><span className="font-medium text-slate-700">{header.subjectName}</span></div>}
              {header.instructorName && <div><span className="text-slate-500">Instructor: </span><span className="font-medium text-slate-700">{header.instructorName}</span></div>}
              {header.courseName && <div><span className="text-slate-500">Course: </span><span className="font-medium text-slate-700">{header.courseName}</span></div>}
              {header.examDate && <div><span className="text-slate-500">Date: </span><span className="font-medium text-slate-700">{header.examDate}</span></div>}
              {header.totalMarks && <div><span className="text-slate-500">Total Marks: </span><span className="font-medium text-slate-700">{header.totalMarks}</span></div>}
              {header.timeAllowed && <div><span className="text-slate-500">Time: </span><span className="font-medium text-slate-700">{header.timeAllowed}</span></div>}
              {header.studentLevel && <div><span className="text-slate-500"> Student Level: </span><span className="font-medium text-slate-700">{header.studentLevel}</span></div>}
              {header.topics?.length > 0 && (
                <div className="col-span-2">
                  <span className="text-slate-500">Topics: </span>
                  <span className="font-medium text-slate-700">{header.topics.map((t) => `${t.name} (${t.weight}%)`).join(', ')}</span>
                </div>
              )}
            </div>
          )}

          {/* Questions */}
          {questions.length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
                  <CheckSquare size={14} className="text-emerald-500" />
                  Questions ({questions.length})
                </h3>
                {isFullyApproved && (
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <button
                      onClick={() => exportApprovalPdf(questions, submission.title, header)}
                      title="Export 4 shuffled PDF sets"
                      className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-emerald-50 hover:bg-emerald-100 text-emerald-600 border border-emerald-200 rounded-lg transition"
                    >
                      <FileDown size={12} /> PDF ×4
                    </button>
                    <button
                      onClick={() => exportApprovalDoc(questions, submission.title, header)}
                      title="Export 4 shuffled DOCX sets"
                      className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-blue-50 hover:bg-blue-100 text-blue-600 border border-blue-200 rounded-lg transition"
                    >
                      <FileDown size={12} /> DOCX ×4
                    </button>
                    <button
                      onClick={() => exportApprovalJson(questions, submission.title, header)}
                      title="Export 4 shuffled JSON sets"
                      className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-violet-50 hover:bg-violet-100 text-violet-600 border border-violet-200 rounded-lg transition"
                    >
                      <FileDown size={12} /> JSON ×4
                    </button>
                  </div>
                )}
              </div>
              <div className="space-y-2 max-h-64 overflow-y-auto rounded-xl border border-slate-100 p-3 bg-slate-50">
                {['mcq', 'true_false', 'fill_blank'].map((type) => {
                  const qs = questions.filter((q) => q.type === type);
                  if (!qs.length) return null;
                  const labels = { mcq: 'Multiple Choice', true_false: 'True / False', fill_blank: 'Fill in the Blanks' };
                  return (
                    <div key={type}>
                      <p className="text-xs uppercase tracking-wider text-slate-400 font-semibold mb-1">{labels[type]}</p>
                      {qs.map((q) => {
                        const num = q.number ?? q.id;
                        const isRej = rejectedQs.has(num);
                        const showCross = canAct;
                        return (
                          <div key={num} className={`flex items-start gap-2 text-sm bg-white border rounded-lg px-3 py-2 mb-1 transition ${
                            isRej ? 'border-red-300 bg-red-50' : 'border-slate-100'
                          }`}>
                            <div className="flex-1">
                              <span className="font-medium text-slate-500 mr-1">{num}.</span>
                              <span className={isRej ? 'text-red-400 line-through' : 'text-slate-700'}>
                                {q.stem || q.question || q.text || ''}
                              </span>
                              {q.options?.length > 0 && (
                                <ul className="mt-1 ml-4 space-y-0.5">
                                  {q.options.map((o, i) => (
                                    <li key={i} className="text-xs text-slate-600 list-disc">{o}</li>
                                  ))}
                                </ul>
                              )}
                            </div>
                            {showCross && (
                              <button
                                type="button"
                                onClick={() => toggleQReject(num)}
                                title={isRej ? 'Unmark' : 'Mark for rejection'}
                                className={`shrink-0 mt-0.5 w-5 h-5 rounded flex items-center justify-center text-xs font-bold transition ${
                                  isRej
                                    ? 'bg-red-500 text-white hover:bg-red-400'
                                    : 'bg-slate-200 text-slate-400 hover:bg-red-200 hover:text-red-600'
                                }`}
                              >
                                ✕
                              </button>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Approval Stages Timeline */}
          <div>
            <h3 className="text-sm font-semibold text-slate-700 mb-3">Approval Progress</h3>
            <div className="space-y-2">
              {stages.map((s) => {
                const isActive = s.stage_number === submission.current_stage && isPending;
                const isDone = s.status !== 'pending';
                return (
                  <div
                    key={s.id}
                    className={`rounded-xl border px-4 py-3 text-sm ${
                      isActive ? 'border-amber-300 bg-amber-50' :
                      s.status === 'approve' ? 'border-emerald-200 bg-emerald-50' :
                      s.status === 'send_back' ? 'border-red-200 bg-red-50' :
                      'border-slate-200 bg-slate-50'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                          isActive ? 'bg-amber-200 text-amber-700' :
                          s.status === 'approve' ? 'bg-emerald-200 text-emerald-700' :
                          s.status === 'send_back' ? 'bg-red-200 text-red-700' :
                          'bg-slate-200 text-slate-500'
                        }`}>
                          {s.stage_number}
                        </div>
                        <div>
                          <span className="font-medium text-slate-700">{s.officer_name || 'Officer'}</span>
                          {isActive && <span className="ml-2 text-xs text-amber-600 font-medium">Awaiting review…</span>}
                        </div>
                      </div>
                      {isDone && (
                        <div className="flex items-center gap-1.5">
                          {s.status === 'approve' ?
                            <span className="flex items-center gap-1 text-xs text-emerald-600"><CheckCircle size={12} /> Approved</span> :
                            <span className="flex items-center gap-1 text-xs text-red-600"><XCircle size={12} /> Sent Back</span>
                          }
                          {s.actioned_at && <span className="text-xs text-slate-400">({fmt(s.actioned_at)})</span>}
                        </div>
                      )}
                    </div>
                    {s.remark && (
                      <div className="mt-2 flex items-start gap-1.5 text-xs text-slate-600 italic bg-white/70 rounded-lg px-3 py-2 border border-slate-100">
                        <MessageSquare size={12} className="shrink-0 mt-0.5 text-slate-400" />
                        {s.remark}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Officer action form */}
          {canAct && (
            <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 space-y-3">
              <h3 className="text-sm font-semibold text-blue-700">Your Review (Stage {submission.current_stage})</h3>
              <textarea
                value={remark}
                onChange={(e) => setRemark(e.target.value)}
                placeholder="Optional remark or feedback…"
                rows={3}
                className="w-full bg-white border border-blue-200 rounded-lg px-3 py-2 text-sm text-slate-700 resize-none outline-none focus:border-blue-400 placeholder-slate-400"
              />

              {rejectedQs.size > 0 && (
                <p className="text-xs text-red-600 font-medium">
                  {rejectedQs.size} question{rejectedQs.size > 1 ? 's' : ''} marked for rejection
                </p>
              )}

              {error && (
                <div className="flex items-center gap-2 text-red-500 text-xs">
                  <AlertCircle size={14} /> {error}
                </div>
              )}
              <div className="flex gap-2">
                <button
                  onClick={() => { setAction('approve'); }}
                  className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition ${
                    action === 'approve' ? 'bg-emerald-600 text-white shadow' : 'bg-white border border-emerald-300 text-emerald-700 hover:bg-emerald-50'
                  }`}
                >
                  <CheckCircle size={14} /> Approve
                </button>
                <button
                  onClick={() => { setAction('send_back'); }}
                  className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition ${
                    action === 'send_back' ? 'bg-red-600 text-white shadow' : 'bg-white border border-red-300 text-red-600 hover:bg-red-50'
                  }`}
                >
                  <XCircle size={14} /> Send Back
                </button>
                {action && (
                  <button
                    onClick={handleSubmit}
                    disabled={saving}
                    className="ml-auto flex items-center gap-1.5 px-5 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition"
                  >
                    {saving ? <Loader2 size={14} className="animate-spin" /> : <ChevronRight size={14} />}
                    Submit
                  </button>
                )}
              </div>
            </div>
          )}

          {/* Sent-back notice for submitters */}
          {isSentBack && !isOfficer && (
            <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              <div className="flex items-center gap-2 font-medium mb-1"><XCircle size={14} /> This paper was sent back</div>
              <p className="text-xs text-red-600">Please review the officer remarks above, regenerate the exam, and submit again.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Submission Card ─────────────────────────────────────────────────────────

function SubmissionCard({ sub, isOfficer, onClick }) {
  return (
    <div
      onClick={onClick}
      className="bg-white rounded-xl border border-slate-200 hover:border-blue-300 hover:shadow-md transition cursor-pointer p-4"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-medium text-slate-800 truncate">{sub.title}</p>
          <p className="text-xs text-slate-500 mt-0.5">
            {isOfficer ? '' : `Submitted ${fmt(sub.created_at)}`}
            {isOfficer && sub.stages?.find((s) => s.officer_id === sub._officer_id_hint)?.officer_name
              ? `Stage ${sub.current_stage} of ${sub.total_stages}`
              : `Submitted ${fmt(sub.created_at)}`}
          </p>
        </div>
        <StatusBadge status={sub.status} currentStage={sub.current_stage} totalStages={sub.total_stages} />
      </div>
      {sub.stages?.length > 0 && (
        <div className="mt-3">
          <StageProgress stages={sub.stages} currentStage={sub.current_stage} status={sub.status} />
        </div>
      )}
      {sub.header?.subjectName && (
        <p className="mt-2 text-xs text-slate-400">Subject: {sub.header.subjectName}</p>
      )}
    </div>
  );
}

// ── My Submissions — grouped by status ───────────────────────────────────

function MySubmissionsView({ items, onCardClick }) {
  const pending = items.filter((s) => s.status === 'pending');
  const approved = items.filter((s) => s.status === 'approved');
  const sentBack = items.filter((s) => s.status === 'sent_back');

  const [showApproved, setShowApproved] = useState(pending.length === 0);
  const [showSentBack, setShowSentBack] = useState(pending.length === 0);

  const Section = ({ label, icon: Icon, colorCls, items: list, open, toggle }) => {
    if (!list.length) return null;
    return (
      <div className="mb-4">
        <button
          onClick={toggle}
          className={`flex items-center gap-2 text-sm font-semibold mb-2 ${colorCls} hover:opacity-80 transition`}
        >
          <Icon size={14} />
          {label}
          <span className="font-normal text-xs">({list.length})</span>
          <ChevronRight size={13} className={`ml-auto transition-transform ${open ? 'rotate-90' : ''}`} />
        </button>
        {open && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {list.map((sub) => (
              <SubmissionCard key={sub.id} sub={sub} isOfficer={false} onClick={() => onCardClick(sub)} />
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div>
      {/* Always visible: pending */}
      {pending.length > 0 && (
        <div className="mb-4">
          <p className="flex items-center gap-2 text-sm font-semibold text-amber-700 mb-2">
            <Clock size={14} /> Pending Review <span className="font-normal text-xs">({pending.length})</span>
          </p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {pending.map((sub) => (
              <SubmissionCard key={sub.id} sub={sub} isOfficer={false} onClick={() => onCardClick(sub)} />
            ))}
          </div>
        </div>
      )}

      <Section
        label="Approved"
        icon={CheckCircle}
        colorCls="text-emerald-700"
        items={approved}
        open={showApproved}
        toggle={() => setShowApproved((v) => !v)}
      />
      <Section
        label="Sent Back"
        icon={XCircle}
        colorCls="text-red-600"
        items={sentBack}
        open={showSentBack}
        toggle={() => setShowSentBack((v) => !v)}
      />

      {items.length === 0 && (
        <div className="text-center py-16 text-slate-400">
          <ClipboardList size={36} className="mx-auto mb-3 opacity-40" />
          <p className="text-sm">You have not submitted any exam papers yet.</p>
        </div>
      )}
    </div>
  );
}

// ── Main Panel ─────────────────────────────────────────────────────────────

export default function ApprovalPanel({ user }) {
  const isOfficer = user?.agents?.includes('approval');
  const isExamUser = user?.agents?.includes('exam') || user?.role === 'admin';
  const tabs = [
    ...(isExamUser ? [{ id: 'my', label: 'My Submissions', icon: ClipboardList }] : []),
    ...(isOfficer ? [
      { id: 'pending', label: 'Pending Review', icon: Clock },
      { id: 'history', label: 'Processed', icon: CheckCircle },
    ] : []),
  ];

  const [activeTab, setActiveTab] = useState(isOfficer ? 'pending' : 'my');
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      let data;
      if (activeTab === 'my') data = await getMySubmissions();
      else if (activeTab === 'pending') data = await getPendingReviews();
      else data = await getApprovalHistory();
      setItems(data);
    } catch (err) {
      setError(err.message || 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, [activeTab]);

  useEffect(() => { load(); }, [load]);

  const handleCardClick = async (sub) => {
    setDetailLoading(true);
    try {
      const full = await getSubmission(sub.id);
      setSelected(full);
    } catch {
      setSelected(sub);
    } finally {
      setDetailLoading(false);
    }
  };

  const handleAction = async (submissionId, action, remark) => {
    await submitApprovalAction(submissionId, action, remark);
    await load();
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden">
      {/* Header */}
      <header className="shrink-0 flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-gradient-to-r from-white to-blue-50/60">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-blue-100 flex items-center justify-center">
            <ClipboardList size={16} className="text-blue-600" />
          </div>
          <h1 className="text-base font-semibold text-slate-800">Exam Approvals</h1>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="p-2 rounded-lg hover:bg-slate-100 text-slate-500 transition disabled:opacity-40"
          title="Refresh"
        >
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
        </button>
      </header>

      {/* Tab bar */}
      <div className="shrink-0 flex gap-1 px-6 pt-4 pb-0 border-b border-slate-100 bg-white">
        {tabs.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium rounded-t-lg border-b-2 transition ${
              activeTab === id
                ? 'border-blue-500 text-blue-600 bg-blue-50/60'
                : 'border-transparent text-slate-500 hover:text-slate-700 hover:bg-slate-50'
            }`}
          >
            <Icon size={14} />
            {label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-6">
        {error && (
          <div className="flex items-center gap-2 text-red-500 bg-red-50 rounded-xl px-4 py-3 text-sm mb-4">
            <AlertCircle size={16} /> {error}
          </div>
        )}

        {loading && (
          <div className="flex items-center gap-3 text-slate-500 text-sm">
            <Loader2 size={18} className="animate-spin" /> Loading…
          </div>
        )}

        {!loading && !error && items.length === 0 && (
          <div className="text-center py-16 text-slate-400">
            <ClipboardList size={36} className="mx-auto mb-3 opacity-40" />
            <p className="text-sm">
              {activeTab === 'my' && 'You have not submitted any exam papers yet.'}
              {activeTab === 'pending' && 'No submissions are waiting for your review.'}
              {activeTab === 'history' && 'You have not reviewed any submissions yet.'}
            </p>
          </div>
        )}

        {!loading && items.length > 0 && activeTab !== 'my' && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((sub) => (
              <SubmissionCard
                key={sub.id}
                sub={sub}
                isOfficer={isOfficer && activeTab !== 'my'}
                onClick={() => handleCardClick(sub)}
              />
            ))}
          </div>
        )}

        {!loading && items.length > 0 && activeTab === 'my' && (
          <MySubmissionsView items={items} onCardClick={handleCardClick} />
        )}

        {detailLoading && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
            <Loader2 size={32} className="animate-spin text-white" />
          </div>
        )}
      </div>

      {/* Submission detail / review modal */}
      {selected && (
        <SubmissionModal
          submission={selected}
          isOfficer={isOfficer}
          onClose={() => setSelected(null)}
          onAction={handleAction}
        />
      )}
    </div>
  );
}
