/**
 * Admin Dashboard for Customer Care Bot
 * =======================================
 * Lets the admin:
 * - Configure what info the bot should use
 * - Set what the bot should tell customers
 * - View AI-filtered CRM insights
 * - Manage products and bookings
 * - Control bot behavior
 */

'use client';

import { useState, useEffect } from 'react';

const API_BASE = '/api/customer-care';

interface Insight {
  category: string;
  title: string;
  description: string;
  confidence: number;
  priority: string;
  action_required: boolean;
}

interface BotStats {
  total_bookings: number;
  total_activities: number;
  total_products: number;
  unique_customers: number;
  upcoming_30_days: number;
}

interface BotConfig {
  features: Record<string, boolean>;
  persona: {
    name: string;
    tone: string;
    response_length: string;
  };
  ai: {
    provider: string;
    model: string;
    temperature: number;
  };
}

export default function AdminDashboard() {
  const [activeTab, setActiveTab] = useState<'overview' | 'config' | 'insights' | 'products' | 'crm'>('overview');
  const [stats, setStats] = useState<BotStats | null>(null);
  const [insights, setInsights] = useState<Insight[]>([]);
  const [config, setConfig] = useState<BotConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [customerEmail, setCustomerEmail] = useState('');
  const [customerData, setCustomerData] = useState<any>(null);

  useEffect(() => {
    loadStatus();
    loadInsights();
    loadConfig();
  }, []);

  const loadStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/status/`);
      const data = await res.json();
      if (data.status === 'ok') {
        setStats(data.stats);
      }
    } catch (e) {
      setError('Failed to load status');
    }
  };

  const loadInsights = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/insights/`);
      const data = await res.json();
      setInsights(data.insights || []);
    } catch (e) {
      console.error('Failed to load insights:', e);
    } finally {
      setLoading(false);
    }
  };

  const loadConfig = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/config/`);
      const data = await res.json();
      setConfig(data);
    } catch (e) {
      console.error('Failed to load config:', e);
    }
  };

  const updateFeature = async (feature: string, enabled: boolean) => {
    if (!config) return;
    const newFeatures = { ...config.features, [feature]: enabled };
    try {
      await fetch(`${API_BASE}/api/config/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ features: newFeatures }),
      });
      setConfig({ ...config, features: newFeatures });
    } catch (e) {
      setError('Failed to update config');
    }
  };

  const lookupCustomer = async () => {
    if (!customerEmail) return;
    try {
      const res = await fetch(`${API_BASE}/api/customer/?email=${encodeURIComponent(customerEmail)}`);
      const data = await res.json();
      setCustomerData(data);
    } catch (e) {
      setError('Customer lookup failed');
    }
  };

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'critical': return 'bg-red-100 text-red-800 border-red-200';
      case 'high': return 'bg-orange-100 text-orange-800 border-orange-200';
      case 'medium': return 'bg-yellow-100 text-yellow-800 border-yellow-200';
      default: return 'bg-gray-100 text-gray-800 border-gray-200';
    }
  };

  const getCategoryIcon = (category: string) => {
    switch (category) {
      case 'booking_pattern': return '📊';
      case 'customer_behavior': return '👥';
      case 'product_trend': return '📈';
      case 'revenue': return '💰';
      case 'operational': return '⚙️';
      default: return '📋';
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">🏛️ Roma Assistant Dashboard</h1>
              <p className="text-sm text-gray-500">Customer Care Bot Management</p>
            </div>
            <div className="flex items-center gap-2">
              <span className="px-3 py-1 bg-green-100 text-green-800 rounded-full text-sm font-medium">
                ● Bot Active
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* Navigation */}
      <nav className="bg-white border-b">
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex gap-1">
            {[
              { id: 'overview', label: '📊 Overview', },
              { id: 'config', label: '⚙️ Bot Config', },
              { id: 'insights', label: '🧠 AI Insights', },
              { id: 'crm', label: '👥 CRM Lookup', },
              { id: 'products', label: '🎫 Products', },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === tab.id
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </nav>

      {/* Content */}
      <main className="max-w-7xl mx-auto px-4 py-6">
        {error && (
          <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
            {error}
          </div>
        )}

        {/* Overview Tab */}
        {activeTab === 'overview' && (
          <div className="space-y-6">
            {/* Stats Grid */}
            <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
              {[
                { label: 'Total Bookings', value: stats?.total_bookings || 0, icon: '📋', color: 'blue' },
                { label: 'Activities', value: stats?.total_activities || 0, icon: '🎫', color: 'green' },
                { label: 'Products', value: stats?.total_products || 0, icon: '🏛️', color: 'purple' },
                { label: 'Customers', value: stats?.unique_customers || 0, icon: '👥', color: 'orange' },
                { label: 'Upcoming (30d)', value: stats?.upcoming_30_days || 0, icon: '📅', color: 'red' },
              ].map((stat) => (
                <div key={stat.label} className="bg-white rounded-lg shadow p-4">
                  <div className="flex items-center justify-between">
                    <span className="text-2xl">{stat.icon}</span>
                    <span className={`text-2xl font-bold text-${stat.color}-600`}>
                      {stat.value.toLocaleString()}
                    </span>
                  </div>
                  <p className="mt-2 text-sm text-gray-500">{stat.label}</p>
                </div>
              ))}
            </div>

            {/* Quick Actions */}
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-lg font-semibold mb-4">Quick Actions</h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <button
                  onClick={() => setActiveTab('config')}
                  className="p-4 border-2 border-dashed border-gray-300 rounded-lg hover:border-blue-500 hover:bg-blue-50 transition-colors text-left"
                >
                  <span className="text-2xl">⚙️</span>
                  <h3 className="mt-2 font-medium">Configure Bot</h3>
                  <p className="text-sm text-gray-500">Set what info the bot uses and how it responds</p>
                </button>
                <button
                  onClick={() => setActiveTab('insights')}
                  className="p-4 border-2 border-dashed border-gray-300 rounded-lg hover:border-blue-500 hover:bg-blue-50 transition-colors text-left"
                >
                  <span className="text-2xl">🧠</span>
                  <h3 className="mt-2 font-medium">View AI Insights</h3>
                  <p className="text-sm text-gray-500">See what AI found useful in your CRM data</p>
                </button>
                <button
                  onClick={() => setActiveTab('crm')}
                  className="p-4 border-2 border-dashed border-gray-300 rounded-lg hover:border-blue-500 hover:bg-blue-50 transition-colors text-left"
                >
                  <span className="text-2xl">👥</span>
                  <h3 className="mt-2 font-medium">Look Up Customer</h3>
                  <p className="text-sm text-gray-500">Search CRM data for a specific customer</p>
                </button>
              </div>
            </div>

            {/* Recent Insights Preview */}
            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold">Top AI Insights</h2>
                <button
                  onClick={() => setActiveTab('insights')}
                  className="text-sm text-blue-600 hover:underline"
                >
                  View all →
                </button>
              </div>
              <div className="space-y-3">
                {insights.slice(0, 5).map((insight, i) => (
                  <div key={i} className={`p-3 rounded-lg border ${getPriorityColor(insight.priority)}`}>
                    <div className="flex items-center gap-2">
                      <span>{getCategoryIcon(insight.category)}</span>
                      <span className="font-medium text-sm">{insight.title}</span>
                      <span className="text-xs opacity-70">({Math.round(insight.confidence * 100)}% confidence)</span>
                    </div>
                    <p className="text-sm mt-1 opacity-80">{insight.description}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Config Tab */}
        {activeTab === 'config' && config && (
          <div className="space-y-6">
            {/* Bot Features */}
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-lg font-semibold mb-4">🤖 Bot Features</h2>
              <p className="text-sm text-gray-500 mb-4">Toggle what the customer care bot can do</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {Object.entries(config.features).map(([key, enabled]) => (
                  <label key={key} className="flex items-center justify-between p-3 border rounded-lg hover:bg-gray-50 cursor-pointer">
                    <span className="text-sm font-medium capitalize">
                      {key.replace(/_/g, ' ')}
                    </span>
                    <input
                      type="checkbox"
                      checked={enabled}
                      onChange={(e) => updateFeature(key, e.target.checked)}
                      className="w-5 h-5 text-blue-600 rounded"
                    />
                  </label>
                ))}
              </div>
            </div>

            {/* Bot Persona */}
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-lg font-semibold mb-4">🎭 Bot Persona</h2>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Bot Name</label>
                  <input
                    type="text"
                    value={config.persona.name}
                    readOnly
                    className="w-full p-2 border rounded-lg bg-gray-50"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Tone</label>
                  <input
                    type="text"
                    value={config.persona.tone}
                    readOnly
                    className="w-full p-2 border rounded-lg bg-gray-50"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Response Length</label>
                  <select className="w-full p-2 border rounded-lg">
                    <option value="concise" selected={config.persona.response_length === 'concise'}>Concise</option>
                    <option value="detailed" selected={config.persona.response_length === 'detailed'}>Detailed</option>
                    <option value="adaptive" selected={config.persona.response_length === 'adaptive'}>Adaptive</option>
                  </select>
                </div>
              </div>
            </div>

            {/* AI Settings */}
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-lg font-semibold mb-4">🧠 AI Settings</h2>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Provider</label>
                  <input
                    type="text"
                    value={config.ai.provider}
                    readOnly
                    className="w-full p-2 border rounded-lg bg-gray-50"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Model</label>
                  <input
                    type="text"
                    value={config.ai.model}
                    readOnly
                    className="w-full p-2 border rounded-lg bg-gray-50"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Temperature: {config.ai.temperature}
                  </label>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.1"
                    value={config.ai.temperature}
                    className="w-full"
                  />
                  <div className="flex justify-between text-xs text-gray-500">
                    <span>Precise</span>
                    <span>Creative</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Insights Tab */}
        {activeTab === 'insights' && (
          <div className="space-y-6">
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-lg font-semibold mb-4">🧠 AI-Analyzed CRM Insights</h2>
              <p className="text-sm text-gray-500 mb-4">
                These insights were automatically extracted from your Google Sheets CRM data.
                AI filtered out noise and identified useful patterns.
              </p>

              {/* Filter by category */}
              <div className="flex gap-2 mb-4 flex-wrap">
                {['all', 'booking_pattern', 'customer_behavior', 'product_trend', 'revenue', 'operational'].map((cat) => (
                  <button
                    key={cat}
                    className="px-3 py-1 text-sm rounded-full border hover:bg-gray-50 capitalize"
                  >
                    {cat.replace(/_/g, ' ')}
                  </button>
                ))}
              </div>

              <div className="space-y-3">
                {insights.map((insight, i) => (
                  <div key={i} className={`p-4 rounded-lg border ${getPriorityColor(insight.priority)}`}>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-xl">{getCategoryIcon(insight.category)}</span>
                        <span className="font-semibold">{insight.title}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        {insight.action_required && (
                          <span className="px-2 py-0.5 bg-red-500 text-white text-xs rounded-full">Action Required</span>
                        )}
                        <span className="text-xs opacity-70">{Math.round(insight.confidence * 100)}%</span>
                      </div>
                    </div>
                    <p className="text-sm mt-2 opacity-80">{insight.description}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* CRM Lookup Tab */}
        {activeTab === 'crm' && (
          <div className="space-y-6">
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-lg font-semibold mb-4">👥 Customer Lookup</h2>
              <div className="flex gap-2 mb-4">
                <input
                  type="email"
                  value={customerEmail}
                  onChange={(e) => setCustomerEmail(e.target.value)}
                  placeholder="Enter customer email..."
                  className="flex-1 p-2 border rounded-lg"
                  onKeyDown={(e) => e.key === 'Enter' && lookupCustomer()}
                />
                <button
                  onClick={lookupCustomer}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                >
                  Search
                </button>
              </div>

              {customerData && (
                <div className="space-y-4">
                  {customerData.found ? (
                    <>
                      <div className="p-4 bg-blue-50 rounded-lg">
                        <h3 className="font-semibold text-lg">{customerData.name}</h3>
                        <div className="flex gap-2 mt-2 flex-wrap">
                          {customerData.tags?.map((tag: string, i: number) => (
                            <span key={i} className="px-2 py-1 bg-white rounded-full text-xs border">
                              {tag}
                            </span>
                          ))}
                        </div>
                        <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                          <div>
                            <span className="text-gray-500">Bookings:</span>
                            <span className="ml-1 font-medium">{customerData.total_bookings}</span>
                          </div>
                          <div>
                            <span className="text-gray-500">Frequency:</span>
                            <span className="ml-1 font-medium capitalize">{customerData.booking_frequency}</span>
                          </div>
                          <div>
                            <span className="text-gray-500">Group Size:</span>
                            <span className="ml-1 font-medium">{customerData.preferred_group_size || 'N/A'}</span>
                          </div>
                          <div>
                            <span className="text-gray-500">Language:</span>
                            <span className="ml-1 font-medium">{customerData.language || 'N/A'}</span>
                          </div>
                        </div>
                      </div>

                      {customerData.upcoming_bookings?.length > 0 && (
                        <div>
                          <h4 className="font-semibold mb-2">Upcoming Bookings</h4>
                          <div className="space-y-2">
                            {customerData.upcoming_bookings.map((b: any, i: number) => (
                              <div key={i} className="p-3 border rounded-lg">
                                <div className="flex items-center justify-between">
                                  <div>
                                    <span className="font-medium">{b.date} at {b.time}</span>
                                    <span className="ml-2 text-sm text-gray-500">({b.participants} pax)</span>
                                  </div>
                                  <span className={`px-2 py-0.5 rounded text-xs ${
                                    b.status === 'CONFIRMED' ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'
                                  }`}>
                                    {b.status}
                                  </span>
                                </div>
                                <p className="text-sm text-gray-600 mt-1">{b.product}</p>
                                {b.is_vatican && <span className="text-xs text-blue-600">🏛️ Vatican</span>}
                                {b.is_colosseum && <span className="text-xs text-red-600">🏟️ Colosseum</span>}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {customerData.favorite_products?.length > 0 && (
                        <div>
                          <h4 className="font-semibold mb-2">Favorite Products</h4>
                          <ul className="text-sm text-gray-600 space-y-1">
                            {customerData.favorite_products.map((p: string, i: number) => (
                              <li key={i}>• {p}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="p-4 bg-yellow-50 rounded-lg text-yellow-800">
                      No customer found with this email.
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Products Tab */}
        {activeTab === 'products' && (
          <div className="space-y-6">
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-lg font-semibold mb-4">🎫 Product Catalog</h2>
              <p className="text-sm text-gray-500 mb-4">
                These are the tours and experiences from your CRM. The bot uses these to make recommendations.
              </p>
              <p className="text-sm text-gray-500">
                Loading products from Google Sheets...
              </p>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
