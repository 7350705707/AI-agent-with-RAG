import React, { useState } from 'react';
import { Bot, LogIn, UserPlus, Loader2, AlertCircle, CheckCircle, Clock } from 'lucide-react';
import { login, signup } from '../api';

// -- Password strength calculator -----------------------------------------
function getPasswordStrength(pw) {
  if (!pw) return { score: 0, label: '', color: '' };
  let score = 0;
  if (pw.length >= 8) score++;
  if (/[A-Z]/.test(pw)) score++;
  if (/[0-9]/.test(pw)) score++;
  if (/[^A-Za-z0-9]/.test(pw)) score++;
  const map = [
    { label: 'Too short', color: 'bg-red-400' },
    { label: 'Weak',      color: 'bg-red-400' },
    { label: 'Fair',      color: 'bg-orange-400' },
    { label: 'Good',      color: 'bg-yellow-400' },
    { label: 'Strong',    color: 'bg-emerald-500' },
  ];
  return { score, ...map[score] };
}

export default function LoginPage({ onLogin }) {
  const [tab, setTab] = useState('login'); // 'login' | 'signup'
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [signupPending, setSignupPending] = useState(false);

  const strength = tab === 'signup' ? getPasswordStrength(password) : null;

  const reset = () => {
    setUsername('');
    setPassword('');
    setConfirmPw('');
    setError('');
    setSignupPending(false);
  };

  const switchTab = (t) => {
    setTab(t);
    reset();
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) return;

    if (tab === 'signup') {
      if (password.length < 8) {
        setError('Password must be at least 8 characters');
        return;
      }
      if (!/[A-Z]/.test(password)) {
        setError('Password must contain at least one uppercase letter');
        return;
      }
      if (!/[0-9]/.test(password)) {
        setError('Password must contain at least one digit');
        return;
      }
      if (!/[^A-Za-z0-9]/.test(password)) {
        setError('Password must contain at least one special character');
        return;
      }
      if (password !== confirmPw) {
        setError('Passwords do not match');
        return;
      }
    }

    setError('');
    setLoading(true);
    try {
      if (tab === 'login') {
        const data = await login(username.trim(), password);
        onLogin(data.user);
      } else {
        const data = await signup(username.trim(), password);
        if (data.pending_approval) {
          setSignupPending(true);
        } else {
          onLogin(data.user);
        }
      }
    } catch (err) {
      setError(err.message || `${tab === 'login' ? 'Login' : 'Signup'} failed`);
    } finally {
      setLoading(false);
    }
  };

  // -- Pending approval screen ------------------------------------------
  if (signupPending) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center px-4">
        <div className="w-full max-w-sm text-center">
          <div className="w-16 h-16 rounded-full bg-amber-100 flex items-center justify-center mx-auto mb-4">
            <Clock size={32} className="text-amber-500" />
          </div>
          <h2 className="text-xl font-semibold text-slate-900 mb-2">Account Pending Approval</h2>
          <p className="text-sm text-slate-500 mb-6 leading-relaxed">
            Your account <strong className="text-slate-700">@{username}</strong> has been created
            and is awaiting admin approval. You will be able to sign in once an admin activates your account.
          </p>
          <button
            onClick={() => { setSignupPending(false); setTab('login'); reset(); setUsername(username); }}
            className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg py-2.5 text-sm font-medium transition"
          >
            <LogIn size={16} />
            Back to Sign In
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Brand */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-14 h-14 rounded-2xl bg-blue-600/10 flex items-center justify-center mb-4">
            <Bot size={28} className="text-blue-500" />
          </div>
          <h1 className="text-xl font-semibold text-slate-900">EduQuest Ecosystem</h1>
          <p className="text-sm text-slate-500 mt-1">
            {tab === 'login' ? 'Sign in to your account' : 'Create a new account'}
          </p>
        </div>

        {/* Tabs */}
        <div className="flex mb-4 bg-white rounded-xl border border-slate-200 p-1 shadow-sm">
          <button
            onClick={() => switchTab('login')}
            className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-sm font-medium transition ${
              tab === 'login'
                ? 'bg-slate-100 text-slate-800 shadow-sm'
                : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            <LogIn size={14} />
            Sign In
          </button>
          <button
            onClick={() => switchTab('signup')}
            className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-sm font-medium transition ${
              tab === 'signup'
                ? 'bg-slate-100 text-slate-800 shadow-sm'
                : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            <UserPlus size={14} />
            Sign Up
          </button>
        </div>

        {/* Signup info notice */}
        {tab === 'signup' && (
          <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-3 text-xs text-amber-700">
            <Clock size={14} className="shrink-0 mt-0.5" />
            <span>New accounts require admin approval before you can sign in.</span>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="bg-white rounded-2xl border border-slate-200 p-6 space-y-4 shadow-sm">
          {error && (
            <div className="flex items-center gap-2 text-red-500 bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm">
              <AlertCircle size={16} className="shrink-0" />
              {error}
            </div>
          )}

          <div>
            <label className="block text-xs text-slate-500 mb-1.5 uppercase tracking-wider">Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2.5 text-sm text-slate-800 placeholder-slate-400 outline-none focus:border-blue-500 transition"
              placeholder="Enter username"
              autoFocus
              autoComplete="username"
            />
          </div>

          <div>
            <label className="block text-xs text-slate-500 mb-1.5 uppercase tracking-wider">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2.5 text-sm text-slate-800 placeholder-slate-400 outline-none focus:border-blue-500 transition"
              placeholder="Enter password"
              autoComplete={tab === 'login' ? 'current-password' : 'new-password'}
            />
            {/* Password strength indicator (signup only) */}
            {tab === 'signup' && password.length > 0 && (
              <div className="mt-2">
                <div className="flex gap-1 mb-1">
                  {[1, 2, 3, 4].map((i) => (
                    <div
                      key={i}
                      className={`flex-1 h-1 rounded-full transition-all ${
                        strength.score >= i ? strength.color : 'bg-slate-200'
                      }`}
                    />
                  ))}
                </div>
                <p className="text-xs text-slate-400">{strength.label} � must have 8+ chars, uppercase, digit &amp; special char</p>
              </div>
            )}
          </div>

          {tab === 'signup' && (
            <div>
              <label className="block text-xs text-slate-500 mb-1.5 uppercase tracking-wider">Confirm Password</label>
              <input
                type="password"
                value={confirmPw}
                onChange={(e) => setConfirmPw(e.target.value)}
                className="w-full bg-slate-50 border border-slate-300 rounded-lg px-3 py-2.5 text-sm text-slate-800 placeholder-slate-400 outline-none focus:border-blue-500 transition"
                placeholder="Confirm password"
                autoComplete="new-password"
              />
            </div>
          )}

          <button
            type="submit"
            disabled={loading || !username.trim() || !password.trim() || (tab === 'signup' && !confirmPw.trim())}
            className={`w-full flex items-center justify-center gap-2 ${
              tab === 'login'
                ? 'bg-blue-600 hover:bg-blue-500'
                : 'bg-emerald-600 hover:bg-emerald-500'
            } disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg py-2.5 text-sm font-medium transition`}
          >
            {loading ? (
              <Loader2 size={16} className="animate-spin" />
            ) : tab === 'login' ? (
              <LogIn size={16} />
            ) : (
              <UserPlus size={16} />
            )}
            {loading
              ? (tab === 'login' ? 'Signing in�' : 'Creating account�')
              : (tab === 'login' ? 'Sign In' : 'Create Account')}
          </button>
        </form>

        <p className="text-center text-xs text-slate-400 mt-4">
          EduQuest Ecosystem � Secure Offline Intranet Application
        </p>
      </div>
    </div>
  );
}

