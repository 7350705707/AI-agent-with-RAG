import React, { useState, useEffect } from 'react';
import {
  Shield,
  Plus,
  Trash2,
  Save,
  Loader2,
  UserPlus,
  X,
  KeyRound,
  Check,
  AlertCircle,
} from 'lucide-react';
import { listUsers, createUser, updateUser, deleteUser as apiDeleteUser, resetUserPassword } from '../api';

const ALL_AGENTS = [
  { id: 'chat', label: 'RAG Chat' },
  { id: 'exam', label: 'Exam' },
  { id: 'knowledge', label: 'Knowledge Base' },
  { id: 'search', label: 'KB Search' },
];

export default function AdminPanel() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [error, setError] = useState('');

  // Create form
  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newRole, setNewRole] = useState('user');
  const [newAgents, setNewAgents] = useState(['chat']);
  const [creating, setCreating] = useState(false);

  // Password reset
  const [resetId, setResetId] = useState(null);
  const [resetPw, setResetPw] = useState('');

  // Edit tracking
  const [saving, setSaving] = useState({});

  const refresh = async () => {
    try {
      const data = await listUsers();
      setUsers(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); }, []);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!newUsername.trim() || !newPassword.trim()) return;
    setCreating(true);
    setError('');
    try {
      await createUser(newUsername.trim(), newPassword, newRole, newAgents);
      setNewUsername('');
      setNewPassword('');
      setNewRole('user');
      setNewAgents(['general']);
      setShowCreate(false);
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  };

  const handleToggleAgent = (userId, agentId) => {
    setUsers((prev) =>
      prev.map((u) => {
        if (u.id !== userId) return u;
        const has = u.agents.includes(agentId);
        return { ...u, agents: has ? u.agents.filter((a) => a !== agentId) : [...u.agents, agentId] };
      })
    );
  };

  const handleRoleChange = (userId, role) => {
    setUsers((prev) =>
      prev.map((u) => (u.id === userId ? { ...u, role } : u))
    );
  };

  const handleActiveToggle = (userId) => {
    setUsers((prev) =>
      prev.map((u) => (u.id === userId ? { ...u, is_active: !u.is_active } : u))
    );
  };

  const handleSave = async (user) => {
    setSaving((s) => ({ ...s, [user.id]: true }));
    setError('');
    try {
      await updateUser(user.id, {
        role: user.role,
        agents: user.agents,
        is_active: user.is_active,
      });
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving((s) => ({ ...s, [user.id]: false }));
    }
  };

  const handleDelete = async (userId) => {
    if (!confirm('Delete this user?')) return;
    setError('');
    try {
      await apiDeleteUser(userId);
      await refresh();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleResetPassword = async () => {
    if (!resetPw.trim() || resetPw.length < 4) return;
    setError('');
    try {
      await resetUserPassword(resetId, resetPw);
      setResetId(null);
      setResetPw('');
    } catch (err) {
      setError(err.message);
    }
  };

  const toggleNewAgent = (agentId) => {
    setNewAgents((prev) =>
      prev.includes(agentId) ? prev.filter((a) => a !== agentId) : [...prev, agentId]
    );
  };

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 size={24} className="animate-spin text-gray-500" />
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col h-full">
      {/* Header */}
      <header className="shrink-0 flex items-center justify-between px-6 py-4 border-b border-amber-100 bg-gradient-to-r from-white to-amber-50/60">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-amber-100 flex items-center justify-center">
            <Shield size={16} className="text-amber-600" />
          </div>
          <h1 className="text-base font-semibold text-slate-800">Admin Panel â€“ User Management</h1>
        </div>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm transition"
        >
          {showCreate ? <X size={14} /> : <UserPlus size={14} />}
          {showCreate ? 'Cancel' : 'Add User'}
        </button>
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-4">
        {/* Error */}
        {error && (
          <div className="flex items-center gap-2 text-red-400 bg-red-400/10 rounded-lg px-3 py-2 text-sm mb-4">
            <AlertCircle size={16} />
            {error}
            <button onClick={() => setError('')} className="ml-auto text-gray-500 hover:text-gray-300"><X size={14} /></button>
          </div>
        )}

        {/* Create Form */}
        {showCreate && (
          <form onSubmit={handleCreate} className="bg-white rounded-xl border border-slate-200 shadow-sm p-4 mb-6 space-y-3">
            <h2 className="text-sm font-medium text-slate-700 mb-2">Create New User</h2>
            <div className="grid grid-cols-2 gap-3">
              <input
                type="text"
                placeholder="Username"
                value={newUsername}
                onChange={(e) => setNewUsername(e.target.value)}
                className="bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-sm text-slate-800 placeholder-slate-400 outline-none focus:border-blue-500"
                autoFocus
              />
              <input
                type="password"
                placeholder="Password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-sm text-slate-800 placeholder-slate-400 outline-none focus:border-blue-500"
              />
            </div>
            <div className="flex items-center gap-4">
              <label className="text-xs text-slate-500">Role:</label>
              <select
                value={newRole}
                onChange={(e) => setNewRole(e.target.value)}
                className="bg-slate-50 border border-slate-300 rounded-lg px-3 py-1.5 text-sm text-slate-800 outline-none focus:border-blue-500"
              >
                <option value="user">User</option>
                <option value="admin">Admin</option>
              </select>
              <label className="text-xs text-slate-500 ml-4">Agents:</label>
              {ALL_AGENTS.map((a) => (
                <label key={a.id} className="flex items-center gap-1.5 text-sm text-slate-600 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={newAgents.includes(a.id)}
                    onChange={() => toggleNewAgent(a.id)}
                    className="rounded border-slate-300 bg-white text-blue-600 focus:ring-blue-500"
                  />
                  {a.label}
                </label>
              ))}
            </div>
            <button
              type="submit"
              disabled={creating || !newUsername.trim() || !newPassword.trim()}
              className="flex items-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 rounded-lg text-sm transition"
            >
              {creating ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
              Create User
            </button>
          </form>
        )}

        {/* Users Table */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className="text-left px-4 py-3 text-xs text-slate-500 uppercase tracking-wider">Username</th>
                <th className="text-left px-4 py-3 text-xs text-slate-500 uppercase tracking-wider">Role</th>
                <th className="text-left px-4 py-3 text-xs text-slate-500 uppercase tracking-wider">Agent Access</th>
                <th className="text-center px-4 py-3 text-xs text-slate-500 uppercase tracking-wider">Active</th>
                <th className="text-right px-4 py-3 text-xs text-slate-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {users.map((u) => (
                <tr key={u.id} className="hover:bg-slate-50 transition">
                  <td className="px-4 py-3 text-slate-800 font-medium">
                    {u.username}
                    {u.username === 'admin' && (
                      <span className="ml-2 text-[10px] bg-amber-100 text-amber-600 px-1.5 py-0.5 rounded">DEFAULT</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <select
                      value={u.role}
                      onChange={(e) => handleRoleChange(u.id, e.target.value)}
                      disabled={u.username === 'admin'}
                      className="bg-white border border-slate-300 rounded px-2 py-1 text-xs text-slate-700 outline-none focus:border-blue-500 disabled:opacity-50"
                    >
                      <option value="user">User</option>
                      <option value="admin">Admin</option>
                    </select>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1.5 flex-wrap">
                      {ALL_AGENTS.map((a) => {
                        const enabled = u.agents.includes(a.id);
                        return (
                          <button
                            key={a.id}
                            type="button"
                            onClick={() => handleToggleAgent(u.id, a.id)}
                            className={`px-2.5 py-1 rounded-full text-xs font-medium transition-all border ${
                              enabled
                                ? 'bg-blue-600/20 text-blue-400 border-blue-500/50'
                                : 'bg-white text-slate-400 border-slate-300 hover:border-slate-400'
                            }`}
                          >
                            {a.label}
                          </button>
                        );
                      })}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <button
                      onClick={() => handleActiveToggle(u.id)}
                      disabled={u.username === 'admin'}
                      className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium transition-all border ${
                        u.is_active
                          ? 'bg-emerald-600/20 text-emerald-400 border-emerald-500/50'
                          : 'bg-gray-800 text-gray-500 border-gray-700'
                      } ${u.username === 'admin' ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:opacity-80'}`}
                    >
                      <span className={`w-1.5 h-1.5 rounded-full ${u.is_active ? 'bg-emerald-400' : 'bg-gray-500'}`} />
                      {u.is_active ? 'Active' : 'Inactive'}
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        onClick={() => handleSave(u)}
                        disabled={saving[u.id]}
                        className="p-1.5 rounded hover:bg-slate-100 text-blue-500 hover:text-blue-600 transition"
                        title="Save changes"
                      >
                        {saving[u.id] ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                      </button>
                      <button
                        onClick={() => { setResetId(u.id); setResetPw(''); }}
                        className="p-1.5 rounded hover:bg-slate-100 text-amber-500 hover:text-amber-600 transition"
                        title="Reset password"
                      >
                        <KeyRound size={14} />
                      </button>
                      {u.username !== 'admin' && (
                        <button
                          onClick={() => handleDelete(u.id)}
                          className="p-1.5 rounded hover:bg-slate-100 text-red-400 hover:text-red-500 transition"
                          title="Delete user"
                        >
                          <Trash2 size={14} />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Password reset modal */}
        {resetId && (
          <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
            <div className="bg-white border border-slate-200 rounded-2xl shadow-xl p-6 w-80 space-y-4">
              <h3 className="text-sm font-medium text-slate-800">Reset Password</h3>
              <input
                type="password"
                placeholder="New password (min 4 chars)"
                value={resetPw}
                onChange={(e) => setResetPw(e.target.value)}
                className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-sm text-slate-800 placeholder-slate-400 outline-none focus:border-blue-500"
                autoFocus
              />
              <div className="flex gap-2 justify-end">
                <button
                  onClick={() => setResetId(null)}
                  className="px-3 py-1.5 rounded-lg text-sm text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition"
                >
                  Cancel
                </button>
                <button
                  onClick={handleResetPassword}
                  disabled={resetPw.length < 4}
                  className="flex items-center gap-1 px-3 py-1.5 bg-amber-600 hover:bg-amber-500 disabled:opacity-40 rounded-lg text-sm transition"
                >
                  <Check size={14} />
                  Reset
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

