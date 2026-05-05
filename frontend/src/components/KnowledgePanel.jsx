import React, { useState, useEffect, useRef } from 'react';
import {
  BookOpen,
  Upload,
  Trash2,
  Loader2,
  FileText,
  AlertCircle,
  CheckCircle2,
  XCircle,
  HardDriveDownload,
  Download,
  Pencil,
  Check,
  X,
  RefreshCw,
  Zap,
} from 'lucide-react';
import { uploadKnowledgeDoc, listKnowledgeDocs, deleteKnowledgeDoc, clearKnowledgeBase, getKnowledgeDocUrl, renameKnowledgeDoc, indexKnowledgeDoc } from '../api';

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function KnowledgePanel() {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadQueue, setUploadQueue] = useState([]); // [{name, pct, status}]
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [clearing, setClearing] = useState(false);
  const [renamingId, setRenamingId] = useState(null);
  const [renameValue, setRenameValue] = useState('');
  const [indexingIds, setIndexingIds] = useState(new Set());
  const fileRef = useRef(null);
  const renameInputRef = useRef(null);

  const refresh = async () => {
    try {
      setLoading(true);
      const docs = await listKnowledgeDocs();
      setDocuments(docs);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); }, []);

  // Auto-clear messages
  useEffect(() => {
    if (error) { const t = setTimeout(() => setError(''), 5000); return () => clearTimeout(t); }
  }, [error]);
  useEffect(() => {
    if (success) { const t = setTimeout(() => setSuccess(''), 4000); return () => clearTimeout(t); }
  }, [success]);

  const handleUpload = async (e) => {
    const files = Array.from(e.target.files);
    if (!files.length) return;
    setUploading(true);
    setError('');
    // Initialise queue with all files at 0%
    const initial = files.map((f) => ({ name: f.name, pct: 0, status: 'pending' }));
    setUploadQueue(initial);
    let uploaded = 0;
    let duplicates = 0;
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      setUploadQueue((prev) => prev.map((item, idx) => idx === i ? { ...item, status: 'uploading' } : item));
      try {
        const doc = await uploadKnowledgeDoc(file, (pct) => {
          setUploadQueue((prev) => prev.map((item, idx) =>
            idx === i ? { ...item, pct, status: pct === 100 ? 'saving' : 'uploading' } : item
          ));
        });
        setUploadQueue((prev) => prev.map((item, idx) => idx === i ? { ...item, pct: 100, status: 'done' } : item));
        setDocuments((prev) => [doc, ...prev.filter((d) => d.id !== doc.id)]);
        uploaded++;
      } catch (err) {
        if (err.isDuplicate) {
          duplicates++;
          setUploadQueue((prev) => prev.map((item, idx) => idx === i ? { ...item, pct: 100, status: 'duplicate' } : item));
        } else {
          setUploadQueue((prev) => prev.map((item, idx) => idx === i ? { ...item, status: 'error' } : item));
          setError(`Failed to upload ${file.name}: ${err.message}`);
        }
      }
    }
    const msgs = [];
    if (uploaded > 0) msgs.push(`${uploaded} document${uploaded > 1 ? 's' : ''} added to library.`);
    if (duplicates > 0) msgs.push(`${duplicates} duplicate file${duplicates > 1 ? 's' : ''} skipped.`);
    if (msgs.length) setSuccess(msgs.join(' '));
    setUploading(false);
    // Keep queue visible briefly then clear
    setTimeout(() => setUploadQueue([]), 3000);
    fileRef.current.value = '';
    refresh(); // immediate sync after upload
  };

  const handleDelete = async (docId, filename) => {
    if (!confirm(`Remove "${filename}" from the library?`)) return;
    try {
      await deleteKnowledgeDoc(docId);
      setSuccess(`"${filename}" removed.`);
      refresh();
    } catch (e) {
      setError(e.message);
    }
  };

  const handleClear = async () => {
    if (!confirm('Clear the entire library? This will remove all documents.')) return;
    setClearing(true);
    try {
      await clearKnowledgeBase();
      setSuccess('Library cleared.');
      setDocuments([]);
    } catch (e) {
      setError(e.message);
    } finally {
      setClearing(false);
    }
  };

  const startRename = (doc) => {
    setRenamingId(doc.id);
    setRenameValue(doc.filename);
    setTimeout(() => renameInputRef.current?.focus(), 50);
  };

  const cancelRename = () => {
    setRenamingId(null);
    setRenameValue('');
  };

  const commitRename = async (docId) => {
    const newName = renameValue.trim();
    if (!newName) return cancelRename();
    try {
      await renameKnowledgeDoc(docId, newName);
      setDocuments((prev) => prev.map((d) => d.id === docId ? { ...d, filename: newName } : d));
      setSuccess(`Renamed to "${newName}".`);
    } catch (e) {
      setError(e.message);
    } finally {
      cancelRename();
    }
  };

  const handleRenameKeyDown = (e, docId) => {
    if (e.key === 'Enter') { e.preventDefault(); commitRename(docId); }
    if (e.key === 'Escape') cancelRename();
  };

  const handleIndex = async (docId, filename) => {
    setIndexingIds((prev) => new Set([...prev, docId]));
    try {
      await indexKnowledgeDoc(docId);
      setSuccess(`Indexing started for "${filename}". Refresh in a moment to see chunk count.`);
    } catch (e) {
      setError(`Failed to start indexing: ${e.message}`);
    } finally {
      setIndexingIds((prev) => { const s = new Set(prev); s.delete(docId); return s; });
      setTimeout(() => refresh(), 3000);
    }
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="shrink-0 border-b border-purple-100 px-6 py-4 bg-gradient-to-r from-white to-purple-50/60">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-purple-100 flex items-center justify-center">
            <BookOpen size={18} className="text-purple-600" />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-slate-800">Library Base</h1>
            <p className="text-xs text-slate-500">
              Upload reference documents to teach the AI. The chat agent will cite these sources when answering questions.
            </p>
          </div>
        </div>
      </div>

      {/* Alerts */}
      {error && (
        <div className="mx-6 mt-4 flex items-center gap-2 px-4 py-2.5 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
          <AlertCircle size={16} className="shrink-0" /> {error}
        </div>
      )}
      {success && (
        <div className="mx-6 mt-4 flex items-center gap-2 px-4 py-2.5 bg-emerald-500/10 border border-emerald-500/20 rounded-lg text-emerald-400 text-sm">
          <CheckCircle2 size={16} className="shrink-0" /> {success}
        </div>
      )}

      {/* Upload area */}
      <div className="shrink-0 px-6 pt-5 pb-3">
        <div
          className="border-2 border-dashed border-gray-700 hover:border-emerald-500/40 rounded-xl p-6 text-center transition cursor-pointer"
          onClick={() => !uploading && fileRef.current?.click()}
        >
          {uploading ? (
            <div className="flex flex-col items-center gap-2">
              <Loader2 size={28} className="text-emerald-400 animate-spin" />
              <p className="text-sm text-gray-400">
                Uploading {uploadQueue.length} file{uploadQueue.length !== 1 ? 's' : ''}…
              </p>
              <p className="text-xs text-gray-600">Uploaded documents can be manually indexed using the Index button</p>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-2">
              <Upload size={28} className="text-gray-500" />
              <p className="text-sm text-gray-400">
                Click to upload <strong className="text-gray-300">PDF, DOCX, or PPTX</strong> files
              </p>
              <p className="text-xs text-gray-600">Documents are split into chunks and indexed for AI retrieval</p>
            </div>
          )}
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx,.pptx"
            multiple
            className="hidden"
            onChange={handleUpload}
          />
        </div>
        {/* Per-file upload progress */}
        {uploadQueue.length > 0 && (
          <div className="mt-3 space-y-2">
            {uploadQueue.map((item, idx) => (
              <div key={idx} className="bg-gray-800/60 rounded-lg px-3 py-2">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-gray-300 truncate max-w-[70%]">{item.name}</span>
                  <span className={`text-xs font-medium ${
                    item.status === 'done' ? 'text-emerald-400'
                    : item.status === 'duplicate' ? 'text-yellow-400'
                    : item.status === 'error' ? 'text-red-400'
                    : item.status === 'saving' ? 'text-blue-300'
                    : 'text-gray-400'
                  }`}>
                    {item.status === 'done' ? 'Done ✓'
                      : item.status === 'duplicate' ? 'Duplicate'
                      : item.status === 'error' ? 'Error'
                      : item.status === 'saving' ? 'Saving…'
                      : `${item.pct}%`}
                  </span>
                </div>
                <div className="w-full bg-gray-700 rounded-full h-1.5">
                  <div
                    className={`h-1.5 rounded-full transition-all duration-200 ${
                      item.status === 'done' ? 'bg-emerald-500'
                      : item.status === 'duplicate' ? 'bg-yellow-500'
                      : item.status === 'error' ? 'bg-red-500'
                      : item.status === 'saving' ? 'bg-blue-400 animate-pulse'
                      : 'bg-blue-500'
                    }`}
                    style={{ width: `${item.pct}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Document list */}
      <div className="flex-1 overflow-y-auto px-6 pb-4">
        <div className="flex items-center justify-between mb-3">
          <p className="text-xs uppercase tracking-wider text-gray-500">
            Documents ({documents.length})
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={refresh}
              disabled={loading}
              title="Refresh document list"
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-indigo-50 hover:bg-indigo-100 text-indigo-600 border border-indigo-200 rounded-lg transition disabled:opacity-50"
            >
              <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
              Refresh
            </button>
            {documents.length > 0 && (
              <button
                onClick={handleClear}
                disabled={clearing}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-red-500/10 hover:bg-red-500/20 text-red-400 rounded-lg transition disabled:opacity-50"
              >
                {clearing ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
                Clear All
              </button>
            )}
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 size={24} className="text-gray-500 animate-spin" />
          </div>
        ) : documents.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-gray-600">
            <HardDriveDownload size={40} className="mb-3 opacity-40" />
            <p className="text-sm">No documents in the library yet.</p>
            <p className="text-xs mt-1">Upload files above to get started.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {documents.map((doc) => (
              <div
                key={doc.id}
                className="flex items-center justify-between px-4 py-3 bg-gray-800/50 border border-gray-800 rounded-lg group"
              >
                <div className="flex items-center gap-3 min-w-0 flex-1">
                  <FileText size={18} className="text-emerald-400/70 shrink-0" />
                  <div className="min-w-0 flex-1">
                    {renamingId === doc.id ? (
                      <div className="flex items-center gap-1">
                        <input
                          ref={renameInputRef}
                          value={renameValue}
                          onChange={(e) => setRenameValue(e.target.value)}
                          onKeyDown={(e) => handleRenameKeyDown(e, doc.id)}
                          className="flex-1 bg-white text-sm text-slate-800 rounded px-2 py-0.5 outline-none border border-blue-500 min-w-0"
                        />
                        <button onClick={() => commitRename(doc.id)} className="p-1 text-emerald-400 hover:text-emerald-300">
                          <Check size={13} />
                        </button>
                        <button onClick={cancelRename} className="p-1 text-gray-500 hover:text-red-400">
                          <X size={13} />
                        </button>
                      </div>
                    ) : (
                      <>
                        <p className="text-sm text-gray-200 truncate">{doc.filename}</p>
                        <p className="text-xs text-gray-500">
                          {formatBytes(doc.file_size)} ·{' '}
                          {doc.chunk_count === 0
                            ? <span className="text-yellow-500/80">not indexed</span>
                            : `${doc.chunk_count} chunks`}
                          {doc.uploaded_by && ` · by ${doc.uploaded_by}`}
                        </p>
                      </>
                    )}
                  </div>
                </div>
                {renamingId !== doc.id && (
                  <div className="flex items-center gap-1 shrink-0">
                    {doc.chunk_count === 0 && (
                      <button
                        onClick={() => handleIndex(doc.id, doc.filename)}
                        disabled={indexingIds.has(doc.id)}
                        className="flex items-center gap-1 px-2 py-1 rounded text-xs bg-amber-500/10 hover:bg-amber-500/20 text-amber-500 hover:text-amber-400 transition disabled:opacity-50"
                        title="Start indexing this document"
                      >
                        {indexingIds.has(doc.id)
                          ? <Loader2 size={12} className="animate-spin" />
                          : <Zap size={12} />}
                        Index
                      </button>
                    )}
                    <button
                      onClick={() => startRename(doc)}
                      className="p-1.5 rounded hover:bg-blue-500/20 text-gray-600 hover:text-blue-400 opacity-0 group-hover:opacity-100 transition"
                      title="Rename document"
                    >
                      <Pencil size={14} />
                    </button>
                    <a
                      href={getKnowledgeDocUrl(doc.id)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="p-1.5 rounded hover:bg-blue-500/20 text-gray-600 hover:text-blue-400 opacity-0 group-hover:opacity-100 transition"
                      title="Download document"
                    >
                      <Download size={14} />
                    </a>
                    <button
                      onClick={() => handleDelete(doc.id, doc.filename)}
                      className="p-1.5 rounded hover:bg-red-500/20 text-gray-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition"
                      title="Remove document"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
