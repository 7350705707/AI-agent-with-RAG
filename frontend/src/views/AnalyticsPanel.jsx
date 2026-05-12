import React, { useState, useEffect } from 'react';
import { BarChart2, Loader2, AlertCircle, Users, MessageSquare, BookOpen, MessagesSquare } from 'lucide-react';
import { getAnalyticsSummary, getMyAnalytics } from '../api';

function StatCard({ icon: Icon, label, value, color = 'indigo' }) {
  const colors = {
    indigo: 'bg-indigo-50 text-indigo-600',
    blue: 'bg-blue-50 text-blue-600',
    emerald: 'bg-emerald-50 text-emerald-600',
    purple: 'bg-purple-50 text-purple-600',
  };
  return (
    <div className="bg-white border border-slate-200 rounded-xl px-5 py-4 flex items-center gap-4 shadow-sm">
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${colors[color]}`}>
        <Icon size={20} />
      </div>
      <div>
        <p className="text-xs text-slate-500">{label}</p>
        <p className="text-2xl font-bold text-slate-800">{value ?? '—'}</p>
      </div>
    </div>
  );
}

function BarRow({ label, value, max, color = 'bg-indigo-500' }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-slate-600 w-28 shrink-0 capitalize">{label}</span>
      <div className="flex-1 bg-slate-100 rounded-full h-2.5">
        <div className={`h-2.5 rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-slate-500 w-10 text-right">{value}</span>
    </div>
  );
}

export default function AnalyticsPanel({ user }) {
  const isAdmin = user?.role === 'admin';
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetch = async () => {
      setLoading(true);
      setError('');
      try {
        const res = isAdmin ? await getAnalyticsSummary() : await getMyAnalytics();
        setData(res);
      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    };
    fetch();
  }, [isAdmin]);

  return (
    <div className="flex-1 flex flex-col h-full">
      {/* Header */}
      <header className="shrink-0 flex items-center gap-2 px-6 py-4 border-b border-indigo-100 bg-gradient-to-r from-white to-indigo-50/60">
        <div className="w-8 h-8 rounded-lg bg-indigo-100 flex items-center justify-center">
          <BarChart2 size={16} className="text-indigo-600" />
        </div>
        <h1 className="text-base font-semibold text-slate-800">Analytics</h1>
        <span className="ml-2 text-xs text-slate-400">{isAdmin ? 'Admin view' : 'My stats'}</span>
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-5">
        {loading && (
          <div className="flex items-center justify-center py-16 gap-2 text-indigo-500">
            <Loader2 size={20} className="animate-spin" />
            <span className="text-sm">Loading analytics…</span>
          </div>
        )}
        {error && (
          <div className="flex items-center gap-2 px-4 py-3 bg-red-50 border border-red-200 rounded-lg text-red-600 text-sm">
            <AlertCircle size={16} /> {error}
          </div>
        )}
        {data && !loading && (
          <div className="space-y-6">
            {/* Stat cards */}
            {isAdmin ? (
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <StatCard icon={MessageSquare} label="Total Messages" value={data.total_messages} color="indigo" />
                <StatCard icon={Users} label="Total Users" value={data.total_users} color="blue" />
                <StatCard icon={BookOpen} label="Documents" value={data.total_documents} color="emerald" />
                <StatCard icon={MessagesSquare} label="Conversations" value={data.total_conversations} color="purple" />
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-4">
                <StatCard icon={MessageSquare} label="My Messages" value={data.total_messages} color="indigo" />
                <StatCard icon={MessagesSquare} label="My Conversations" value={data.total_conversations} color="purple" />
              </div>
            )}

            {/* Messages by agent */}
            {data.by_agent && Object.keys(data.by_agent).length > 0 && (
              <div className="bg-white border border-slate-200 rounded-xl px-5 py-4 shadow-sm">
                <h2 className="text-sm font-semibold text-slate-700 mb-3">Messages by Agent</h2>
                <div className="space-y-2">
                  {Object.entries(data.by_agent)
                    .sort((a, b) => b[1] - a[1])
                    .map(([agent, count]) => (
                      <BarRow
                        key={agent}
                        label={agent}
                        value={count}
                        max={Math.max(...Object.values(data.by_agent))}
                        color="bg-indigo-500"
                      />
                    ))}
                </div>
              </div>
            )}

            {/* Daily messages (last 14 days) */}
            {data.daily_messages && data.daily_messages.length > 0 && (
              <div className="bg-white border border-slate-200 rounded-xl px-5 py-4 shadow-sm">
                <h2 className="text-sm font-semibold text-slate-700 mb-3">Daily Messages (Last 14 Days)</h2>
                {(() => {
                  const maxVal = Math.max(...data.daily_messages.map((d) => d.count), 1);
                  return (
                    <div className="space-y-1.5">
                      {data.daily_messages.map((row) => (
                        <BarRow key={row.date} label={row.date} value={row.count} max={maxVal} color="bg-blue-400" />
                      ))}
                    </div>
                  );
                })()}
              </div>
            )}

            {/* Top users (admin only) */}
            {isAdmin && data.top_users && data.top_users.length > 0 && (
              <div className="bg-white border border-slate-200 rounded-xl px-5 py-4 shadow-sm">
                <h2 className="text-sm font-semibold text-slate-700 mb-3">Top Users</h2>
                <table className="w-full text-xs text-slate-600">
                  <thead>
                    <tr className="text-left text-slate-400 border-b border-slate-100">
                      <th className="pb-2 font-medium">User</th>
                      <th className="pb-2 font-medium text-right">Messages</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.top_users.map((u, i) => (
                      <tr key={i} className="border-b border-slate-50 last:border-0">
                        <td className="py-1.5">{u.user_id || 'anonymous'}</td>
                        <td className="py-1.5 text-right font-medium text-slate-800">{u.count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
