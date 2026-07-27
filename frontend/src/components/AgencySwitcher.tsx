'use client';

import { useState } from 'react';
import { Agency } from '@/lib/api';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Building2, 
  ChevronDown, 
  Check,
  Crown,
  Zap,
  Activity
} from 'lucide-react';

interface AgencySwitcherProps {
  currentAgency: Agency;
  agencies: Agency[];
  onAgencyChange: (agency: Agency) => void;
}

export default function AgencySwitcher({ currentAgency, agencies, onAgencyChange }: AgencySwitcherProps) {
  const [isOpen, setIsOpen] = useState(false);

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
      case 'free': return 'text-gray-400';
      case 'pro': return 'text-blue-400';
      case 'agency': return 'text-yellow-400';
      default: return 'text-gray-400';
    }
  };

  return (
    <div className="relative">
      <motion.button
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-3 px-4 py-2 bg-[#0F0F0F] border border-[#262626] rounded-xl hover:border-[#00E37C] transition-colors"
      >
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-[#262626] rounded-lg flex items-center justify-center">
            {getPlanIcon(currentAgency.plan)}
          </div>
          <div className="text-left">
            <div className="text-sm font-medium text-white">{currentAgency.name}</div>
            <div className={`text-xs capitalize ${getPlanColor(currentAgency.plan)}`}>
              {currentAgency.plan}
            </div>
          </div>
        </div>
        <ChevronDown className={`w-4 h-4 text-[#888888] transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </motion.button>

      <AnimatePresence>
        {isOpen && (
          <>
            {/* Backdrop */}
            <div 
              className="fixed inset-0 z-40" 
              onClick={() => setIsOpen(false)}
            />
            
            {/* Dropdown */}
            <motion.div
              initial={{ opacity: 0, y: -10, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -10, scale: 0.95 }}
              transition={{ duration: 0.15 }}
              className="absolute top-full left-0 mt-2 w-80 bg-[#0F0F0F] border border-[#262626] rounded-xl shadow-2xl z-50 overflow-hidden"
            >
              <div className="p-2">
                <div className="text-xs font-medium text-[#888888] px-3 py-2 uppercase tracking-wider">
                  Switch Agency
                </div>
                
                <div className="space-y-1">
                  {agencies.map((agency) => (
                    <motion.button
                      key={agency.id}
                      whileHover={{ backgroundColor: '#1A1A1A' }}
                      onClick={() => {
                        onAgencyChange(agency);
                        setIsOpen(false);
                      }}
                      className="w-full flex items-center gap-3 px-3 py-3 rounded-lg text-left transition-colors"
                    >
                      <div className="w-8 h-8 bg-[#262626] rounded-lg flex items-center justify-center">
                        {getPlanIcon(agency.plan)}
                      </div>
                      
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-white">{agency.name}</span>
                          {agency.id === currentAgency.id && (
                            <Check className="w-4 h-4 text-[#00E37C]" />
                          )}
                        </div>
                        <div className="flex items-center gap-2 text-xs text-[#888888]">
                          <span className={`capitalize ${getPlanColor(agency.plan)}`}>
                            {agency.plan}
                          </span>
                          <span>•</span>
                          <span>ID: {agency.id}</span>
                          {agency.is_active && (
                            <>
                              <span>•</span>
                              <div className="w-2 h-2 bg-[#00E37C] rounded-full"></div>
                            </>
                          )}
                        </div>
                      </div>
                    </motion.button>
                  ))}
                </div>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}