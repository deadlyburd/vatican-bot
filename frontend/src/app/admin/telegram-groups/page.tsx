'use client';

// Force dynamic rendering
export const dynamic = 'force-dynamic';

export default function TelegramGroupsAdmin() {
  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-3xl font-bold text-gray-900">Telegram Groups Management</h1>
        <p className="text-gray-600 mt-2">Admin dashboard for managing Telegram groups</p>
        
        <div className="mt-8 bg-white p-6 rounded-lg shadow">
          <h2 className="text-xl font-semibold mb-4">Test Page</h2>
          <p>If you can see this, the routing is working!</p>
          <p>API Base URL: {process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}</p>
        </div>
      </div>
    </div>
  );
}
