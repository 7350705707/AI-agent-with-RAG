import React, { useState, useEffect, useRef } from 'react';
import { ChevronDown, Cpu, Check, RefreshCw } from 'lucide-react';
import { listModels, loadModel } from '../api';

export default function ModelSelector() {
  const [models, setModels] = useState([]);
  const [active, setActive] = useState('');
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const ref = useRef(null);

  const DEFAULT_MODEL = 'qwen2.5-7b-instruct-1m';

  const fetchModels = async () => {
    setLoading(true);
    try {
      const data = await listModels();
      const modelList = data.models || [];
      setModels(modelList);
      console.log(`Fetched models: ${modelList.map(m => m.id).join(', ')}`);

      const currentActive = data.active || '';
      // Auto-select and load default model if backend has no active model or
      // the active model doesn't match our preferred default
      const defaultMatch = modelList.find(m => m.id.includes(DEFAULT_MODEL));
      if (defaultMatch && !currentActive.includes(DEFAULT_MODEL)) {
        await loadModel(defaultMatch.id);
        console.log(`Auto-loaded default model: ${defaultMatch.id}`);
        setActive(defaultMatch.id);
      } else {
        console.log(`Current active model: ${currentActive}`);
        setActive(currentActive);
      }
    } catch { /* backend down */ }
    setLoading(false);
  };

  useEffect(() => { fetchModels(); }, []);

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleSelect = async (id) => {
    if (id === active) { setOpen(false); return; }
    try {
      await loadModel(id);
      setActive(id);
    } catch { /* ignore */ }
    setOpen(false);
  };

  // Display name: trim path prefixes, keep the model filename
  const displayName = (id) => {
    if (!id) return 'No model';
    const parts = id.split('/');
    return parts[parts.length - 1] || id;
  };

  return (
    <div ref={ref} className="relative w-full">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm bg-indigo-800/50 border border-indigo-700/60 transition text-left hover:bg-indigo-800/70"
      >
        <Cpu size={14} className="text-emerald-400 shrink-0" />
        <span className="truncate flex-1 text-indigo-100">{displayName(active)}</span>
        <ChevronDown size={14} className={`text-indigo-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute bottom-full mb-1 left-0 w-full bg-indigo-900 border border-indigo-700 rounded-lg shadow-2xl z-50 max-h-60 overflow-y-auto">
          {/* Refresh button */}
            <div className="flex items-center justify-between px-3 py-2 border-b border-indigo-800">
            <span className="text-[11px] uppercase tracking-wider text-indigo-400/70">LM Studio Models</span>
            <button
              onClick={(e) => { e.stopPropagation(); fetchModels(); }}
              className="p-1 rounded hover:bg-indigo-800 text-indigo-400 hover:text-indigo-200 transition"
              title="Refresh models"
            >
              <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
            </button>
          </div>

          {models.length === 0 && (
            <p className="px-3 py-3 text-xs text-indigo-400">
              {loading ? 'Loading…' : 'No models found. Is LM Studio running?'}
            </p>
          )}

          {models.map((m) => (
            <button
              key={m.id}
              onClick={() => handleSelect(m.id)}
              className={`w-full flex items-center gap-2 px-3 py-2 text-sm transition ${
                m.id === active
                  ? 'bg-indigo-500/30 text-white'
                  : 'hover:bg-indigo-800/60 text-indigo-200'
              }`}
            >
              {m.id === active ? <Check size={14} className="shrink-0" /> : <span className="w-[14px] shrink-0" />}
              <span className="truncate">{displayName(m.id)}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
