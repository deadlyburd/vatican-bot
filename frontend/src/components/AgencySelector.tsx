'use client';

import { useState, useEffect } from 'react';
import { api, Agency } from '@/lib/api';
import { motion } from 'framer-motion';
import { 
  Building2, 
  Plus, 
  Users, 
  Activity,
  ArrowRight,
  Crown,
  Zap
} from 'lucide-react';

interface AgencySelectorProps {
  onAgencySelect: (agency: Agency) => void;
}

export default function AgencySelector({ onAgencySelect }: AgencySelectorProps) {
  const [agencies, setAgencies] = useState<Agency[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newAgencyName, setNewAgencyName] = useState('');
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    loadAgencies();
  }, []);

  const loadAgencies = async () => {
    try {
      const agenciesData = await api.getAgencies();
      setAgencies(agenciesData);
    } catch (error) {
      console.error('Failed to load agencies:', error);
    } finally {
      setLoading(false);
    }
  };

  const createAgency = async () => {
    if (!newAgencyName.trim()) return;
    
    setCreating(true);
    try {
      // Create new agency via API
      const newAgency = await api.createAgency({
        name: newAgencyName.trim(),
        plan: 'free',
        owner_id: `user_${Date.now()}`,
        is_active: true
      });
      
      setAgencies([...agencies, newAgency]);
      setNewAgencyName('');
      setShowCreateForm(false);
    } catch (error) {
      console.error('Failed to create agency:', error);
      alert('Failed to create agency');
    } finally {
      setCreating(false);
    }
  };

  const getPlanIcon = (plan: string) => {
    switch (plan) {
      case 'free': return <Activity className="w-4 h-4 text-gray-400" />;
      case 'pro': return <Zap className="w-4 h-4 text-blue-400" />;
      case 'agency': return <Crown className="w-4 h-4 text-yellow-400" />;
      default: return <Activity className="w-4 h-4 text-gray-400" />;
    }
  };

  const getPlanColor = (plan: string) => {
    switch (plan) {
      case 'free': return 'border-gray-600 hover:border-gray-500';
      case 'pro': return 'border-blue-600 hover:border-blue-500';
      case 'agency': return 'border-yellow-600 hover:border-yellow-500';
      default: return 'border-gray-600 hover:border-gray-500';
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#050505]">
        <div className="flex flex-col items-center gap-6">
          <div className="w-12 h-12 rounded-2xl bg-[#0F0F0F] border border-[#262626] flex items-center justify-center">
            <Building2 className="w-6 h-6 text-[#00E37C] animate-pulse" />
          </div>
          <div className="text-xs font-medium uppercase tracking-[0.2em] text-[#888888]">Loading Agencies</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#050505] flex items-center justify-center p-8">
      <div className="max-w-4xl w-full">
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center mb-12"
        >
          <div className="w-16 h-16 rounded-2xl bg-[#0F0F0F] border border-[#262626] flex items-center justify-center mx-auto mb-6">
            <Building2 className="w-8 h-8 text-[#00E37C]" />
          </div>
          <h1 className="text-3xl font-semibold text-white mb-4">Select Agency</h1>
          <p className="text-[#888888] max-w-md mx-auto">
            Choose which agency dashboard you want to access. Each agency has its own monitoring tasks and configurations.
          </p>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
          {agencies.map((agency, index) => (
            <motion.div
              key={agency.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.1 }}
              onClick={() => onAgencySelect(agency)}
              className={`bg-[#0F0F0F] border-2 ${getPlanColor(agency.plan)} rounded-2xl p-6 cursor-pointer transition-all duration-200 hover:bg-[#1A1A1A] group`}
            >
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-[#262626] rounded-xl flex items-center justify-center">
                    {getPlanIcon(agency.plan)}
                  </div>
                  <div>
                    <h3 className="font-semibold text-white group-hover:text-[#00E37C] transition-colors">
                      {agency.name}
                    </h3>
                    <div className="flex items-center gap-2 text-sm text-[#888888]">
                      <span className="capitalize">{agency.plan}</span>
                      {agency.is_active && (
                        <div className="w-2 h-2 bg-[#00E37C] rounded-full"></div>
                      )}
                    </div>
                  </div>
                </div>
                <ArrowRight className="w-5 h-5 text-[#888888] group-hover:text-[#00E37C] transition-colors" />
              </div>
              
              <div className="space-y-2 text-sm text-[#888888]">
                <div className="flex items-center gap-2">
                  <Users className="w-4 h-4" />
                  <span>ID: {agency.id}</span>
                </div>
                {agency.telegram_chat_id && (
                  <div className="flex items-center gap-2">
                    <Activity className="w-4 h-4" />
                    <span>Telegram: {agency.telegram_chat_id}</span>
                  </div>
                )}
              </div>
            </motion.div>
          ))}

          {/* Create New Agency Card */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: agencies.length * 0.1 }}
            onClick={() => setShowCreateForm(true)}
            className="bg-[#0F0F0F] border-2 border-dashed border-[#262626] rounded-2xl p-6 cursor-pointer transition-all duration-200 hover:border-[#00E37C] hover:bg-[#1A1A1A] group flex flex-col items-center justify-center text-center min-h-[200px]"
          >
            <div className="w-12 h-12 bg-[#262626] rounded-xl flex items-center justify-center mb-4 group-hover:bg-[#00E37C]/10 transition-colors">
              <Plus className="w-6 h-6 text-[#888888] group-hover:text-[#00E37C] transition-colors" />
            </div>
            <h3 className="font-semibold text-white mb-2">Create New Agency</h3>
            <p className="text-sm text-[#888888]">Set up a new agency with its own monitoring tasks</p>
          </motion.div>
        </div>

        {/* Create Agency Form */}
        {showCreateForm && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-[#0F0F0F] border border-[#262626] rounded-2xl p-6 max-w-md mx-auto"
          >
            <h3 className="text-lg font-semibold text-white mb-4">Create New Agency</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-[#888888] mb-2">
                  Agency Name
                </label>
                <input
                  type="text"
                  value={newAgencyName}
                  onChange={(e) => setNewAgencyName(e.target.value)}
                  placeholder="Enter agency name..."
                  className="w-full px-4 py-3 bg-[#1A1A1A] border border-[#262626] rounded-xl text-white placeholder-[#666666] focus:outline-none focus:border-[#00E37C] transition-colors"
                  onKeyPress={(e) => e.key === 'Enter' && createAgency()}
                />
              </div>
              <div className="flex gap-3">
                <button
                  onClick={createAgency}
                  disabled={creating || !newAgencyName.trim()}
                  className="flex-1 bg-[#00E37C] text-black font-medium py-3 px-4 rounded-xl hover:bg-[#00E37C]/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {creating ? 'Creating...' : 'Create Agency'}
                </button>
                <button
                  onClick={() => {
                    setShowCreateForm(false);
                    setNewAgencyName('');
                  }}
                  className="px-4 py-3 text-[#888888] hover:text-white transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
}