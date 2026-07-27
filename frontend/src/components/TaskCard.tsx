'use client';

import { useState, useEffect } from 'react';
import { MonitorTask } from '@/lib/api';
import { Clock, Calendar, Trash2, Check, ChevronDown, ChevronUp } from 'lucide-react';

interface TaskCardProps {
    task: MonitorTask;
    onDelete?: (id: number) => Promise<void>;
}

const STATUS_STYLES: Record<string, { bar: string; badge: string; label: string }> = {
    available: { bar: 'bg-[#00E37C]', badge: 'bg-[#00E37C]/10 text-[#00E37C] border-[#00E37C]/30', label: 'Available' },
    sold_out:  { bar: 'bg-red-500',   badge: 'bg-red-500/10 text-red-400 border-red-500/30',       label: 'Sold Out' },
    error:     { bar: 'bg-orange-500',badge: 'bg-orange-500/10 text-orange-400 border-orange-500/30', label: 'Error' },
    closed:    { bar: 'bg-[#555]',    badge: 'bg-[#555]/10 text-[#888] border-[#555]/30',           label: 'Closed' },
};
const defaultStyle = { bar: 'bg-blue-500', badge: 'bg-blue-500/10 text-blue-400 border-blue-500/30', label: 'Checking' };

export default function TaskCard({ task, onDelete }: TaskCardProps) {
    const [timeLeft, setTimeLeft] = useState('...');
    const [expanded, setExpanded] = useState(false);

    const status = task.last_status?.toLowerCase() || 'checking';
    const style = STATUS_STYLES[status] || defaultStyle;
    const isAvailable = status === 'available';

    const TIER_BADGE: Record<string, string> = {
        hold:  '🔒 Hold',
        snipe: '🤖 Snipe',
    };

    useEffect(() => {
        const tick = () => {
            if (!task.last_checked) { setTimeLeft('Pending'); return; }
            const next = new Date(task.last_checked).getTime() + (task.check_interval || 60) * 1000;
            const diff = next - Date.now();
            if (diff <= 0) { setTimeLeft('Now'); return; }
            const m = Math.floor(diff / 60000);
            const s = Math.floor((diff % 60000) / 1000);
            setTimeLeft(`${m}:${s.toString().padStart(2, '0')}`);
        };
        tick();
        const id = setInterval(tick, 1000);
        return () => clearInterval(id);
    }, [task.last_checked, task.check_interval]);

    const getSlots = (): string[] => {
        const d: any = task.latest_check?.details;
        if (!d) return [];
        if (Array.isArray(d.slots)) return d.slots.map((s: any) => typeof s === 'string' ? s : s?.time).filter(Boolean);
        if (typeof d === 'object') {
            const times: string[] = [];
            Object.values(d).forEach((items: any) => {
                if (Array.isArray(items)) items.forEach((it: any) => (it?.slots || []).forEach((s: any) => times.push(typeof s === 'string' ? s : s?.time)));
            });
            return times.filter(Boolean);
        }
        return [];
    };

    const slots = getSlots();
    const langFlag: Record<string, string> = { ENG: '🇬🇧', ITA: '🇮🇹', FRA: '🇫🇷', DEU: '🇩🇪', SPA: '🇪🇸' };

    return (
        <div className="bg-[#0F0F0F] border border-[#262626] rounded-2xl overflow-hidden">
            {/* Status bar */}
            <div className={`h-1 w-full ${style.bar}`} />

            <div className="p-4">
                {/* Header row */}
                <div className="flex items-start justify-between gap-2 mb-3">
                    <div className="min-w-0">
                        <h3 className="text-base font-semibold text-white truncate">{task.area_name}</h3>
                        <p className="text-xs text-[#666] mt-0.5">Vatican Museums · {task.visitors} visitor{task.visitors !== 1 ? 's' : ''}</p>
                    </div>
                    <span className={`shrink-0 px-2.5 py-1 rounded-full text-[11px] font-semibold border ${style.badge}`}>
                        {style.label}
                    </span>
                </div>

                {/* Ticket + language */}
                {task.ticket_name && (
                    <div className="flex items-center gap-2 mb-3 flex-wrap">
                        <span className="text-xs text-[#888] bg-[#1a1a1a] border border-[#262626] px-2.5 py-1 rounded-lg truncate max-w-full">
                            {task.ticket_name}
                        </span>
                        {task.language && (
                            <span className="text-xs text-[#00E37C] bg-[#00E37C]/10 border border-[#00E37C]/20 px-2 py-1 rounded-lg">
                                {langFlag[task.language] || ''} {task.language}
                            </span>
                        )}
                        {task.tier && TIER_BADGE[task.tier] && (
                            <span className="text-xs text-purple-400 bg-purple-500/10 border border-purple-500/20 px-2 py-1 rounded-lg">
                                {TIER_BADGE[task.tier]}
                            </span>
                        )}
                    </div>
                )}

                {/* Dates */}
                <div className="flex items-center gap-1.5 mb-3 flex-wrap">
                    <Calendar className="w-3.5 h-3.5 text-[#555] shrink-0" />
                    {task.dates.slice(0, 3).map((d, i) => (
                        <span key={i} className="text-xs font-mono text-[#888] bg-[#1a1a1a] border border-[#262626] px-2 py-0.5 rounded-md">{d}</span>
                    ))}
                    {task.dates.length > 3 && <span className="text-xs text-[#555]">+{task.dates.length - 3}</span>}
                </div>

                {/* Available slots */}
                {isAvailable && slots.length > 0 && (
                    <div className="mb-3 p-3 bg-[#00E37C]/5 border border-[#00E37C]/20 rounded-xl">
                        <div className="flex items-center gap-1.5 mb-2">
                            <Check className="w-3.5 h-3.5 text-[#00E37C]" />
                            <span className="text-xs font-semibold text-[#00E37C]">{slots.length} slot{slots.length !== 1 ? 's' : ''} available</span>
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                            {slots.slice(0, 8).map((s, i) => (
                                <span key={i} className="text-xs font-mono text-[#00E37C] bg-[#00E37C]/10 border border-[#00E37C]/20 px-2 py-0.5 rounded-md">{s}</span>
                            ))}
                            {slots.length > 8 && <span className="text-xs text-[#00E37C]/60">+{slots.length - 8}</span>}
                        </div>
                    </div>
                )}

                {/* Expandable preferred times */}
                {task.preferred_times?.length > 0 && (
                    <button onClick={() => setExpanded(e => !e)} className="flex items-center gap-1 text-xs text-[#555] hover:text-[#888] mb-3 transition-colors">
                        <Clock className="w-3 h-3" />
                        Preferred times
                        {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                    </button>
                )}
                {expanded && (
                    <div className="flex flex-wrap gap-1.5 mb-3">
                        {task.preferred_times.map((t, i) => (
                            <span key={i} className="text-xs font-mono text-[#888] bg-[#1a1a1a] border border-[#262626] px-2 py-0.5 rounded-md">{t}</span>
                        ))}
                    </div>
                )}

                {/* Footer */}
                <div className="flex items-center justify-between pt-3 border-t border-[#1a1a1a]">
                    <div className="flex items-center gap-1.5 text-xs text-[#555]">
                        <div className={`w-1.5 h-1.5 rounded-full ${timeLeft === 'Now' ? 'bg-[#00E37C] animate-pulse' : 'bg-[#333]'}`} />
                        <span className="font-mono text-[#888]">{timeLeft}</span>
                    </div>
                    <button
                        onClick={() => confirm('Delete this monitor?') && onDelete?.(task.id)}
                        className="flex items-center gap-1.5 text-xs text-red-500/70 hover:text-red-400 active:scale-95 transition-all px-3 py-1.5 rounded-lg hover:bg-red-500/10"
                    >
                        <Trash2 className="w-3.5 h-3.5" />
                        Delete
                    </button>
                </div>
            </div>
        </div>
    );
}
