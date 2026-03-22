import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { auth as authApi } from './api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      const stored = localStorage.getItem('user');
      return stored ? JSON.parse(stored) : null;
    } catch {
      return null;
    }
  });
  const [loading, setLoading] = useState(true);

  // Keep React state in sync when api.js forces a session clear (401 refresh failure).
  useEffect(() => {
    const handleLogout = () => {
      setUser(null);
    };
    window.addEventListener('auth:logout', handleLogout);
    return () => window.removeEventListener('auth:logout', handleLogout);
  }, []);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      setLoading(false);
      return;
    }

    const initSession = async () => {
      try {
        const u = await authApi.me();
        if (u) {
          setUser(u);
          localStorage.setItem('user', JSON.stringify(u));
          return;
        }
      } catch {
        // /me failed — try refreshing the token once before giving up
        try {
          const refreshed = await authApi.refresh();
          if (refreshed?.access_token) {
            localStorage.setItem('token', refreshed.access_token);
            if (refreshed.user) {
              setUser(refreshed.user);
              localStorage.setItem('user', JSON.stringify(refreshed.user));
              return;
            }
          }
        } catch {
          // Refresh also failed — session is truly invalid
        }
      }
      // Clear stale session
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      setUser(null);
    };

    initSession().finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email, password) => {
    const data = await authApi.login({ email, password });
    localStorage.setItem('token', data.access_token);
    localStorage.setItem('user', JSON.stringify(data.user));
    setUser(data.user);
    return data;
  }, []);

  const register = useCallback(async (body) => {
    const data = await authApi.register(body);
    localStorage.setItem('token', data.access_token);
    localStorage.setItem('user', JSON.stringify(data.user));
    setUser(data.user);
    return data;
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
