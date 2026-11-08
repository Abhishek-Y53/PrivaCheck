import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type PropsWithChildren,
} from 'react';
import { api, authApi } from '../lib/api';
import type { AuthUser } from '../types/auth';

interface AuthContextValue {
  user: AuthUser | null;
  isLoading: boolean;
  initializationError: string;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: PropsWithChildren) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [initializationError, setInitializationError] = useState('');

  useEffect(() => {
    let active = true;

    const handleUnauthorized = () => {
      if (!active) return;
      setUser(null);
      setIsLoading(false);
    };

    window.addEventListener('privacheck:unauthorized', handleUnauthorized);

    if (api.isMockMode) {
      // Mock scans contain no private backend data. Authentication is intentionally
      // bypassed only when the developer explicitly enables local demo mode.
      setIsLoading(false);
    } else {
      authApi.initialize()
        .then((currentUser) => {
          if (active) {
            setUser(currentUser);
            setInitializationError('');
          }
        })
        .catch((error: unknown) => {
          if (active) {
            setUser(null);
            setInitializationError(
              error instanceof Error ? error.message : 'Unable to restore your session.',
            );
          }
        })
        .finally(() => {
          if (active) setIsLoading(false);
        });
    }

    return () => {
      active = false;
      window.removeEventListener('privacheck:unauthorized', handleUnauthorized);
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const authenticatedUser = await authApi.login(email, password);
    setUser(authenticatedUser);
    setInitializationError('');
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    const authenticatedUser = await authApi.register(email, password);
    setUser(authenticatedUser);
    setInitializationError('');
  }, []);

  const logout = useCallback(async () => {
    if (!api.isMockMode) await authApi.logout();
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    isLoading,
    initializationError,
    login,
    register,
    logout,
  }), [user, isLoading, initializationError, login, register, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider.');
  return context;
}
