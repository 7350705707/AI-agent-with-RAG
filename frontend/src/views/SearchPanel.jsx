import React, { useState, useEffect } from 'react';
import { Search, Loader2, FileText, AlertCircle } from 'lucide-react';
import { searchKnowledge, getKnowledgeDocUrl } from '../api';

export default function SearchPanel() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSearch = async (e) => {
    e?.preventDefault();
    const q = query.trim();
    if (!q) return;
    setLoading(true);
    setError('');
    setResults(null);
    try {
      const data = await searchKnowledge(q, 12);
      setResults(data.results);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handleSearch();
  };

  return (
    <div className="flex-1 flex flex-col h-full">
      {/* Header */}
      <header className="shrink-0 flex items-center gap-2 px-6 py-4 border-b border-indigo-100 bg-gradient-to-r from-white to-indigo-50/60">
        <div className="w-8 h-8 rounded-lg bg-indigo-100 flex items-center justify-center">
          <Search size={16} className="text-indigo-600" />
        </div>
        <h1 className="text-base font-semibold text-slate-800">KB Semantic Search</h1>
      </header>

      {/* Search bar */}
      <div className="shrink-0 px-6 py-5">
        <div className="flex gap-2">
          <div className="flex-1 flex items-center gap-2 bg-white rounded-xl px-4 py-2.5 border border-slate-200 focus-within:border-indigo-500 shadow-sm">
            <Search size={16} className="text-slate-400 shrink-0" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Search your knowledge base semantically…"
              className="flex-1 bg-transparent outline-none text-sm text-slate-800 placeholder-slate-400"
            />
          </div>
          <button
            onClick={handleSearch}
            disabled={loading || !query.trim()}
            className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed transition"
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : 'Search'}
          </button>
        </div>
        {error && (
          <div className="mt-3 flex items-center gap-2 px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-red-600 text-xs">
            <AlertCircle size={14} /> {error}
          </div>
        )}
      </div>

      {/* Results */}
      <div className="flex-1 overflow-y-auto px-6 pb-6">
        {results === null && !loading && (
          <div className="flex flex-col items-center justify-center h-full text-gray-400 gap-2">
            <Search size={40} strokeWidth={1} />
            <p className="text-sm">Enter a query to search your knowledge base</p>
          </div>
        )}
        {loading && (
          <div className="flex items-center justify-center py-12 gap-2 text-indigo-500">
            <Loader2 size={20} className="animate-spin" />
            <span className="text-sm">Searching…</span>
          </div>
        )}
        {results !== null && !loading && results.length === 0 && (
          <div className="text-center text-gray-500 text-sm py-12">No matching results found.</div>
        )}
        {results && results.length > 0 && (
          <div className="space-y-3">
            <p className="text-xs text-gray-400">{results.length} result{results.length !== 1 ? 's' : ''} found</p>
            {results.map((r, i) => (
              <div key={i} className="bg-white border border-slate-200 rounded-xl px-4 py-3 shadow-sm">
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-1.5">
                    <FileText size={14} className="text-indigo-500 shrink-0" />
                    {r.doc_id ? (
                      <a
                        href={getKnowledgeDocUrl(r.doc_id)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm font-medium text-indigo-600 hover:underline truncate max-w-xs"
                      >
                        {r.filename}
                      </a>
                    ) : (
                      <span className="text-sm font-medium text-slate-700">{r.filename}</span>
                    )}
                  </div>
                  {r.score != null && (
                    <span className="text-xs text-gray-400 shrink-0 ml-2">
                      score: {typeof r.score === 'number' ? r.score.toFixed(3) : r.score}
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-600 leading-relaxed line-clamp-4">{r.snippet}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
