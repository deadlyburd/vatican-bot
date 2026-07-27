'use client';

import { useState, useEffect, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { Shield, Building2, Users, Activity, Plus, Edit, Trash2, ToggleLeft, ToggleRight, X, Check, BarChart3, Lock, RefreshCw } from 'lucide-react';

const AUTH = () => typeof window !== 'undefined' ? localStorage.getItem('session_token') : '';
const apiFetch = (path: string, opts: RequestInit = {}) =>
  fetch(`/api/v1/admin/${path}`, {
    ...opts,
    headers: { 'Authorization': `Bearer ${AUTH()}`, 'Content-Type': 'application/json', ...(opts.headers || {}) },
  });

type Agency = { id: number; name: string; plan: string; is_active: boolean; user_count: number; task_count: number; active_task_count: number; created_at: string; telegram_groups: any[]; telegram_chat_id?: string };
type User = { id: number; username: string; email: string; full_name: string; is_active: boolean; is_admin: boolean; agency: { id: number; name: string; plan: string }; last_login: string | null; task_count: number };
type Task = { id: number; agency: { id: number; name: string }; ticket_name: string; ticket_type: string; language: string; dates: string[]; visitors: number; is_active: boolean; last_checked: string | null; last_status: string };
type RecapSlot = { id: number; date: string; slot_time: string; ticket_name: string; visitors: number; total_price: string; status: string; recap_id: string; hold_started_at: string; age_hours: number; jsessionid: string | null };

// ── Recap Tab ─────────────────────────────────────────────────────────────────
function RecapView() {
  const [data, setData] = useState<{ slots: RecapSlot[]; total: number; by_status: any } | null>(null);
  const [loading, setLoading] = useState(true);
  const [filterDate, setFilterDate] = useState('');
  const [filterMonth, setFilterMonth] = useState('all');

  const load = async () => {
    setLoading(true);
    try {
      const r = await apiFetch('recap/');
      const d = await r.json();
      setData(d);
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => {
    if (!data) return [];
    return data.slots.filter(s => {
      if (filterMonth !== 'all') {
        const monthMap: Record<string, string> = { april: '/04/', may: '/05/', june: '/06/' };
        if (!s.date?.includes(monthMap[filterMonth])) return false;
      }
      if (filterDate && !s.date?.includes(filterDate)) return false;
      return true;
    });
  }, [data, filterDate, filterMonth]);

  const totalValue = filtered.reduce((sum, s) => sum + parseFloat(s.total_price || '0'), 0);

  const inputCls = "bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-white text-xs focus:outline-none focus:border-red-500/50 placeholder:text-gray-500";

  if (loading) return <div className="flex items-center justify-center py-20 text-gray-400 text-sm">Loading recap slots...</div>;

  return (
    <div className="space-y-4">
      {/* Stats row */}
      <div className="grid grid-cols-3 gap-3">
        {[
          ['Total Held', data?.by_status?.held ?? 0, 'text-green-400'],
          ['Paying', data?.by_status?.paying ?? 0, 'text-yellow-400'],
          ['Paid', data?.by_status?.paid ?? 0, 'text-blue-400'],
        ].map(([label, val, color]) => (
          <div key={label as string} className="bg-gray-900 border border-gray-800 rounded-xl p-3 text-center">
            <p className="text-gray-500 text-xs mb-1">{label}</p>
            <p className={`text-2xl font-bold ${color}`}>{val}</p>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 items-center">
        <div className="flex gap-1">
          {['all', 'april', 'may', 'june'].map(m => (
            <button key={m} onClick={() => setFilterMonth(m)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium capitalize transition-all ${
                filterMonth === m ? 'bg-red-600 text-white' : 'bg-gray-800 border border-gray-700 text-gray-400 hover:text-white'
              }`}>
              {m === 'all' ? 'All' : m}
            </button>
          ))}
        </div>
        <input className={inputCls} placeholder="Filter date (e.g. 15/04)" value={filterDate}
          onChange={e => setFilterDate(e.target.value)} style={{ width: 160 }} />
        {filterDate && (
          <button onClick={() => setFilterDate('')} className="text-xs text-red-400 hover:text-red-300">Clear</button>
        )}
        <button onClick={load} className="ml-auto flex items-center gap-1.5 text-xs text-gray-400 hover:text-white bg-gray-800 border border-gray-700 px-3 py-1.5 rounded-lg">
          <RefreshCw className="w-3 h-3" /> Refresh
        </button>
        <span className="text-xs text-gray-500">{filtered.length} slots · <span className="text-green-400 font-semibold">€{totalValue.toLocaleString()}</span></span>
      </div>

      {/* Table */}
      {filtered.length === 0 ? (
        <div className="bg-gray-900 border border-gray-800 rounded-xl flex flex-col items-center justify-center py-16">
          <Lock className="w-8 h-8 text-gray-600 mb-3" />
          <p className="text-gray-500 text-sm">No recap slots found</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-gray-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 bg-gray-900/80">
                {['#', 'Date', 'Time', 'Ticket', 'Visitors', 'Price', 'Status', 'Age', 'RecapID'].map(h => (
                  <th key={h} className="text-left px-3 py-2.5 text-xs text-gray-500 font-medium whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((s, i) => (
                <tr key={s.id} className={`border-b border-gray-800/50 ${i % 2 === 0 ? 'bg-gray-900' : 'bg-gray-900/50'} hover:bg-gray-800/50 transition-colors`}>
                  <td className="px-3 py-2 text-gray-500 text-xs">#{s.id}</td>
                  <td className="px-3 py-2 text-white font-mono text-xs">{s.date}</td>
                  <td className="px-3 py-2 text-green-400 font-mono text-xs font-semibold">{s.slot_time}</td>
                  <td className="px-3 py-2 text-gray-300 text-xs max-w-[160px] truncate">{s.ticket_name?.replace('Musei Vaticani - ', '')}</td>
                  <td className="px-3 py-2 text-gray-300 text-xs">👥 {s.visitors}</td>
                  <td className="px-3 py-2 text-green-400 text-xs font-semibold">€{s.total_price}</td>
                  <td className="px-3 py-2">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${
                      s.status === 'held' ? 'bg-green-900/50 text-green-400' :
                      s.status === 'paying' ? 'bg-yellow-900/50 text-yellow-400' :
                      'bg-blue-900/50 text-blue-400'
                    }`}>{s.status}</span>
                  </td>
                  <td className="px-3 py-2 text-gray-500 text-xs">{s.age_hours}h</td>
                  <td className="px-3 py-2 text-gray-600 text-xs font-mono truncate max-w-[120px]">{s.recap_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function AdminPanel() {
  const router = useRouter();
  const [view, setView] = useState<'dashboard' | 'agencies' | 'users' | 'tasks' | 'recap'>('dashboard');
  const [agencies, setAgencies] = useState<Agency[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState<{ type: string; data?: any } | null>(null);
  const [form, setForm] = useState<any>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => { checkAuth(); }, []);

  const checkAuth = async () => {
    const token = localStorage.getItem('session_token');
    if (!token) { router.push('/'); return; }
    try {
      const res = await fetch('/api/v1/auth/verify/', { headers: { 'Authorization': `Bearer ${token}` } });
      const data = await res.json();
      if (!data.user?.is_super_admin) { router.push('/'); return; }
      loadAll();
    } catch { router.push('/'); }
  };

  const loadAll = async () => {
    setLoading(true);
    try {
      const [a, u, t, s] = await Promise.all([
        apiFetch('agencies/').then(r => r.json()),
        apiFetch('users/').then(r => r.json()),
        apiFetch('tasks/').then(r => r.json()),
        apiFetch('dashboard/overview/').then(r => r.json()),
      ]);
      setAgencies(Array.isArray(a) ? a : []);
      setUsers(Array.isArray(u) ? u : []);
      setTasks(Array.isArray(t) ? t : []);
      setStats(s);
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  const openModal = (type: string, data?: any) => {
    setError('');
    setForm(data ? { ...data } : {});
    setModal({ type, data });
  };
  const closeModal = () => { setModal(null); setForm({}); setError(''); };

  const save = async () => {
    setSaving(true); setError('');
    try {
      if (modal?.type === 'edit-agency') {
        const res = await apiFetch(`agencies/${modal.data.id}/`, { method: 'PATCH', body: JSON.stringify({ name: form.name, plan: form.plan, telegram_chat_id: form.telegram_chat_id }) });
        if (!res.ok) throw new Error((await res.json()).error || 'Failed');
        // Update local state immediately
        setAgencies(prev => prev.map(a => a.id === modal.data.id ? { ...a, name: form.name, plan: form.plan, telegram_chat_id: form.telegram_chat_id } : a));
      } else if (modal?.type === 'create-agency') {
        const res = await apiFetch('agencies/', { method: 'POST', body: JSON.stringify({ name: form.name, plan: form.plan || 'free', telegram_chat_id: form.telegram_chat_id }) });
        if (!res.ok) throw new Error((await res.json()).error || 'Failed');
      } else if (modal?.type === 'edit-user') {
        const body: any = { username: form.username, email: form.email, full_name: form.full_name, agency_id: form.agency_id };
        if (form.password) body.password = form.password;
        const res = await apiFetch(`users/${modal.data.id}/`, { method: 'PUT', body: JSON.stringify(body) });
        if (!res.ok) throw new Error((await res.json()).error || 'Failed');
        // Update local state immediately
        const agencyName = agencies.find(a => a.id === form.agency_id)?.name || '';
        setUsers(prev => prev.map(u => u.id === modal.data.id ? { ...u, username: form.username, email: form.email, full_name: form.full_name, agency: { ...u.agency, id: form.agency_id, name: agencyName } } : u));
      } else if (modal?.type === 'create-user') {
        const res = await apiFetch('users/', { method: 'POST', body: JSON.stringify({ username: form.username, email: form.email, password: form.password, full_name: form.full_name || '', agency_id: form.agency_id }) });
        if (!res.ok) throw new Error((await res.json()).error || 'Failed');
      } else if (modal?.type === 'edit-task') {
        const res = await apiFetch(`tasks/${modal.data.id}/`, { method: 'PATCH', body: JSON.stringify({ is_active: form.is_active, visitors: form.visitors }) });
        if (!res.ok) throw new Error((await res.json()).error || 'Failed');
        setTasks(prev => prev.map(t => t.id === modal.data.id ? { ...t, is_active: form.is_active, visitors: form.visitors } : t));
      }
      closeModal();
      loadAll(); // also refresh in background for full consistency
    } catch (e: any) { setError(e.message); }
    setSaving(false);
  };

  const deleteItem = async (type: string, id: number) => {
    if (!confirm('Are you sure?')) return;
    try {
      const res = await apiFetch(`${type}/${id}/`, { method: 'DELETE' });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        alert(data.error || `Delete failed (${res.status})`);
        return;
      }
      if (type === 'agencies') setAgencies(prev => prev.filter(a => a.id !== id));
      if (type === 'users') setUsers(prev => prev.filter(u => u.id !== id));
      if (type === 'tasks') setTasks(prev => prev.filter(t => t.id !== id));
    } catch (e: any) {
      alert(e.message || 'Delete failed');
    }
  };

  const toggleAgency = async (id: number) => {
    setAgencies(prev => prev.map(a => a.id === id ? { ...a, is_active: !a.is_active } : a));
    await apiFetch(`agencies/${id}/toggle_active/`, { method: 'POST' });
  };

  const toggleTask = async (id: number) => {
    setTasks(prev => prev.map(t => t.id === id ? { ...t, is_active: !t.is_active } : t));
    const task = tasks.find(t => t.id === id);
    if (!task) return;
    await apiFetch(`tasks/${id}/`, { method: 'PATCH', body: JSON.stringify({ is_active: !task.is_active }) });
  };

  if (loading) return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center">
      <div className="text-center text-white">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-red-500 mx-auto mb-3" />
        Loading...
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      {/* Header */}
      <div className="bg-gray-900 border-b border-gray-800 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Shield className="text-red-500 w-6 h-6" />
          <span className="font-bold text-lg">Super Admin</span>
        </div>
        <button onClick={async () => {
          const token = localStorage.getItem('session_token');
          if (token) await fetch('/api/v1/auth/logout/', { method: 'POST', headers: { 'Authorization': `Bearer ${token}` } }).catch(() => {});
          localStorage.clear();
          window.location.href = '/';
        }} className="flex items-center gap-2 text-sm text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 px-3 py-2 rounded-lg transition-colors">
          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
          Logout
        </button>
      </div>

      {/* Nav */}
      <div className="flex gap-1 px-4 pt-3 overflow-x-auto scrollbar-hide">
        {([['dashboard', BarChart3], ['agencies', Building2], ['users', Users], ['tasks', Activity], ['recap', Lock]] as any[]).map(([key, Icon]) => (
          <button key={key} onClick={() => setView(key)}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium capitalize transition-colors whitespace-nowrap ${view === key ? 'bg-red-600 text-white' : 'text-gray-400 hover:text-white hover:bg-gray-800'}`}>
            <Icon className="w-4 h-4" />{key}
          </button>
        ))}
      </div>

      <div className="p-4 space-y-4">

        {/* Dashboard */}
        {view === 'dashboard' && stats && (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {[
              ['Agencies', stats.system_stats?.total_agencies, stats.system_stats?.active_agencies + ' active', 'text-blue-400'],
              ['Users', stats.system_stats?.total_users, stats.system_stats?.active_users + ' active', 'text-green-400'],
              ['Tasks', stats.system_stats?.total_tasks, stats.system_stats?.active_tasks + ' active', 'text-yellow-400'],
              ['New Agencies (30d)', stats.recent_activity?.new_agencies_30d, '', 'text-purple-400'],
              ['New Users (30d)', stats.recent_activity?.new_users_30d, '', 'text-pink-400'],
              ['New Tasks (30d)', stats.recent_activity?.new_tasks_30d, '', 'text-orange-400'],
            ].map(([label, val, sub, color]) => (
              <div key={label as string} className="bg-gray-900 rounded-xl p-4 border border-gray-800">
                <p className="text-gray-400 text-xs mb-1">{label}</p>
                <p className={`text-3xl font-bold ${color}`}>{val}</p>
                {sub && <p className="text-gray-500 text-xs mt-1">{sub}</p>}
              </div>
            ))}
          </div>
        )}

        {/* Agencies */}
        {view === 'agencies' && (
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <h2 className="font-semibold text-gray-200">Agencies ({agencies.length})</h2>
              <button onClick={() => openModal('create-agency')} className="flex items-center gap-2 bg-red-600 hover:bg-red-700 px-3 py-2 rounded-lg text-sm">
                <Plus className="w-4 h-4" /> New Agency
              </button>
            </div>
            {agencies.map(a => (
              <div key={a.id} className="bg-gray-900 border border-gray-800 rounded-xl p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className="font-medium">{a.name}</span>
                      <span className="text-xs bg-gray-700 px-2 py-0.5 rounded">{a.plan}</span>
                      <span className={`text-xs px-2 py-0.5 rounded ${a.is_active ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'}`}>
                        {a.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </div>
                    <p className="text-gray-400 text-xs">{a.user_count} users · {a.task_count} tasks · Chat: {a.telegram_chat_id || 'not set'}</p>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <button onClick={() => toggleAgency(a.id)} className="p-2 hover:bg-gray-700 rounded-lg">
                      {a.is_active ? <ToggleRight className="w-5 h-5 text-green-400" /> : <ToggleLeft className="w-5 h-5 text-gray-500" />}
                    </button>
                    <button onClick={() => openModal('edit-agency', a)} className="p-2 hover:bg-gray-700 rounded-lg"><Edit className="w-4 h-4 text-blue-400" /></button>
                    <button onClick={() => deleteItem('agencies', a.id)} className="p-2 hover:bg-gray-700 rounded-lg"><Trash2 className="w-4 h-4 text-red-400" /></button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Users */}
        {view === 'users' && (
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <h2 className="font-semibold text-gray-200">Users ({users.length})</h2>
              <button onClick={() => openModal('create-user')} className="flex items-center gap-2 bg-red-600 hover:bg-red-700 px-3 py-2 rounded-lg text-sm">
                <Plus className="w-4 h-4" /> New User
              </button>
            </div>
            {users.map(u => (
              <div key={u.id} className="bg-gray-900 border border-gray-800 rounded-xl p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className="font-medium">{u.username}</span>
                      <span className="text-xs text-gray-400 truncate max-w-[120px]">{u.email}</span>
                      {u.is_admin && <span className="text-xs bg-yellow-900 text-yellow-300 px-2 py-0.5 rounded">Admin</span>}
                      <span className={`text-xs px-2 py-0.5 rounded ${u.is_active ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'}`}>
                        {u.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </div>
                    <p className="text-gray-400 text-xs">Agency: {u.agency.name} · {u.agency.plan}</p>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <button onClick={() => openModal('edit-user', { ...u, agency_id: u.agency.id })} className="p-2 hover:bg-gray-700 rounded-lg"><Edit className="w-4 h-4 text-blue-400" /></button>
                    <button onClick={() => deleteItem('users', u.id)} className="p-2 hover:bg-gray-700 rounded-lg"><Trash2 className="w-4 h-4 text-red-400" /></button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Tasks */}
        {view === 'tasks' && (
          <div className="space-y-3">
            <h2 className="font-semibold text-gray-200">All Tasks ({tasks.length})</h2>
            {tasks.map(t => (
              <div key={t.id} className="bg-gray-900 border border-gray-800 rounded-xl p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className="font-medium text-sm">{t.ticket_name || 'Unnamed'}</span>
                      <span className="text-xs bg-gray-700 px-2 py-0.5 rounded">{t.agency.name}</span>
                      <span className={`text-xs px-2 py-0.5 rounded ${t.is_active ? 'bg-green-900 text-green-300' : 'bg-gray-700 text-gray-400'}`}>
                        {t.is_active ? 'Active' : 'Paused'}
                      </span>
                    </div>
                    <p className="text-gray-400 text-xs">{t.language || 'Standard'} · {t.visitors} visitors</p>
                    <p className="text-gray-500 text-xs truncate">{t.dates?.join(', ')}</p>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <button onClick={() => toggleTask(t.id)} className="p-2 hover:bg-gray-700 rounded-lg">
                      {t.is_active ? <ToggleRight className="w-5 h-5 text-green-400" /> : <ToggleLeft className="w-5 h-5 text-gray-500" />}
                    </button>
                    <button onClick={() => openModal('edit-task', t)} className="p-2 hover:bg-gray-700 rounded-lg"><Edit className="w-4 h-4 text-blue-400" /></button>
                    <button onClick={() => deleteItem('tasks', t.id)} className="p-2 hover:bg-gray-700 rounded-lg"><Trash2 className="w-4 h-4 text-red-400" /></button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
        {/* Recap */}
        {view === 'recap' && <RecapView />}

      </div>
      {modal && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-md p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold capitalize">{modal.type.replace('-', ' ')}</h3>
              <button onClick={closeModal}><X className="w-5 h-5 text-gray-400" /></button>
            </div>

            {error && <p className="text-red-400 text-sm bg-red-900/30 px-3 py-2 rounded-lg">{error}</p>}

            {/* Agency fields */}
            {(modal.type === 'edit-agency' || modal.type === 'create-agency') && (
              <div className="space-y-3">
                <input className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm" placeholder="Agency name"
                  value={form.name || ''} onChange={e => setForm({ ...form, name: e.target.value })} />
                <select className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm"
                  value={form.plan || 'free'} onChange={e => setForm({ ...form, plan: e.target.value })}>
                  <option value="free">Free</option>
                  <option value="standard">Standard</option>
                  <option value="premium">Premium</option>
                  <option value="system">System</option>
                </select>
                <input className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm" placeholder="Telegram Chat ID (e.g. -1001234567890)"
                  value={form.telegram_chat_id || ''} onChange={e => setForm({ ...form, telegram_chat_id: e.target.value })} />
                <p className="text-gray-500 text-xs">To get the chat ID: add the bot to the group, then check bot logs or use @userinfobot</p>
              </div>
            )}

            {/* User fields */}
            {(modal.type === 'edit-user' || modal.type === 'create-user') && (
              <div className="space-y-3">
                <input className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm" placeholder="Username"
                  value={form.username || ''} onChange={e => setForm({ ...form, username: e.target.value })} />
                <input className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm" placeholder="Email"
                  value={form.email || ''} onChange={e => setForm({ ...form, email: e.target.value })} />
                <input className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm" placeholder={modal.type === 'edit-user' ? 'New password (leave blank to keep)' : 'Password'}
                  type="password" value={form.password || ''} onChange={e => setForm({ ...form, password: e.target.value })} />
                <select className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm"
                  value={form.agency_id || ''} onChange={e => setForm({ ...form, agency_id: parseInt(e.target.value) })}>
                  <option value="">Select agency...</option>
                  {agencies.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>
              </div>
            )}

            {/* Task fields */}
            {modal.type === 'edit-task' && (
              <div className="space-y-3">
                <p className="text-gray-400 text-sm">Task: <span className="text-white">{form.ticket_name}</span></p>
                <p className="text-gray-400 text-sm">Agency: <span className="text-white">{form.agency?.name}</span></p>
                <label className="flex items-center gap-2 text-sm cursor-pointer">
                  <input type="checkbox" checked={form.is_active || false} onChange={e => setForm({ ...form, is_active: e.target.checked })} />
                  Active
                </label>
                <input className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm" placeholder="Visitors" type="number"
                  value={form.visitors || 1} onChange={e => setForm({ ...form, visitors: parseInt(e.target.value) })} />
              </div>
            )}

            <div className="flex gap-3 pt-2">
              <button onClick={closeModal} className="flex-1 bg-gray-800 hover:bg-gray-700 py-2 rounded-lg text-sm">Cancel</button>
              <button onClick={save} disabled={saving} className="flex-1 bg-red-600 hover:bg-red-700 py-2 rounded-lg text-sm flex items-center justify-center gap-2">
                {saving ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <Check className="w-4 h-4" />}
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
