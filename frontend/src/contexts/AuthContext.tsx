import { createContext, useContext, useState, useEffect } from 'react';
import type { ReactNode } from 'react';

interface AuthContextType {
  isAuthenticated: boolean;
  token: string | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<boolean>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const API_BASE = '/api';

async function tryAccessSso(): Promise<string | null> {
  try {
    const response = await fetch(`${API_BASE}/auth/access-sso`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
    });
    if (!response.ok) {
      return null;
    }
    const data = await response.json();
    return typeof data.access_token === 'string' ? data.access_token : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    const applyToken = (accessToken: string) => {
      setToken(accessToken);
      setIsAuthenticated(true);
      localStorage.setItem('admin_token', accessToken);
    };

    const init = async () => {
      const storedToken = localStorage.getItem('admin_token');
      if (storedToken) {
        if (!cancelled) {
          setToken(storedToken);
          setIsAuthenticated(true);
          setLoading(false);
        }
        return;
      }

      // Behind Cloudflare Access: mint Arquivo JWT without password form.
      const ssoToken = await tryAccessSso();
      if (!cancelled) {
        if (ssoToken) {
          applyToken(ssoToken);
        } else {
          setIsAuthenticated(false);
          setToken(null);
        }
        setLoading(false);
      }
    };

    void init();

    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === 'admin_token') {
        const currentToken = localStorage.getItem('admin_token');
        if (!currentToken) {
          setIsAuthenticated(false);
          setToken(null);
        } else {
          setToken(currentToken);
          setIsAuthenticated(true);
        }
      }
    };

    const handleTokenCleared = () => {
      const currentToken = localStorage.getItem('admin_token');
      if (!currentToken) {
        setIsAuthenticated(false);
        setToken(null);
      }
    };

    window.addEventListener('storage', handleStorageChange);
    window.addEventListener('auth-token-cleared', handleTokenCleared);
    return () => {
      cancelled = true;
      window.removeEventListener('storage', handleStorageChange);
      window.removeEventListener('auth-token-cleared', handleTokenCleared);
    };
  }, []);

  const login = async (username: string, password: string): Promise<boolean> => {
    try {
      const response = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username, password }),
      });

      if (!response.ok) {
        return false;
      }

      const data = await response.json();
      const accessToken = data.access_token;

      setToken(accessToken);
      setIsAuthenticated(true);
      localStorage.setItem('admin_token', accessToken);

      return true;
    } catch (error) {
      console.error('Login error:', error);
      return false;
    }
  };

  const logout = () => {
    setIsAuthenticated(false);
    setToken(null);
    localStorage.removeItem('admin_token');
  };

  return (
    <AuthContext.Provider value={{ isAuthenticated, token, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
