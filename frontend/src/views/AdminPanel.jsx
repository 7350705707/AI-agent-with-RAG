import React, { useState, useEffect, useCallback } from 'react';
import {
  Shield,
  Plus,
  Trash2,
  Loader2,
  UserPlus,
  X,
  KeyRound,
  Check,
  AlertCircle,
  Edit2,
  UserCheck,
  Clock,
  CheckCircle,
  RefreshCw,
} from 'lucide-react';
import {
  listUsers,
  createUser,
  updateUser,
  deleteUser as apiDeleteUser,
  resetUserPassword,
  listPendingUsers,
  approveUser,
} from '../api';

const ALL_AGENTS = [
  { id: 'chat', label: 'RAG Chat' },
  { id: 'exam', label: 'Exam' },
  { id: 'knowledge', label: 'Knowledge Base' },
  { id: 'search', label: 'KB Search' },
  { id: 'approval', label: 'Approver' },
];

// -- Toast ----------------------------------------------------------------

function Toast({ message, type, onClose }) {
  useEffect(() => {
    const t = setTimeout(onClose, 3500);
    return () => clearTimeout(t);
  }, [onClose]);
  const colors = type === 'success'
    ? 'bg-emerald-600 text-white'
    : 'bg-red-600 text-white';
  return (
    <div className={`fixed top-4 right-4 z-[100] flex items-center gap-2 px-4 py-2.5 rounded-xl shadow-lg text-sm font-medium ${colors}`}>
      {type === 'success' ? <CheckCircle size={15} /> : <AlertCircle size={15} />}
      {message}
      <button onClick={onClose} className="ml-2 opacity-70 hover:opacity-100"><X size={14} /></button>
    </div>
  );
}

// -- Edit User Modal ------------------------------------------------------

