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
  target_lang?: string;
  is_running?: boolean;
  stalled?: boolean;
  stalled_reason?: string | null;
  progress?: {
    marker_percent: number;
    translation_percent: number;
    stress_percent: number;
    tts_percent: number;
    overall_percent: number;
  };
  output_files?: string[];
  is_manga?: boolean;
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

  const contentType = response.headers.get('content-type') || '';
  let data: any;

  if (contentType.includes('application/json')) {
    try {
      data = await response.json();
    } catch (e) {
      const rawText = await response.text().catch(() => '');
      data = {
        status: 'error',
        message: `Невалідний JSON у відповіді (HTTP ${response.status}): ${rawText.slice(0, 200)}`,
      };
    }
  } else {
    const rawText = await response.text().catch(() => '');
    data = {
      status: 'error',
      message: `Сервер повернув не-JSON відповідь (HTTP ${response.status}): ${rawText.slice(0, 200)}`,
    };
  }

  if (!response.ok) {
    throw new Error(data.message || `HTTP помилка ${response.status}`);
  }

  return data as T;
}

