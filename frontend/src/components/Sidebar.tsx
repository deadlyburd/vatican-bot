'use client';

import React from 'react';
import { LayoutDashboard, Terminal, Zap } from 'lucide-react';

type TabType = 'matrix' | 'logs' | 'settings' | 'holds';

interface SidebarProps {
    activeTab: TabType;
    setActiveTab?: (tab: TabType) => void;
    className?: string;
}

export default function Sidebar({ activeTab, setActiveTab, className = '' }: SidebarProps) {
    return (
        <>
            {/* Desktop sidebar */}
            <aside className={`hidden md:flex w-64 min-w-[16rem] bg-[#0F0F0F] border-r border-[#262626] flex-col p-5 ${className}`}>
                <div className="flex items-center gap-3 mb-10 px-2">
                    <div className="w-9 h-9 rounded-xl bg-[#00E37C] flex items-center justify-center">
                        <Zap size={18} className="text-[#050505]" />
                    </div>
                    <div>
                        <h1 className="text-base font-semibold text-white tracking-tight leading-none">HYDRA</h1>
                        <p className="text-[10px] font-medium text-[#888888] uppercase tracking-widest mt-0.5">Enterprise</p>
                    </div>
                </div>
                <nav className="flex-1 space-y-1">
                    <SidebarItem active={activeTab === 'matrix'} onClick={() => setActiveTab?.('matrix')} icon={<LayoutDashboard className="w-4 h-4" />} label="Overview" />
                    <SidebarItem active={activeTab === 'logs'} onClick={() => setActiveTab?.('logs')} icon={<Terminal className="w-4 h-4" />} label="Logs" />
                </nav>
            </aside>

            {/* Mobile bottom nav */}
            <nav className="md:hidden fixed bottom-0 left-0 right-0 z-50 bg-[#0F0F0F] border-t border-[#262626] flex">
                <MobileNavItem active={activeTab === 'matrix'} onClick={() => setActiveTab?.('matrix')} icon={<LayoutDashboard className="w-5 h-5" />} label="Overview" />
                <MobileNavItem active={activeTab === 'logs'} onClick={() => setActiveTab?.('logs')} icon={<Terminal className="w-5 h-5" />} label="Logs" />
            </nav>
        </>
    );
}

function SidebarItem({ icon, label, active = false, onClick }: { icon: React.ReactNode; label: string; active?: boolean; onClick?: () => void }) {
    return (
        <button onClick={onClick}
            className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm font-medium transition-all ${active ? 'bg-[#262626] text-white' : 'text-[#888888] hover:text-white hover:bg-[#1a1a1a]'}`}>
            <span className={active ? 'text-[#00E37C]' : 'text-[#888888]'}>{icon}</span>
            {label}
        </button>
    );
}

function MobileNavItem({ icon, label, active = false, onClick }: { icon: React.ReactNode; label: string; active?: boolean; onClick?: () => void }) {
    return (
        <button onClick={onClick}
            className={`flex-1 flex flex-col items-center justify-center gap-1 py-3 text-[11px] font-medium transition-colors ${active ? 'text-[#00E37C]' : 'text-[#666]'}`}>
            {icon}
            {label}
        </button>
    );
}