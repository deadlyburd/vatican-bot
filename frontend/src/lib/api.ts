export interface Agency {
    id: number;
    name: string;
    api_key: string;
    telegram_chat_id: string;
    is_active: boolean;
    created_at: string;
    plan: 'free' | 'pro' | 'agency';
    task_limit: number;
    owner_id?: string;
}

export interface MonitorTask {
    id: number;
    agency: number;
    agency_name: string;
    site: 'vatican';
    area_name: string;
    dates: string[];
    preferred_times: string[];
    visitors: number;
    ticket_type: number;
    ticket_id?: string;
    ticket_name?: string;
    language: string;
    tier?: 'notify' | 'hold' | 'snipe';
    is_active: boolean;
    last_checked: string | null;
    check_interval: number;
    last_status?: string;
    last_result_summary?: string;
    created_at: string;
    latest_check?: CheckResult | null;
}

export interface CheckResult {
    id: number;
    task: number;
    status: 'available' | 'sold_out' | 'error' | 'closed';
    found_count: number;
    check_time: string;
    screenshot: string | null;
    // ✅ NEW: God-Tier monitor fields
    check_method?: 'headless' | 'browser' | 'hybrid';
    response_time_ms?: number;
    details?: {
        date?: string;
        ticket_id?: string;
        ticket_name?: string;
        language?: string;
        slots?: { time: string; availability: string }[];
        state_changed?: boolean;
        previous_state?: string;
        is_first_check?: boolean;
        check_method?: string;
    };
}

const getApiUrl = () => {
    // In the browser, always use the relative proxy path so requests go through
    // the Next.js API route (/api/v1/...) which forwards to the backend server-side.
    // This avoids CORS issues and keeps the backend URL secret.
    if (typeof window !== 'undefined') {
        return '/api/v1';
    }
    // Server-side (SSR/build): use env var or direct backend
    const envUrl = process.env.NEXT_PUBLIC_API_URL;
    if (envUrl) {
        return envUrl.endsWith('/') ? envUrl.slice(0, -1) : envUrl;
    }
    return 'http://localhost:8000/api/v1';
};

export const api = {
    getApiUrl: getApiUrl,
    
    // Authentication
    login: async (username: string, password: string) => {
        const res = await fetch(`${getApiUrl()}/auth/login/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ username, password }),
        });
        if (!res.ok) {
            const error = await res.json();
            throw new Error(error.error || 'Login failed');
        }
        return res.json();
    },
    
    register: async (email: string, username: string, password: string, fullName?: string) => {
        const res = await fetch(`${getApiUrl()}/auth/register/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ email, username, password, full_name: fullName }),
        });
        if (!res.ok) {
            const error = await res.json();
            throw new Error(error.error || 'Registration failed');
        }
        return res.json();
    },
    
    logout: async (sessionToken: string) => {
        const res = await fetch(`${getApiUrl()}/auth/logout/`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${sessionToken}`,
            },
        });
        if (!res.ok) throw new Error('Logout failed');
        return res.json();
    },
    
    verifySession: async (sessionToken: string) => {
        const res = await fetch(`${getApiUrl()}/auth/verify/`, {
            headers: {
                'Authorization': `Bearer ${sessionToken}`,
            },
        });
        if (!res.ok) throw new Error('Session invalid');
        return res.json();
    },
    
    getMyAgency: async (ownerId?: string, email?: string) => {
        const res = await fetch(`${getApiUrl()}/my-agency/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                owner_id: ownerId || 'local-admin',
                email: email || 'admin@local.com'
            }),
        });
        if (!res.ok) throw new Error('Failed to get agency');
        return res.json();
    },
    updateAgency: async (agencyId: number, data: Partial<Agency>) => {
        const res = await fetch(`${getApiUrl()}/agencies/${agencyId}/`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data),
        });
        if (!res.ok) throw new Error('Failed to update agency');
        return res.json();
    },
    getAgencies: async (): Promise<Agency[]> => {
        const res = await fetch(`${getApiUrl()}/agencies/`);
        if (!res.ok) throw new Error('Failed to fetch agencies');
        return res.json();
    },
    createAgency: async (data: Partial<Agency>) => {
        const res = await fetch(`${getApiUrl()}/agencies/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data),
        });
        if (!res.ok) throw new Error('Failed to create agency');
        return res.json();
    },
    getTasks: async (agencyId?: number): Promise<MonitorTask[]> => {
        const sessionToken = typeof window !== 'undefined' ? localStorage.getItem('session_token') : null;
        const headers: HeadersInit = {};
        if (sessionToken) {
            headers['Authorization'] = `Bearer ${sessionToken}`;
        }
        
        const url = agencyId
            ? `${getApiUrl()}/tasks/?agency_id=${agencyId}`
            : `${getApiUrl()}/tasks/`;
        const res = await fetch(url, { headers });
        if (!res.ok) throw new Error('Failed to fetch tasks');
        return res.json();
    },
    getResults: async (taskId?: number, agencyId?: number): Promise<CheckResult[]> => {
        const sessionToken = typeof window !== 'undefined' ? localStorage.getItem('session_token') : null;
        const headers: HeadersInit = {};
        if (sessionToken) {
            headers['Authorization'] = `Bearer ${sessionToken}`;
        }
        
        const baseUrl = getApiUrl();
        let url = `${baseUrl}/results/`;
        const params = new URLSearchParams();
        if (taskId) params.append('task', taskId.toString());
        if (agencyId) params.append('agency_id', agencyId.toString());

        if (params.toString()) {
            url += `?${params.toString()}`;
        }

        const res = await fetch(url, { headers });
        if (!res.ok) throw new Error('Failed to fetch results');
        return res.json();
    },
    createTask: async (payload: any): Promise<void> => {
        const res = await fetch(`${getApiUrl()}/tasks/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(JSON.stringify(err));
        }
        if (!res.ok) {
            const err = await res.json();
            throw new Error(JSON.stringify(err));
        }
    },
    deleteTask: async (taskId: number): Promise<void> => {
        const res = await fetch(`${getApiUrl()}/tasks/${taskId}/`, {
            method: 'DELETE',
        });
        if (!res.ok) throw new Error('Failed to delete task');
    },

    // ✅ NEW: Vatican Ticket Discovery
    getVaticanTickets: async (date: string, visitors?: number) => {
        const params = new URLSearchParams();
        params.append('date', date);
        if (visitors) {
            params.append('visitors', visitors.toString());
        }
        const res = await fetch(`${getApiUrl()}/vatican/tickets/?${params.toString()}`);
        if (!res.ok) throw new Error(' Failed to fetch Vatican tickets');
        return res.json();
    }
};
