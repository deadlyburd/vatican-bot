'use client';

import { useState } from 'react';
import { api } from '@/lib/api';
import vaticanTickets from '../data/vatican_tickets.json';
import { X } from 'lucide-react';

interface TaskModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSuccess: () => void;
    agencyId: number | null;
    agencyPlan?: string;
}

const TIER_OPTIONS = [
    { value: 'notify', label: '🔔 Notify Only', desc: 'Alert when tickets open', plans: ['free', 'pro', 'agency'] },
    { value: 'hold',   label: '🔒 Notify + Hold', desc: 'Lock slot + send payment link', plans: ['pro', 'agency'] },
    { value: 'snipe',  label: '🤖 Notify + Hold + Snipe', desc: 'Auto-book with stored profile', plans: ['agency'] },
];

export default function TaskModal({ isOpen, onClose, onSuccess, agencyId, agencyPlan = 'free' }: TaskModalProps) {
    const [formData, setFormData] = useState({
        site: 'vatican' as 'vatican',
        dates: [] as string[],
        preferred_times: '',
        visitors: 2,
        tier: 'notify',
    });
    const [newDate, setNewDate] = useState('');
    const [loading, setLoading] = useState(false);
    const [selectedTicketId, setSelectedTicketId] = useState<string | null>(null);

    if (!isOpen) return null;

    const addDate = () => {
        if (newDate && !formData.dates.includes(newDate)) {
            setFormData({ ...formData, dates: [...formData.dates, newDate] });
            setNewDate('');
        }
    };

    const removeDate = (dateToRemove: string) => {
        setFormData({ ...formData, dates: formData.dates.filter((d: string) => d !== dateToRemove) });
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!agencyId) {
            alert('Session error. Please logout and login again.');
            return;
        }
        if (formData.dates.length === 0) {
            alert('Please add at least one date.');
            return;
        }
        if (!selectedTicketId) {
            alert('Please select a ticket type.');
            return;
        }
        
        setLoading(true);
        try {
            // Get ticket details from selected ticket
            const selectedTicket = vaticanTickets.find((t: any) => t.id === selectedTicketId);
            if (!selectedTicket) {
                throw new Error('Invalid ticket selection');
            }
            
            const ticketType = selectedTicket.ticket_type;
            const languageValue = selectedTicket.language;
            const ticketNameValue = selectedTicket.name.includes('Standard') 
                ? 'Musei Vaticani - Biglietti d\'ingresso'
                : 'Musei Vaticani - Visita Guidata';
            const areaName = selectedTicket.tag;
            
            const payload = {
                site: formData.site,
                area_name: areaName,
                dates: formData.dates,
                preferred_times: formData.preferred_times.split(',').map((t: string) => t.trim()).filter(Boolean),
                visitors: formData.visitors,
                agency: agencyId,
                ticket_type: ticketType,
                ticket_name: ticketNameValue,
                language: languageValue || undefined,
                tier: formData.tier,
                notification_mode: 'available_only',
            };

            await api.createTask(payload);

            onSuccess();
            onClose();
        } catch (err: unknown) {
            const message = err instanceof Error ? err.message : String(err);
            alert(`Error: ${message}`);
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 z-[100] flex items-end sm:items-center justify-center sm:p-6 bg-[#050505]/80 backdrop-blur-xl">
            <div className="w-full sm:max-w-xl bg-[#0F0F0F] border border-[#262626] relative overflow-hidden max-h-[92vh] overflow-y-auto rounded-t-2xl rounded-b-none sm:rounded-2xl">
                {/* Green accent bar */}
                <div className="h-1 w-full bg-[#00E37C]" />

                <div className="p-6">
                <button
                    onClick={onClose}
                    className="absolute top-3 right-3 text-[#888888] hover:text-white transition-colors w-8 h-8 flex items-center justify-center rounded-lg hover:bg-[#262626]"
                >
                    <X size={18} />
                </button>

                <div className="mb-6">
                    <h2 className="text-xl font-semibold text-white tracking-tight">New Monitor</h2>
                    <p className="text-[#888888] text-sm mt-1">Configure automated ticket tracking</p>
                </div>

                <form onSubmit={handleSubmit} className="space-y-6">
                    <div className="space-y-4">
                        {/* Ticket Selector - Primary Selection */}
                        <div>
                            <label className="block text-xs font-medium text-[#888888] uppercase tracking-wider mb-2">
                                Select Ticket Type
                            </label>
                            <select
                                value={selectedTicketId || ''}
                                onChange={(e: React.ChangeEvent<HTMLSelectElement>) => {
                                    setSelectedTicketId(e.target.value || null);
                                }}
                                className="w-full bg-[#1a1a1a] border border-[#262626] rounded-xl px-4 py-3 text-white focus:outline-none focus:border-[#00E37C]/50 text-sm"
                                required
                            >
                                <option value="">-- Select Ticket Type --</option>
                                {vaticanTickets.map((ticket: any) => (
                                    <option key={ticket.id} value={ticket.id}>
                                        {ticket.name}
                                    </option>
                                ))}
                            </select>
                            <p className="text-xs text-[#666666] mt-2">
                                Choose between standard entry or guided tours in different languages
                            </p>
                        </div>

                        {/* Visitors */}
                        <div>
                            <label className="block text-xs font-medium text-[#888888] uppercase tracking-wider mb-2">Number of Visitors</label>
                            <input
                                type="number"
                                min="1"
                                max="10"
                                value={formData.visitors}
                                onChange={(e) => setFormData({ ...formData, visitors: parseInt(e.target.value) })}
                                className="w-full bg-[#1a1a1a] border border-[#262626] rounded-xl px-4 py-3 text-white focus:outline-none focus:border-[#00E37C]/50 text-sm"
                                required
                            />
                        </div>

                        <div>
                            <label className="block text-xs font-medium text-[#888888] uppercase tracking-wider mb-2">Monitoring Dates</label>
                            <div className="flex gap-2 mb-3">
                                <input
                                    type="date"
                                    value={newDate}
                                    onChange={(e) => setNewDate(e.target.value)}
                                    className="flex-1 bg-[#1a1a1a] border border-[#262626] rounded-xl px-4 py-3 text-white focus:outline-none focus:border-[#00E37C]/50 text-sm"
                                />
                                <button
                                    type="button"
                                    onClick={addDate}
                                    className="px-6 bg-[#00E37C] text-[#050505] font-medium rounded-xl hover:bg-[#00E37C]/80 transition-colors"
                                >
                                    Add
                                </button>
                            </div>
                            <div className="flex flex-wrap gap-2 min-h-[44px] p-3 bg-[#1a1a1a] rounded-xl border border-dashed border-[#262626]">
                                {formData.dates.map(date => (
                                    <span key={date} className="bg-[#262626] border border-[#404040] px-3 py-1.5 rounded-lg text-xs font-mono text-white flex items-center gap-2">
                                        {date}
                                        <button type="button" onClick={() => removeDate(date)} className="text-[#888888] hover:text-[#FF4D4D]">×</button>
                                    </span>
                                ))}
                                {formData.dates.length === 0 && <span className="text-xs text-[#888888]">No dates selected</span>}
                            </div>
                        </div>

                        {/* Preferred Times */}
                        <div>
                            <label className="block text-xs font-medium text-[#888888] uppercase tracking-wider mb-2">Preferred Times (Optional)</label>
                            <input
                                type="text"
                                placeholder="e.g. 09:00, 10:30, 14:00"
                                value={formData.preferred_times}
                                onChange={(e) => setFormData({ ...formData, preferred_times: e.target.value })}
                                className="w-full bg-[#1a1a1a] border border-[#262626] rounded-xl px-4 py-3 text-white focus:outline-none focus:border-[#00E37C]/50 text-sm placeholder:text-[#888888]"
                            />
                            <p className="text-xs text-[#666666] mt-2">
                                You'll be notified of all available slots, but preferred times will be highlighted
                            </p>
                        </div>

                        {/* Tier Selection */}
                        <div>
                            <label className="block text-xs font-medium text-[#888888] uppercase tracking-wider mb-2">Monitoring Tier</label>
                            <div className="space-y-2">
                                {TIER_OPTIONS.map(opt => {
                                    const locked = !opt.plans.includes(agencyPlan);
                                    return (
                                        <button
                                            key={opt.value}
                                            type="button"
                                            disabled={locked}
                                            onClick={() => !locked && setFormData({ ...formData, tier: opt.value })}
                                            className={`w-full flex items-center justify-between px-4 py-3 rounded-xl border text-left transition-all
                                                ${formData.tier === opt.value && !locked
                                                    ? 'border-[#00E37C] bg-[#00E37C]/5 text-white'
                                                    : locked
                                                        ? 'border-[#262626] bg-[#111] text-[#444] cursor-not-allowed'
                                                        : 'border-[#262626] bg-[#1a1a1a] text-[#888] hover:border-[#404040]'
                                                }`}
                                        >
                                            <div>
                                                <div className="text-sm font-medium">{opt.label}</div>
                                                <div className="text-xs mt-0.5 opacity-70">{opt.desc}</div>
                                            </div>
                                            {locked && (
                                                <span className="text-[10px] px-2 py-0.5 bg-[#262626] text-[#555] rounded-full uppercase shrink-0 ml-2">
                                                    {opt.plans[0]} plan
                                                </span>
                                            )}
                                            {!locked && formData.tier === opt.value && (
                                                <div className="w-4 h-4 rounded-full bg-[#00E37C] flex items-center justify-center shrink-0 ml-2">
                                                    <div className="w-2 h-2 rounded-full bg-[#050505]" />
                                                </div>
                                            )}
                                        </button>
                                    );
                                })}
                            </div>
                        </div>
                    </div>

                    <button
                        disabled={loading || !agencyId || !selectedTicketId}
                        type="submit"
                        className="w-full bg-[#00E37C] text-[#050505] font-semibold py-3 rounded-xl hover:bg-[#00E37C]/90 active:scale-95 transition-all disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                    >
                        {!agencyId ? 'Initializing Session...' : loading ? 'Creating Monitor...' : 'Create Monitor'}
                    </button>                </form>
                </div>
            </div>
        </div>
    );
}
