'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { Loader2, Globe, ChevronDown, Clock, Ticket } from 'lucide-react';

interface TicketItem {
    id: string;
    name: string;
    originalName: string;
    description: string; // ✅ NEW
    category: string;
    timeSlot: string | null;
    needsLanguage: boolean;
    availableLanguages: string[];
    ticketType: number;
}

interface TicketSelectorProps {
    date: string;
    visitors: number;
    selectedTicketId: string | null;
    selectedTicketName: string | null;
    selectedLanguage: string | null;
    onSelectTicket: (ticketId: string, ticketName: string) => void;
    onSelectLanguage: (language: string | null) => void;
}

export default function TicketSelector({
    date,
    visitors,
    selectedTicketId,
    selectedLanguage,
    onSelectTicket,
    onSelectLanguage
}: TicketSelectorProps) {
    const [tickets, setTickets] = useState<TicketItem[]>([]);
    const [grouped, setGrouped] = useState<Record<string, TicketItem[]>>({});
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [expandedCategory, setExpandedCategory] = useState<string | null>(null);

    useEffect(() => {
        const fetchTickets = async () => {
            if (!date) {
                setLoading(false);
                return;
            }

            try {
                setLoading(true);
                setError(null);
                const data = await api.getVaticanTickets(date, visitors);
                setTickets(data.tickets || []);
                setGrouped(data.grouped || {});

                // Auto-expand first category
                if (data.grouped) {
                    const categories = Object.keys(data.grouped);
                    if (categories.length > 0) {
                        setExpandedCategory(categories[0]);
                    }
                }
            } catch (err) {
                console.error('Failed to fetch tickets:', err);
                setError('Failed to load tickets. Please try again.');
            } finally {
                setLoading(false);
            }
        };

        fetchTickets();
    }, [date]);

    if (!date) {
        return (
            <div className="p-4 bg-[#1a1a1a] rounded-xl border border-[#262626]">
                <p className="text-sm text-[#888888]">Please select a date first to view available tickets.</p>
            </div>
        );
    }

    if (loading) {
        return (
            <div className="p-6 bg-[#1a1a1a] rounded-xl border border-[#262626] flex items-center justify-center gap-3">
                <Loader2 className="w-5 h-5 animate-spin text-[#00E37C]" />
                <span className="text-sm text-[#888888]">Loading tickets for {date}...</span>
            </div>
        );
    }

    if (error) {
        return (
            <div className="p-4 bg-[#FF4D4D]/10 rounded-xl border border-[#FF4D4D]/20">
                <p className="text-sm text-[#FF4D4D]">{error}</p>
            </div>
        );
    }

    if (tickets.length === 0) {
        return (
            <div className="p-4 bg-orange-500/10 rounded-xl border border-orange-500/20">
                <p className="text-sm text-orange-400">No tickets found for {date}. Try a different date.</p>
            </div>
        );
    }

    const categories = Object.keys(grouped);

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                    <Ticket className="w-4 h-4 text-[#888888]" />
                    <label className="text-sm font-medium text-white">
                        Select Ticket ({tickets.length} available)
                    </label>
                </div>
            </div>

            {/* Grouped Ticket Display */}
            <div className="space-y-3 max-h-[400px] overflow-y-auto pr-2">
                {categories.map((category) => {
                    const categoryTickets = grouped[category];
                    const isExpanded = expandedCategory === category;
                    const hasTimeSlots = categoryTickets.some(t => t.timeSlot);
                    const ticketType = categoryTickets[0]?.ticketType;

                    return (
                        <div
                            key={category}
                            className="border border-[#262626] rounded-xl overflow-hidden"
                        >
                            {/* Category Header */}
                            <button
                                type="button"
                                onClick={() => setExpandedCategory(isExpanded ? null : category)}
                                className="w-full px-4 py-3 flex items-center justify-between bg-[#1a1a1a] hover:bg-[#222222] transition-colors"
                            >
                                <div className="flex items-center gap-3">
                                    <span className={`
                                        text-xs px-2 py-0.5 rounded-full font-medium
                                        ${ticketType === 0
                                            ? 'bg-[#00E37C]/20 text-[#00E37C]'
                                            : 'bg-purple-500/20 text-purple-400'
                                        }
                                    `}>
                                        {ticketType === 0 ? 'Standard' : 'Guided'}
                                    </span>
                                    <span className="font-medium text-white text-sm">{category}</span>
                                    <span className="text-xs text-[#888888]">
                                        ({categoryTickets.length} {hasTimeSlots ? 'time slots' : 'options'})
                                    </span>
                                </div>
                                <ChevronDown className={`w-4 h-4 text-[#888888] transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
                            </button>

                            {/* Ticket List */}
                            {isExpanded && (
                                <div className="p-3 bg-[#0d0d0d] space-y-2">
                                    {categoryTickets.map((ticket, index) => {
                                        const isSelected = selectedTicketId === ticket.id;

                                        return (
                                            <div
                                                key={ticket.id}
                                                className={`
                                                    border rounded-lg p-3 transition-all duration-200 cursor-pointer
                                                    ${isSelected
                                                        ? 'border-[#00E37C] bg-[#00E37C]/10'
                                                        : 'border-[#262626] bg-[#1a1a1a] hover:border-[#404040]'
                                                    }
                                                `}
                                                onClick={() => {
                                                    onSelectTicket(ticket.id, ticket.originalName);
                                                    if (!ticket.needsLanguage) {
                                                        onSelectLanguage(null);
                                                    }
                                                }}
                                            >
                                                <div className="flex items-start gap-3">
                                                    <input
                                                        type="radio"
                                                        name="ticket"
                                                        value={ticket.id}
                                                        checked={isSelected}
                                                        onChange={() => { }}
                                                        className="mt-1 w-4 h-4 accent-[#00E37C]"
                                                    />

                                                    <div className="flex-1">
                                                        {/* Ticket number badge */}
                                                        <div className="flex items-center gap-2 mb-1">
                                                            <span className="text-xs bg-[#333] text-[#888] px-2 py-0.5 rounded font-mono">
                                                                #{index + 1}
                                                            </span>
                                                        </div>

                                                        {/* Full ticket name - PROMINENT */}
                                                        <div className="text-white text-sm leading-relaxed font-medium">
                                                            {ticket.originalName}
                                                        </div>

                                                        {/* Description / Subtitle */}
                                                        {ticket.description && (
                                                            <div className="text-xs text-[#888888] mt-1 leading-relaxed">
                                                                {ticket.description}
                                                            </div>
                                                        )}
                                                    </div>
                                                </div>

                                                {/* Language selector for guided tours */}
                                                {isSelected && ticket.needsLanguage && (
                                                    <div className="mt-3 ml-7 pl-3 border-l-2 border-[#00E37C]/30">
                                                        <label className="block text-xs font-medium text-[#888888] mb-2">
                                                            🌐 Tour Language
                                                        </label>

                                                        <div className="relative">
                                                            <select
                                                                value={selectedLanguage || ''}
                                                                onChange={(e) => onSelectLanguage(e.target.value || null)}
                                                                onClick={(e) => e.stopPropagation()}
                                                                className="w-full px-3 py-2 pr-8 bg-[#262626] border border-[#404040] rounded-lg text-sm text-white focus:outline-none focus:border-[#00E37C] appearance-none cursor-pointer"
                                                            >
                                                                <option value="">-- Choose Language --</option>
                                                                {ticket.availableLanguages.map((lang) => {
                                                                    const langNames: Record<string, string> = {
                                                                        'ENG': '🇬🇧 English',
                                                                        'ITA': '🇮🇹 Italian',
                                                                        'FRA': '🇫🇷 French',
                                                                        'DEU': '🇩🇪 German',
                                                                        'SPA': '🇪🇸 Spanish'
                                                                    };

                                                                    return (
                                                                        <option key={lang} value={lang}>
                                                                            {langNames[lang] || lang}
                                                                        </option>
                                                                    );
                                                                })}
                                                            </select>

                                                            <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#888888] pointer-events-none" />
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
