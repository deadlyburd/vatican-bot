'use client';

import { useState, useMemo } from 'react';
import { Lock, Search, Filter } from 'lucide-react';

interface HeldSlot {
  id: number;
  date: string;
  slot_time: string;
  ticket_name: string;
  visitors: number;
  total_price: string;
  status: string;
  hold_duration_minutes: number;
}

export default function HoldsView({ slots }: { slots: HeldSlot[] }) {
  const [filterDate, setFilterDate] = useState('');
  const [filterTime, setFilterTime] = useState('');
  const [filterVisitors, setFilterVisitors] = useState('');
  const [filterMonth, setFilterMonth] = useState('all');

  const filtered = useMemo(() => {
    return slots.filter(h => {
      if (filterMonth !== 'all') {
        if (filterMonth === 'april' && !h.date?.includes('/04/')) return false;
        if (filterMonth === 'may' && !h.date?.includes('/05/')) return false;
      }
      if (filterDate && !h.date?.includes(filterDate)) return false;
      if (filterTime && !h.slot_time?.includes(filterTime)) return false;
      if (filterVisitors && String(h.visitors) !== filterVisitors) return false;
      return true;
    });
  }, [slots, filterDate, filterTime, filterVisitors, filterMonth]);

  const totalValue = filtered.reduce((s, h) => s + parseFloat(h.total_price || '0'), 0);

  const inputCls = "bg-[#1a1a1a] border border-[#262626] rounded-xl px-3 py-2 text-white text-xs focus:outline-none focus:border-[#00E37C]/50 placeholder:text-[#555]";

  return (
    <div>
      {/* Filter bar */}
      <div className="flex flex-wrap gap-2 mb-4">
        <div className="flex gap-1">
          {['all','april','may'].map(m => (
            <button key={m} onClick={() => setFilterMonth(m)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all capitalize ${
                filterMonth === m ? 'bg-[#00E37C] text-[#050505]' : 'bg-[#1a1a1a] border border-[#262626] text-[#888] hover:text-white'
              }`}>
              {m === 'all' ? 'All' : m === 'april' ? '🌸 April' : '🌿 May'}
            </button>
          ))}
        </div>
        <input
          className={inputCls}
          placeholder="Filter date (e.g. 15/04)"
          value={filterDate}
          onChange={e => setFilterDate(e.target.value)}
          style={{width: 150}}
        />
        <input
          className={inputCls}
          placeholder="Filter time (e.g. 11:00)"
          value={filterTime}
          onChange={e => setFilterTime(e.target.value)}
          style={{width: 150}}
        />
        <select
          className={inputCls}
          value={filterVisitors}
          onChange={e => setFilterVisitors(e.target.value)}
        >
          <option value="">All visitors</option>
          {[1,2,3,4,5].map(v => <option key={v} value={v}>{v} visitor{v>1?'s':''}</option>)}
        </select>
        {(filterDate || filterTime || filterVisitors || filterMonth !== 'all') && (
          <button onClick={() => { setFilterDate(''); setFilterTime(''); setFilterVisitors(''); setFilterMonth('all'); }}
            className="px-3 py-1.5 rounded-lg text-xs text-red-400 border border-red-500/20 bg-red-500/10 hover:bg-red-500/20 transition-all">
            Clear
          </button>
        )}
        <span className="ml-auto text-xs text-[#666] self-center">
          {filtered.length} slots · <span className="text-[#00E37C] font-semibold">€{totalValue.toLocaleString()}</span>
        </span>
      </div>

      {/* Table */}
      {filtered.length === 0 ? (
        <div className="bg-[#0F0F0F] border border-[#262626] rounded-2xl flex flex-col items-center justify-center py-16 text-center">
          <Lock className="w-8 h-8 text-[#555] mb-3" />
          <p className="text-[#888] text-sm">No holds match your filters</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-[#262626]">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#262626] bg-[#0a0a0a]">
                <th className="text-left px-4 py-3 text-xs text-[#666] font-medium">Date</th>
                <th className="text-left px-4 py-3 text-xs text-[#666] font-medium">Time</th>
                <th className="text-left px-4 py-3 text-xs text-[#666] font-medium">Visitors</th>
                <th className="text-left px-4 py-3 text-xs text-[#666] font-medium">Price</th>
                <th className="text-left px-4 py-3 text-xs text-[#666] font-medium">Ticket</th>
                <th className="text-left px-4 py-3 text-xs text-[#666] font-medium">Held for</th>
                <th className="text-left px-4 py-3 text-xs text-[#666] font-medium">Hold #</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((h, i) => {
                const hrs = Math.floor(h.hold_duration_minutes / 60);
                const mins = h.hold_duration_minutes % 60;
                return (
                  <tr key={h.id} className={`border-b border-[#1a1a1a] ${i % 2 === 0 ? 'bg-[#0F0F0F]' : 'bg-[#0a0a0a]'} hover:bg-[#141414] transition-colors`}>
                    <td className="px-4 py-3 text-white font-mono text-xs">{h.date}</td>
                    <td className="px-4 py-3 text-[#00E37C] font-mono text-xs font-semibold">{h.slot_time}</td>
                    <td className="px-4 py-3 text-white text-xs">👥 {h.visitors}</td>
                    <td className="px-4 py-3 text-[#00E37C] text-xs font-semibold">€{h.total_price}</td>
                    <td className="px-4 py-3 text-[#888] text-xs truncate max-w-[160px]">{h.ticket_name?.replace('Musei Vaticani - ', '')}</td>
                    <td className="px-4 py-3 text-[#666] text-xs">{hrs > 0 ? `${hrs}h ` : ''}{mins}m</td>
                    <td className="px-4 py-3 text-[#555] text-xs">#{h.id}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
