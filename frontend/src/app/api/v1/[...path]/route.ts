import { NextRequest, NextResponse } from 'next/server';

// Backend URL is set via BACKEND_URL env var in Vercel (server-side only, not exposed to browser)
// Falls back to the direct IP for local dev
const BACKEND_URL = process.env.BACKEND_URL || 'http://151.25.69.162:8000';

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  const params = await context.params;
  return proxyRequest(request, params.path, 'GET');
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  const params = await context.params;
  return proxyRequest(request, params.path, 'POST');
}

export async function PUT(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  const params = await context.params;
  return proxyRequest(request, params.path, 'PUT');
}

export async function DELETE(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  const params = await context.params;
  return proxyRequest(request, params.path, 'DELETE');
}

export async function PATCH(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  const params = await context.params;
  return proxyRequest(request, params.path, 'PATCH');
}

async function proxyRequest(
  request: NextRequest,
  pathSegments: string[],
  method: string
) {
  try {
    // Join path segments and ensure trailing slash (deduplicate)
    const path = pathSegments.join('/').replace(/\/+$/, '');
    const url = `${BACKEND_URL}/api/v1/${path}/`;
    
    console.log(`[Proxy] ${method} ${url}`);
    
    // Get request body for POST/PUT/PATCH
    let body = undefined;
    if (['POST', 'PUT', 'PATCH'].includes(method)) {
      try {
        body = await request.text();
        console.log(`[Proxy] Body:`, body);
      } catch (e) {
        console.log(`[Proxy] No body`);
      }
    }

    // Forward headers
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    };

    // Forward Authorization header if present
    const authHeader = request.headers.get('Authorization');
    if (authHeader) {
      headers['Authorization'] = authHeader;
      console.log(`[Proxy] Auth header present`);
    }

    // Make request to backend
    console.log(`[Proxy] Fetching backend...`);
    const response = await fetch(url, {
      method,
      headers,
      body,
    });

    console.log(`[Proxy] Backend response: ${response.status}`);

    // Handle empty responses (204 No Content)
    if (response.status === 204) {
      return new NextResponse(null, { status: 204 });
    }

    // Get response data
    const data = await response.text();
    
    // Parse JSON if possible
    let jsonData;
    try {
      jsonData = data ? JSON.parse(data) : {};
    } catch {
      jsonData = { message: data };
    }

    // Return response with same status
    return NextResponse.json(jsonData, {
      status: response.status,
      headers: {
        'Content-Type': 'application/json',
      },
    });
  } catch (error) {
    console.error('[Proxy] Error:', error);
    return NextResponse.json(
      { error: 'Proxy request failed', details: String(error) },
      { status: 500 }
    );
  }
}
