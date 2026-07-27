'use client';

export const dynamic = 'force-dynamic';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api, Agency, MonitorTask } from '@/lib/api';
import TaskModal from '@/components/TaskModal';
import TaskCard from '@/components/TaskCard';
import LogsView from '@/components/LogsView';
import Sidebar from '@/components/Sidebar';
import LoginPage from '@/components/LoginPage';
import { motion, AnimatePresence } from 'framer-motion';
import HoldsView from '@/components/HoldsView';
import {
  Plus,
  Globe,
  Activity,
  Zap,
  BarChart3,
  Building2,
  Lock,
  LogOut,
  Shield
} from 'lucide-react';

export default function DashboardPage() {
  const router = useRouter();
  const [tasks, setTasks] = useState<MonitorTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<'matrix' | 'logs' | 'holds' | 'settings'>('matrix');
  const [heldSlots, setHeldSlots] = useState<any[]>([]);
  
  // Authentication state
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [sessionToken, setSessionToken] = useState<string | null>(null);
  const [currentAgency, setCurrentAgency] = useState<Agency | null>(null);
  const [currentUser, setCurrentUser] = useState<any>(null);

  useEffect(() => {
    checkAuth();
  }, []);

  useEffect(() => {
    if (isAuthenticated && currentAgency) {
      loadTasks();
      loadHeldSlots();
    }
  }, [isAuthenticated, currentAgency]);

  const checkAuth = async () => {
    try {
      const token = localStorage.getItem('session_token');
      if (!token) { setIsAuthenticated(false); setLoading(false); return; }

      const response = await api.verifySession(token);
      
      // Super admin goes straight to /admin - don't render dashboard at all
      if (response.user?.is_super_admin) {
        router.replace('/admin');
        return; // Don't setLoading(false) - keep spinner until redirect completes
      }

      setSessionToken(token);
      setCurrentAgency(response.agency);
      setCurrentUser(response.user);
      setIsAuthenticated(true);
      setLoading(false);
    } catch (error) {
      localStorage.removeItem('session_token');
      localStorage.removeItem('agency');
      localStorage.removeItem('user');
      setIsAuthenticated(false);
      setLoading(false);
    }
  };

  const handleLoginSuccess = (token: string, agency: Agency, user?: any) => {
    if (user?.is_super_admin) {
      router.replace('/admin');
      return;
    }
    setSessionToken(token);
    setCurrentAgency(agency);
    setCurrentUser(user || null);
    setIsAuthenticated(true);
  };

  const handleLogout = async () => {
    try {
      if (sessionToken) {
        await api.logout(sessionToken);
      }
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      localStorage.removeItem('session_token');
      localStorage.removeItem('agency');
      localStorage.removeItem('user');
      setSessionToken(null);
      setCurrentAgency(null);
      setCurrentUser(null);
      setIsAuthenticated(false);
    }
  };

  const loadTasks = async () => {
    if (!currentAgency) return;
    try {
      const tasksData = await api.getTasks(currentAgency.id);
      setTasks(tasksData);
    } catch (error) {
      console.error('❌ Failed to load tasks:', error);
    }
  };

  const loadHeldSlots = async () => {
    try {
      const token = localStorage.getItem('session_token');
      const res = await fetch('/api/v1/holds/', {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
      });
      if (res.ok) {
        const data = await res.json();
        setHeldSlots(Array.isArray(data) ? data : data.results || []);
      }
    } catch (err) {
      console.error('Failed to load held slots:', err);
    }
  };

  const refreshTasks = async () => {
    if (!currentAgency) return;
    try {
      const tasksData = await api.getTasks(currentAgency.id);
      setTasks(tasksData);
    } catch (err) {
      console.error(err);
    }
  };

  const handleDeleteTask = async (taskId: number) => {
    try {
      setTasks(tasks.filter(t => t.id !== taskId));
      await api.deleteTask(taskId);
    } catch (err) {
      console.error(err);
      alert('Failed to delete task');
      refreshTasks();
    }
  };

  // Show login page if not authenticated
  if (!isAuthenticated) {
    return <LoginPage onLoginSuccess={handleLoginSuccess} />;
  }

  // Still loading or redirecting (e.g. super admin redirect in progress)
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#050505]">
        <div className="flex flex-col items-center gap-6">
          <div className="w-12 h-12 rounded-2xl bg-[#0F0F0F] border border-[#262626] flex items-center justify-center">
            <Activity className="w-6 h-6 text-[#00E37C] animate-pulse" />
          </div>
          <div className="text-xs font-medium uppercase tracking-[0.2em] text-[#888888]">Loading Dashboard</div>
        </div>
      </div>
    );
  }

  if (!currentAgency) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#050505]">
        <div className="text-center">
          <p className="text-white mb-4">No agency found</p>
          <button onClick={handleLogout} className="btn-primary">
            Logout
          </button>
        </div>
      </div>
    );
  }

  const activeTasks = tasks.filter(t => t.is_active).length;
  const totalTasks = tasks.length;
  // No monitor count limits — plan gates tier features (hold/snipe), not quantity

  return (
    <div className="relative flex h-screen overflow-hidden bg-[#050505]">
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} className="flex-shrink-0 z-20" />

      <main className="flex-1 overflow-y-auto relative">
        <div className="p-4 md:p-8 lg:p-12 max-w-[1600px] mx-auto min-h-full pb-24 md:pb-12">

          {/* Mobile header */}
          <div className="md:hidden flex items-center justify-between mb-5">
            <div>
              <div className="flex items-center gap-2 mb-0.5">
                <div className="w-6 h-6 rounded-lg bg-[#00E37C] flex items-center justify-center">
                  <Zap size={13} className="text-[#050505]" />
                </div>
                <span className="text-xs font-semibold text-[#888] uppercase tracking-widest">HYDRA</span>
              </div>
              <h1 className="text-lg font-semibold text-white truncate max-w-[180px]">{currentAgency.name}</h1>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="text-xs text-[#888]">{tasks.length} monitors</span>
                <span className="text-[10px] px-1.5 py-0.5 bg-[#00E37C]/10 text-[#00E37C] rounded-full uppercase font-semibold">{currentAgency.plan}</span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {currentUser?.is_super_admin && (
                <button onClick={() => router.push('/admin')} className="p-2 rounded-xl bg-red-600/20 border border-red-500/30 text-red-400">
                  <Shield className="w-4 h-4" />
                </button>
              )}
              <button onClick={handleLogout} className="p-2 rounded-xl bg-[#1a1a1a] border border-[#262626] text-[#888]">
                <LogOut className="w-4 h-4" />
              </button>
              <button
                onClick={() => setIsModalOpen(true)}
                className="flex items-center gap-1.5 px-3 py-2 bg-[#00E37C] text-[#050505] text-sm font-semibold rounded-xl"
              >
                <Plus className="w-4 h-4" />
                New
              </button>
            </div>
          </div>

          {/* Desktop header */}
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="hidden md:flex justify-between items-start mb-8"
          >
            <div>
              <h1 className="text-2xl font-semibold text-white tracking-tight mb-1">{currentAgency.name}</h1>
              <p className="text-[#888888] text-sm">Live ticket monitoring dashboard</p>
            </div>
            <div className="flex items-center gap-3">
              <div className="px-3 py-1.5 bg-[#0F0F0F] border border-[#262626] rounded-full flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-[#00E37C]" />
                <span className="text-sm font-medium text-[#888888]">{tasks.length} Monitors</span>
                <span className="text-xs px-1.5 py-0.5 bg-[#00E37C]/10 text-[#00E37C] rounded-full uppercase font-semibold">{currentAgency.plan}</span>
              </div>
              {currentUser?.is_super_admin && (
                <button onClick={() => router.push('/admin')} className="h-9 px-4 rounded-lg bg-red-600 text-white text-sm font-medium hover:bg-red-700 transition-colors flex items-center gap-2">
                  <Shield className="w-4 h-4" /> Admin
                </button>
              )}
              <button onClick={handleLogout} className="h-9 px-4 rounded-lg bg-[#1a1a1a] border border-[#262626] text-[#888888] text-sm font-medium hover:text-white transition-colors flex items-center gap-2">
                <LogOut className="w-4 h-4" /> Logout
              </button>
              <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
                onClick={() => setIsModalOpen(true)}
                className="btn-primary">
                <Plus className="w-4 h-4" /><span>New Monitor</span>
              </motion.button>
            </div>
          </motion.div>

          {/* Stats */}
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
            className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
            {[
              { icon: <Activity className="w-4 h-4 text-[#00E37C]" />, bg: 'bg-[#00E37C]/10', val: activeTasks, label: 'Active' },
              { icon: <BarChart3 className="w-4 h-4 text-blue-400" />, bg: 'bg-blue-500/10', val: totalTasks, label: 'Total' },
              { icon: <Building2 className="w-4 h-4 text-purple-400" />, bg: 'bg-purple-500/10', val: currentAgency.plan, label: 'Plan', capitalize: true },
              { icon: <Zap className="w-4 h-4 text-emerald-400" />, bg: 'bg-emerald-500/10', val: tasks.filter(t => t.last_status === 'available').length > 0 ? `${Math.round((tasks.filter(t => t.last_status === 'available').length / Math.max(tasks.length, 1)) * 100)}%` : '0%', label: 'Available' },
            ].map(({ icon, bg, val, label, capitalize }) => (
              <div key={label} className="bg-[#0F0F0F] border border-[#262626] rounded-2xl p-4">
                <div className="flex items-center gap-2.5">
                  <div className={`w-8 h-8 ${bg} rounded-lg flex items-center justify-center shrink-0`}>{icon}</div>
                  <div className="min-w-0">
                    <div className={`text-xl font-semibold text-white truncate ${capitalize ? 'capitalize' : ''}`}>{val}</div>
                    <div className="text-xs text-[#888888]">{label}</div>
                  </div>
                </div>
              </div>
            ))}
          </motion.div>

          {/* Tab switcher */}
          <div className="flex gap-2 mb-6">
            {[
              { id: 'matrix', label: '📋 Monitors' },
              { id: 'holds', label: `🔒 Held Slots (${heldSlots.length})` },
              { id: 'logs', label: '📊 Logs' },
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => { setActiveTab(tab.id as any); if (tab.id === 'holds') loadHeldSlots(); }}
                className={`px-4 py-2 rounded-xl text-sm font-medium transition-all ${
                  activeTab === tab.id
                    ? 'bg-[#00E37C] text-[#050505]'
                    : 'bg-[#1a1a1a] border border-[#262626] text-[#888] hover:text-white'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Content */}
          <AnimatePresence mode="wait">
            <motion.div key={activeTab} initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -10 }} transition={{ duration: 0.3 }}>
              {activeTab === 'matrix' && (
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                  {Array.isArray(tasks) && tasks.map((task, i) => (
                    <motion.div key={`task-${task.id}-${i}`} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
                      <TaskCard task={task} onDelete={handleDeleteTask} />
                    </motion.div>
                  ))}
                  {(!Array.isArray(tasks) || tasks.length === 0) && (
                    <div className="col-span-full bg-[#0F0F0F] border border-[#262626] rounded-2xl flex flex-col items-center justify-center text-center py-16">
                      <div className="w-14 h-14 bg-[#262626] rounded-full flex items-center justify-center mb-4">
                        <Globe className="w-6 h-6 text-[#888888]" />
                      </div>
                      <h3 className="text-lg font-semibold text-white mb-2">No Active Monitors</h3>
                      <p className="text-[#888888] text-sm max-w-xs mb-5">Create a monitor to start tracking Vatican ticket availability.</p>
                      <button onClick={() => setIsModalOpen(true)} className="btn-primary">
                        <Plus className="w-4 h-4" /> Create Monitor
                      </button>
                    </div>
                  )}
                </div>
              )}
              {activeTab === 'logs' && (
                <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
                  <LogsView agencyId={currentAgency.id} />
                </motion.div>
              )}
              {activeTab === 'holds' && (
                <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
                  {/* Summary bar */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
                    {[
                      { label: 'Total Slots', val: heldSlots.length },
                      { label: 'April Slots', val: heldSlots.filter((h:any) => h.date?.includes('/04/')).length },
                      { label: 'May Slots', val: heldSlots.filter((h:any) => h.date?.includes('/05/')).length },
                      { label: 'Total Value', val: `€${heldSlots.reduce((s:number,h:any) => s + parseFloat(h.total_price||0), 0).toLocaleString()}` },
                    ].map(({label, val}) => (
                      <div key={label} className="bg-[#0F0F0F] border border-[#262626] rounded-2xl p-4 text-center">
                        <div className="text-xl font-bold text-white">{val}</div>
                        <div className="text-xs text-[#666] mt-1">{label}</div>
                      </div>
                    ))}
                  </div>
                  <div className="mb-4 p-3 bg-purple-500/10 border border-purple-500/20 rounded-xl">
                    <p className="text-xs text-purple-300">🔒 Exclusive — slots held by HydraBot. Anyone wanting tickets must contact you directly.</p>
                  </div>
                  <HoldsView slots={heldSlots} />
                </motion.div>
              )}
            </motion.div>
          </AnimatePresence>
        </div>
      </main>

      <TaskModal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} onSuccess={refreshTasks} agencyId={currentAgency.id} agencyPlan={currentAgency.plan} />
    </div>
  );
}
