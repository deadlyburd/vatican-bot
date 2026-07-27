
import { useEffect, useState } from 'react';
import { api, CheckResult } from '@/lib/api';
import { CheckCircle, XCircle, AlertTriangle, Clock, Search, Zap, Globe, ChevronDown, ChevronUp } from 'lucide-react';

interface LogsViewProps {
    agencyId: number | null;
}

export default function LogsView({ agencyId }: LogsViewProps) {
    const [logs, setLogs] = useState<CheckResult[]>([]);
    const [loading, setLoading] = useState(true);
    const [expandedLog, setExpandedLog] = useState<number | null>(null);

    useEffect(() => {
        if (!agencyId) return;

        const fetchLogs = async () => {
            try {
                // Fetch last 100 results
                const data = await api.getResults(undefined, agencyId);
                setLogs(data.slice(0, 100));
            } catch (e) {
                console.error("Failed to fetch logs", e);
            } finally {
                setLoading(false);
            }
        };

        fetchLogs();
        const interval = setInterval(fetchLogs, 5000);
        return () => clearInterval(interval);
    }, [agencyId]);

    if (loading) return <div className="text-[#888888] text-sm animate-pulse">Loading logs...</div>;

    if (logs.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center py-20 text-[#888888]">
                <Clock className="w-12 h-12 mb-4 opacity-20" />
                <p>No activity logs recorded yet.</p>
            </div>
        );
    }

    return (
        <div className="space-y-4">
            <div className="flex justify-between items-center mb-6">
                <h2 className="text-xl font-semibold text-white">System Logs</h2>
                <div className="flex items-center gap-4">
                    {/* Legend */}
                    <div className="flex items-center gap-3 text-xs">
                        <span className="flex items-center gap-1 text-[#888888]">
                            <Zap className="w-3 h-3 text-blue-400" />
                            Headless
                        </span>
                        <span className="flex items-center gap-1 text-[#888888]">
                            <Globe className="w-3 h-3 text-purple-400" />
                            Browser
                        </span>
                    </div>
                    <div className="text-xs text-[#888888]">Auto-refreshing every 5s</div>
                </div>
            </div>

            <div className="border border-[#262626] rounded-xl overflow-hidden bg-[#0F0F0F]">
                <table className="w-full text-left text-sm">
                    <thead className="bg-[#1a1a1a] text-[#888888]">
                        <tr>
                            <th className="px-4 py-3 font-medium">Status</th>
                            <th className="px-4 py-3 font-medium">Method</th>
                            <th className="px-4 py-3 font-medium">Time</th>
                            <th className="px-4 py-3 font-medium">Task</th>
                            <th className="px-4 py-3 font-medium">Details</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-[#262626]">
                        {logs.map((log) => (
                            <>
                                <tr 
                                    key={log.id} 
                                    className="hover:bg-[#1a1a1a]/50 transition-colors cursor-pointer"
                                    onClick={() => setExpandedLog(expandedLog === log.id ? null : log.id)}
                                >
                                    <td className="px-4 py-3">
                                        <StatusBadge status={log.status} />
                                    </td>
                                    <td className="px-4 py-3">
                                        <MethodBadge 
                                            method={log.check_method || log.details?.check_method} 
                                            responseTime={log.response_time_ms}
                                        />
                                    </td>
                                    <td className="px-4 py-3 text-[#CCCCCC]">
                                        {new Date(log.check_time).toLocaleString('en-US', {
                                            month: 'short',
                                            day: '2-digit',
                                            hour: '2-digit',
                                            minute: '2-digit',
                                            second: '2-digit',
                                            hour12: false
                                        })}
                                    </td>
                                    <td className="px-4 py-3 text-[#888888] font-mono text-xs">
                                        Task #{log.task}
                                    </td>
                                    <td className="px-4 py-3">
                                        <div className="flex items-center gap-2">
                                            {log.found_count > 0 ? (
                                                <span className="text-emerald-400 font-medium">
                                                    Found {log.found_count} tickets
                                                </span>
                                            ) : (
                                                <span className="text-[#888888]">No availability</span>
                                            )}
                                            {expandedLog === log.id ? (
                                                <ChevronUp className="w-4 h-4 text-[#888888]" />
                                            ) : (
                                                <ChevronDown className="w-4 h-4 text-[#888888]" />
                                            )}
                                        </div>
                                    </td>
                                </tr>
                                {/* Expanded Details Row */}
                                {expandedLog === log.id && log.details && (
                                    <tr className="bg-[#1a1a1a]/30">
                                        <td colSpan={5} className="px-4 py-4">
                                            <LogDetails details={log.details} />
                                        </td>
                                    </tr>
                                )}
                            </>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

function StatusBadge({ status }: { status: string }) {
    if (status === 'available') {
        return (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
                <CheckCircle className="w-3.5 h-3.5" />
                Available
            </span>
        );
    }
    if (status === 'sold_out' || status === 'closed') {
        return (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-500/10 text-red-500 border border-red-500/20">
                <XCircle className="w-3.5 h-3.5" />
                {status === 'closed' ? 'Closed' : 'Sold Out'}
            </span>
        );
    }
    return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-500/10 text-yellow-500 border border-yellow-500/20">
            <AlertTriangle className="w-3.5 h-3.5" />
            {status}
        </span>
    );
}

function MethodBadge({ method, responseTime }: { method?: string; responseTime?: number }) {
    const isHeadless = method === 'headless' || method === 'god_tier_headless';
    
    if (isHeadless) {
        return (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-blue-500/10 text-blue-400 border border-blue-500/20">
                <Zap className="w-3 h-3" />
                Headless
                {responseTime && (
                    <span className="text-[10px] opacity-70">({responseTime}ms)</span>
                )}
            </span>
        );
    }
    
    return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-purple-500/10 text-purple-400 border border-purple-500/20">
            <Globe className="w-3 h-3" />
            Browser
            {responseTime && (
                <span className="text-[10px] opacity-70">({responseTime}ms)</span>
            )}
        </span>
    );
}

function LogDetails({ details }: { details: CheckResult['details'] }) {
    if (!details) return null;
    
    return (
        <div className="space-y-3">
            {/* Ticket Info */}
            {(details.ticket_name || details.ticket_id) && (
                <div className="flex items-center gap-4 text-sm">
                    {details.ticket_name && (
                        <span className="text-white font-medium">{details.ticket_name}</span>
                    )}
                    {details.ticket_id && (
                        <span className="text-[#888888] font-mono text-xs">ID: {details.ticket_id}</span>
                    )}
                    {details.language && (
                        <span className="px-2 py-0.5 rounded-full text-xs bg-[#262626] text-[#888888]">
                            {details.language}
                        </span>
                    )}
                </div>
            )}
            
            {/* Date */}
            {details.date && (
                <div className="text-xs text-[#888888]">
                    Date: <span className="text-[#CCCCCC]">{details.date}</span>
                </div>
            )}
            
            {/* State Change Indicator */}
            {details.state_changed && (
                <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
                    <span className="text-emerald-400 text-sm font-medium">
                        🔔 State Changed: Closed → Open
                    </span>
                </div>
            )}
            
            {/* Slots */}
            {details.slots && details.slots.length > 0 && (
                <div>
                    <div className="text-xs text-[#888888] mb-2">Available Time Slots:</div>
                    <div className="flex flex-wrap gap-2">
                        {details.slots.map((slot, idx) => (
                            <span 
                                key={idx}
                                className="px-2 py-1 rounded-lg bg-emerald-500/10 text-emerald-400 text-xs font-medium border border-emerald-500/20"
                            >
                                {typeof slot === 'string' ? slot : slot.time}
                            </span>
                        ))}
                    </div>
                </div>
            )}
            
            {/* Check Method */}
            {details.check_method && (
                <div className="text-xs text-[#888888]">
                    Check Method: <span className="text-[#CCCCCC]">{details.check_method}</span>
                </div>
            )}
        </div>
    );
}
