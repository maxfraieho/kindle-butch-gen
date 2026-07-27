/**
 * Unified API Client for Vydra (kindle-butch-gen) Flask Backend.
 * Handles session authentication, JSON error parsing, and type-safe responses.
 */

export interface ApiResponse<T = any> {
  status: string;
  message?: string;
  data?: T;
  [key: string]: any;
}

export interface Book {
  slug: string;
  title: string;
  authors?: string;
  lang?: string;
  status?: string;
  progress?: number;
  current_stage?: string;
  pdf_pages?: number;
  total_chunks?: number;
  created_at?: string;
  output_files?: string[];
  [key: string]: any;
}

export async function apiFetch<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const defaultHeaders: HeadersInit = {
    'Accept': 'application/json',
  };

  if (!(options.body instanceof FormData)) {
    defaultHeaders['Content-Type'] = 'application/json';
  }

  const response = await fetch(path, {
    ...options,
    credentials: 'same-origin', // Send session cookies
    headers: {
      ...defaultHeaders,
      ...options.headers,
    },
  });

  if (response.status === 401) {
    // If request requires auth and fails
    if (!window.location.pathname.startsWith('/login')) {
      window.location.href = '/login';
    }
    throw new Error('Unauthorized');
  }

  const data = await response.json().catch(() => ({ status: 'error', message: 'Failed to parse JSON response' }));

  if (!response.ok) {
    throw new Error(data.message || `HTTP error ${response.status}`);
  }

  return data as T;
}
