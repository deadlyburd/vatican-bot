'use client';

import { useState } from 'react';
import { api } from '@/lib/api';
import { Lock, User, Zap, AlertCircle } from 'lucide-react';

interface LoginPageProps {
    onLoginSuccess: (sessionToken: string, agency: any, user: any) => void;
}

export default function LoginPage({ onLoginSuccess }: LoginPageProps) {
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');

    const handleLogin = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(''); setLoading(true);
        try {
            const response = await api.login(username, password);
            localStorage.setItem('session_token', response.session_token);
            localStorage.setItem('user', JSON.stringify(response.user));
            localStorage.setItem('agency', JSON.stringify(response.agency));
            onLoginSuccess(response.session_token, response.agency, response.user);
        } catch (err: any) {
            setError(err.message || 'Login failed');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-[#050505] flex flex-col items-center justify-center px-4 py-8">
            <div className="w-full max-w-sm">
                {/* Logo */}
                <div className="text-center mb-8">
                    <div className="w-14 h-14 rounded-2xl bg-[#0F0F0F] border border-[#262626] flex items-center justify-center mx-auto mb-4">
                        <Zap className="w-7 h-7 text-[#00E37C]" />
                    </div>
                    <h1 className="text-2xl font-semibold text-white">HYDRA Monitor</h1>
                    <p className="text-[#888888] text-sm mt-1">Sign in to your account</p>
                </div>

                <div className="bg-[#0F0F0F] border border-[#262626] rounded-2xl p-6">
                    {error && (
                        <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-xl flex items-start gap-2">
                            <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
                            <p className="text-sm text-red-400">{error}</p>
                        </div>
                    )}

                    <form onSubmit={handleLogin} className="space-y-4">
                        <div>
                            <label className="block text-xs font-medium text-[#888888] mb-1.5">Username</label>
                            <div className="relative">
                                <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#666666]" />
                                <input
                                    type="text"
                                    value={username}
                                    onChange={e => setUsername(e.target.value)}
                                    placeholder="Enter username"
                                    className="w-full pl-10 pr-4 py-3 bg-[#1A1A1A] border border-[#262626] rounded-xl text-white text-sm placeholder-[#555] focus:outline-none focus:border-[#00E37C] transition-colors"
                                    required autoCapitalize="none" autoCorrect="off"
                                />
                            </div>
                        </div>

                        <div>
                            <label className="block text-xs font-medium text-[#888888] mb-1.5">Password</label>
                            <div className="relative">
                                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#666666]" />
                                <input
                                    type="password"
                                    value={password}
                                    onChange={e => setPassword(e.target.value)}
                                    placeholder="Enter password"
                                    className="w-full pl-10 pr-4 py-3 bg-[#1A1A1A] border border-[#262626] rounded-xl text-white text-sm placeholder-[#555] focus:outline-none focus:border-[#00E37C] transition-colors"
                                    required
                                />
                            </div>
                        </div>

                        <button
                            type="submit"
                            disabled={loading}
                            className="w-full bg-[#00E37C] text-black font-semibold py-3 rounded-xl hover:bg-[#00E37C]/90 active:scale-95 transition-all disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                        >
                            {loading ? 'Signing in...' : 'Sign In'}
                        </button>
                    </form>
                </div>
            </div>
        </div>
    );
}
