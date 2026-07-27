import React, { createContext, useContext, useState, useEffect } from 'react';
import { apiFetch } from '../api/client';

interface AuthContextType {
  authenticated: boolean;
  user: string | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  authenticated: false,
  user: null,
  loading: true,
  login: async () => {},
  logout: async () => {},
});

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [authenticated, setAuthenticated] = useState<boolean>(false);
  const [user, setUser] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const checkAuth = async () => {
    try {
      const data = await apiFetch<{ authenticated: boolean; user?: string }>('/api/auth/check');
      setAuthenticated(data.authenticated);
      setUser(data.user || null);
    } catch {
      setAuthenticated(false);
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    checkAuth();
  }, []);

  const login = async (username: string, password: string) => {
    const data = await apiFetch<{ status: string; user: string; message?: string }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
    if (data.status === 'ok') {
      setAuthenticated(true);
      setUser(data.user);
    } else {
      throw new Error(data.message || 'Помилка авторизації');
    }
  };

  const logout = async () => {
    await apiFetch('/api/auth/logout', { method: 'POST' }).catch(() => {});
    setAuthenticated(false);
    setUser(null);
    window.location.href = '/login';
  };

  return (
    <AuthContext.Provider value={{ authenticated, user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
