import React, { useState } from 'react';
import { UserCircle, Lock, CheckCircle, AlertCircle, Eye, EyeOff, X } from 'lucide-react';
import { changePassword } from '../api';

function Badge({ label }) {
  return (
    <span className="px-2 py-0.5 text-xs rounded-full bg-blue-600/20 text-blue-300 border border-blue-600/30">
      {label}
    </span>
  );
}

export default function UserProfilePanel({ user, onClose }) {
  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState(null); // { type: 'success'|'error', msg }

  const showToast = (type, msg) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 3500);
  };

  const strength = (() => {
    if (!newPw) return 0;
    let s = 0;
    if (newPw.length >= 8) s++;
    if (/[A-Z]/.test(newPw)) s++;
    if (/[0-9]/.test(newPw)) s++;
    if (/[^A-Za-z0-9]/.test(newPw)) s++;
    return s;
  })();
  const strengthLabel = ['', 'Weak', 'Fair', 'Good', 'Strong'][strength];
  const strengthColor = ['', 'bg-red-500', 'bg-amber-400', 'bg-yellow-400', 'bg-emerald-500'][strength];

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (newPw !== confirmPw) return showToast('error', 'New passwords do not match');
    if (newPw.length < 8) return showToast('error', 'Password must be at least 8 characters');
    setSaving(true);
    try {
      await changePassword(currentPw, newPw);
      setCurrentPw(''); setNewPw(''); setConfirmPw('');
      showToast('success', 'Password updated successfully');
    } catch (err) {
      showToast('error', err.message || 'Failed to update password');
    } finally {
      setSaving(false);
    }
  };

  return (
    /* Modal overlay */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }}
    >
      <div className="relative w-full max-w-md mx-4 bg-gray-900 border border-gray-700 rounded-2xl shadow-2xl overflow-y-auto max-h-[90vh]">
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-3 right-3 p-1.5 rounded-lg text-gray-500 hover:text-gray-200 hover:bg-gray-800 transition"
        >
          <X size={16} />
        </button>

        <div className="px-6 py-6">
          {/* Toast */}
          {toast && (
            <div className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm mb-5
              ${toast.type === 'success' ? 'bg-emerald-700/80 text-emerald-100' : 'bg-red-800/80 text-red-100'}`}>
              {toast.type === 'success' ? <CheckCircle size={14} /> : <AlertCircle size={14} />}
              {toast.msg}
            </div>
          )}

          {/* Header */}
          <div className="flex items-center gap-3 mb-6">
            <div className="w-11 h-11 rounded-xl bg-gray-700 flex items-center justify-center shrink-0">
              <UserCircle size={24} className="text-gray-400" />
            </div>
            <div>
              <h2 className="text-base font-bold text-gray-100">{user?.username || '—'}</h2>
              <p className="text-xs text-gray-400 capitalize">{user?.role || 'user'}</p>
            </div>
          </div>

          {/* Info card */}
          <div className="bg-gray-800/60 border border-gray-700 rounded-xl p-4 mb-5">
            <h3 className="text-xs uppercase tracking-wider text-gray-500 mb-3">Account Details</h3>
            <div className="space-y-2.5">
              <div>
                <p className="text-xs text-gray-500">Username</p>
                <p className="text-sm text-gray-200 mt-0.5">{user?.username}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Role</p>
                <p className="text-sm text-gray-200 mt-0.5 capitalize">{user?.role}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500 mb-1.5">Assigned Agents</p>
                <div className="flex flex-wrap gap-1.5">
                  {(user?.agents ?? []).length === 0
                    ? <span className="text-xs text-gray-600">No agents assigned</span>
                    : (user?.agents ?? []).map((a) => <Badge key={a} label={a} />)}
                </div>
              </div>
            </div>
          </div>

          {/* Change password */}
          <div className="bg-gray-800/60 border border-gray-700 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-4">
              <Lock size={13} className="text-gray-400" />
              <h3 className="text-xs uppercase tracking-wider text-gray-500">Change Password</h3>
            </div>
            <form onSubmit={handleSubmit} className="space-y-3">
              {/* Current password */}
              <div>
                <label className="block text-xs text-gray-400 mb-1">Current Password</label>
                <div className="relative">
                  <input
                    type={showCurrent ? 'text' : 'password'}
                    value={currentPw}
                    onChange={(e) => setCurrentPw(e.target.value)}
                    required
                    className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100
                      focus:outline-none focus:border-blue-500 pr-9"
                    placeholder="••••••••"
                  />
                  <button type="button" onClick={() => setShowCurrent((v) => !v)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300">
                    {showCurrent ? <EyeOff size={13} /> : <Eye size={13} />}
                  </button>
                </div>
              </div>

              {/* New password */}
              <div>
                <label className="block text-xs text-gray-400 mb-1">New Password</label>
                <div className="relative">
                  <input
                    type={showNew ? 'text' : 'password'}
                    value={newPw}
                    onChange={(e) => setNewPw(e.target.value)}
                    required
                    className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100
                      focus:outline-none focus:border-blue-500 pr-9"
                    placeholder="••••••••"
                  />
                  <button type="button" onClick={() => setShowNew((v) => !v)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300">
                    {showNew ? <EyeOff size={13} /> : <Eye size={13} />}
                  </button>
                </div>
                {newPw && (
                  <div className="mt-1.5">
                    <div className="flex gap-1 mb-0.5">
                      {[1, 2, 3, 4].map((n) => (
                        <div key={n} className={`h-1 flex-1 rounded-full ${n <= strength ? strengthColor : 'bg-gray-700'}`} />
                      ))}
                    </div>
                    <p className="text-xs text-gray-500">{strengthLabel}</p>
                  </div>
                )}
              </div>

              {/* Confirm password */}
              <div>
                <label className="block text-xs text-gray-400 mb-1">Confirm New Password</label>
                <input
                  type="password"
                  value={confirmPw}
                  onChange={(e) => setConfirmPw(e.target.value)}
                  required
                  className={`w-full bg-gray-900 border rounded-lg px-3 py-2 text-sm text-gray-100
                    focus:outline-none focus:border-blue-500
                    ${confirmPw && confirmPw !== newPw ? 'border-red-500' : 'border-gray-700'}`}
                  placeholder="••••••••"
                />
                {confirmPw && confirmPw !== newPw && (
                  <p className="text-xs text-red-400 mt-1">Passwords do not match</p>
                )}
              </div>

              <button
                type="submit"
                disabled={saving || !currentPw || !newPw || newPw !== confirmPw}
                className="w-full py-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-40
                  disabled:cursor-not-allowed text-sm font-medium transition mt-1"
              >
                {saving ? 'Updating…' : 'Update Password'}
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