function EditUserModal({ user: u, onClose, onSave }) {
  const [role, setRole] = useState(u.role);
  const [agents, setAgents] = useState([...(u.agents || [])]);
  const [isActive, setIsActive] = useState(u.is_active);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const toggleAgent = (id) => {
    setAgents((prev) => prev.includes(id) ? prev.filter((a) => a !== id) : [...prev, id]);
  };

  const handleSave = async () => {
    setSaving(true);
    setError('');
    try {
      await onSave(u.id, { role, agents, is_active: isActive });
      onClose();
    } catch (err) {
      setError(err.message || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
          <h2 className="text-sm font-semibold text-slate-800">Edit User � {u.username}</h2>
          <button onClick={onClose} className="p-1.5 rounded hover:bg-slate-100 text-slate-400 transition"><X size={16} /></button>
        </div>
        <div className="px-6 py-5 space-y-5">
          {error && (
            <div className="flex items-center gap-2 text-red-500 bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm">
              <AlertCircle size={14} /> {error}
            </div>
          )}
          {/* Role */}
          <div>
            <label className="block text-xs text-slate-500 mb-1.5 uppercase tracking-wider">Role</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              disabled={u.username === 'admin'}
              className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-sm text-slate-800 outline-none focus:border-blue-500 disabled:opacity-50"
            >
              <option value="user">User</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          {/* Agents */}
          <div>
            <label className="block text-xs text-slate-500 mb-2 uppercase tracking-wider">Agent Access</label>
            <div className="flex flex-wrap gap-2">
              {ALL_AGENTS.map((a) => {
                const on = agents.includes(a.id);
                return (
                  <button
                    key={a.id}
                    type="button"
                    onClick={() => toggleAgent(a.id)}
                    className={`px-3 py-1.5 rounded-full text-xs font-medium transition border ${
                      on ? 'bg-blue-100 border-blue-400 text-blue-700' : 'bg-white border-slate-300 text-slate-500 hover:border-slate-400'
                    }`}
                  >
                    {a.label}
                  </button>
                );
              })}
            </div>
          </div>
          {/* Active toggle */}
          <div className="flex items-center justify-between">
            <label className="text-xs text-slate-500 uppercase tracking-wider">Account Active</label>
            <button
              type="button"
              disabled={u.username === 'admin'}
              onClick={() => setIsActive((v) => !v)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition ${isActive ? 'bg-emerald-500' : 'bg-slate-300'} disabled:opacity-50`}
            >
              <span className={`inline-block h-4 w-4 rounded-full bg-white shadow transition transform ${isActive ? 'translate-x-6' : 'translate-x-1'}`} />
            </button>
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-slate-100">
          <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm text-slate-600 hover:bg-slate-100 transition">Cancel</button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition"
          >
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
            Save Changes
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AdminPanel() {
  const [users, setUsers] = useState([]);
  const [pendingUsers, setPendingUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [error, setError] = useState('');
  const [toast, setToast] = useState(null); // { message, type }
  const [editUser, setEditUser] = useState(null); // user being edited in modal

  // Create form
  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newRole, setNewRole] = useState('user');
  const [newAgents, setNewAgents] = useState(['chat']);
  const [creating, setCreating] = useState(false);

  // Password reset
  const [resetId, setResetId] = useState(null);
  const [resetPw, setResetPw] = useState('');

  const showToast = (message, type = 'success') => setToast({ message, type });

  const refresh = useCallback(async () => {
    try {
      const [all, pending] = await Promise.all([listUsers(), listPendingUsers()]);
      setUsers(all);
      setPendingUsers(pending);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

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
      setNewAgents(['chat']);
      setShowCreate(false);
      await refresh();
      showToast('User created successfully');
    } catch (err) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  };

  const handleSaveUser = async (id, updates) => {
    await updateUser(id, updates);
    await refresh();
    showToast('User updated');
  };

  const handleDelete = async (userId, username) => {
    if (!confirm(`Delete user "${username}"?`)) return;
    setError('');
    try {
      await apiDeleteUser(userId);
      await refresh();
      showToast('User deleted');
    } catch (err) {
      setError(err.message);
    }
  };

  const handleApproveUser = async (userId) => {
    try {
      await approveUser(userId);
      await refresh();
      showToast('User approved and activated');
    } catch (err) {
      showToast(err.message || 'Approval failed', 'error');
    }
  };

  const handleResetPassword = async () => {
    if (!resetPw.trim() || resetPw.length < 4) return;
    setError('');
    try {
      await resetUserPassword(resetId, resetPw);
      setResetId(null);
      setResetPw('');
      showToast('Password reset');
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
      {/* Toast */}
      {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}

      {/* Edit User Modal */}
      {editUser && (
        <EditUserModal
          user={editUser}
          onClose={() => setEditUser(null)}
          onSave={handleSaveUser}
        />
      )}

      {/* Header */}
      <header className="shrink-0 flex items-center justify-between px-6 py-4 border-b border-amber-100 bg-gradient-to-r from-white to-amber-50/60">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-amber-100 flex items-center justify-center">
            <Shield size={16} className="text-amber-600" />
          </div>
          <h1 className="text-base font-semibold text-slate-800">Admin Panel � User Management</h1>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={refresh}
            className="p-2 rounded-lg hover:bg-slate-100 text-slate-500 transition"
            title="Refresh"
          >
            <RefreshCw size={15} />
          </button>
          <button
            onClick={() => setShowCreate(!showCreate)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm transition"
          >
            {showCreate ? <X size={14} /> : <UserPlus size={14} />}
            {showCreate ? 'Cancel' : 'Add User'}
          </button>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
        {/* Error */}
        {error && (
          <div className="flex items-center gap-2 text-red-500 bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm">
            <AlertCircle size={15} />
            {error}
            <button onClick={() => setError('')} className="ml-auto hover:text-red-700"><X size={14} /></button>
          </div>
        )}

        {/* Pending Approvals Section */}
        {pendingUsers.length > 0 && (
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-3">
              <Clock size={16} className="text-amber-600" />
              <h2 className="text-sm font-semibold text-amber-700">
                Pending Approvals ({pendingUsers.length})
              </h2>
            </div>
            <div className="space-y-2">
              {pendingUsers.map((u) => (
                <div key={u.id} className="flex items-center justify-between bg-white border border-amber-100 rounded-lg px-4 py-3">
                  <div>
                    <p className="text-sm font-medium text-slate-800">@{u.username}</p>
                    <p className="text-xs text-slate-500">Registered � awaiting admin activation</p>
                  </div>
                  <button
                    onClick={() => handleApproveUser(u.id)}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-medium transition"
                  >
                    <UserCheck size={13} />
                    Approve
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Create Form */}
        {showCreate && (
          <form onSubmit={handleCreate} className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 space-y-4">
            <h2 className="text-sm font-semibold text-slate-700">Create New User</h2>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-slate-500 mb-1">Username</label>
                <input
                  type="text"
                  placeholder="Username"
                  value={newUsername}
                  onChange={(e) => setNewUsername(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-sm text-slate-800 placeholder-slate-400 outline-none focus:border-blue-500"
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">Password</label>
                <input
                  type="password"
                  placeholder="Password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-sm text-slate-800 placeholder-slate-400 outline-none focus:border-blue-500"
                />
              </div>
            </div>
            <div className="flex items-center gap-4 flex-wrap">
              <div>
                <label className="block text-xs text-slate-500 mb-1">Role</label>
                <select
                  value={newRole}
                  onChange={(e) => setNewRole(e.target.value)}
                  className="bg-slate-50 border border-slate-300 rounded-lg px-3 py-2 text-sm text-slate-800 outline-none focus:border-blue-500"
                >
                  <option value="user">User</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">Agents</label>
                <div className="flex flex-wrap gap-2">
                  {ALL_AGENTS.map((a) => (
                    <label key={a.id} className="flex items-center gap-1.5 text-xs text-slate-600 cursor-pointer bg-white border border-slate-200 rounded-lg px-2.5 py-1.5 hover:border-slate-400 transition">
                      <input
                        type="checkbox"
                        checked={newAgents.includes(a.id)}
                        onChange={() => toggleNewAgent(a.id)}
                        className="accent-blue-600"
                      />
                      {a.label}
                    </label>
                  ))}
                </div>
              </div>
            </div>
            <div className="flex justify-end">
              <button
                type="submit"
                disabled={creating || !newUsername.trim() || !newPassword.trim()}
                className="flex items-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white rounded-lg text-sm font-medium transition"
              >
                {creating ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
                Create User
              </button>
            </div>
          </form>
        )}

        {/* Users Table */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className="text-left px-4 py-3 text-xs text-slate-500 uppercase tracking-wider">Username</th>
                <th className="text-left px-4 py-3 text-xs text-slate-500 uppercase tracking-wider">Role</th>
                <th className="text-left px-4 py-3 text-xs text-slate-500 uppercase tracking-wider">Agents</th>
                <th className="text-center px-4 py-3 text-xs text-slate-500 uppercase tracking-wider">Status</th>
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
                    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${
                      u.role === 'admin' ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-600'
                    }`}>{u.role}</span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1 flex-wrap">
                      {(u.agents || []).map((a) => (
                        <span key={a} className="px-2 py-0.5 rounded-full text-[10px] bg-blue-50 text-blue-600 border border-blue-200">
                          {ALL_AGENTS.find((x) => x.id === a)?.label || a}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium ${
                      u.is_active
                        ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                        : 'bg-slate-100 text-slate-500 border border-slate-200'
                    }`}>
                      <span className={`w-1.5 h-1.5 rounded-full ${u.is_active ? 'bg-emerald-500' : 'bg-slate-400'}`} />
                      {u.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        onClick={() => setEditUser(u)}
                        className="p-1.5 rounded hover:bg-blue-50 text-blue-500 hover:text-blue-700 transition"
                        title="Edit user"
                      >
                        <Edit2 size={14} />
                      </button>
                      <button
                        onClick={() => { setResetId(u.id); setResetPw(''); }}
                        className="p-1.5 rounded hover:bg-amber-50 text-amber-500 hover:text-amber-700 transition"
                        title="Reset password"
                      >
                        <KeyRound size={14} />
                      </button>
                      {u.username !== 'admin' && (
                        <button
                          onClick={() => handleDelete(u.id, u.username)}
                          className="p-1.5 rounded hover:bg-red-50 text-red-400 hover:text-red-600 transition"
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
          <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4">
            <div className="bg-white border border-slate-200 rounded-2xl shadow-xl p-6 w-80 space-y-4">
              <h3 className="text-sm font-semibold text-slate-800">Reset Password</h3>
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
                  className="flex items-center gap-1 px-3 py-1.5 bg-amber-600 hover:bg-amber-500 disabled:opacity-40 text-white rounded-lg text-sm transition"
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
