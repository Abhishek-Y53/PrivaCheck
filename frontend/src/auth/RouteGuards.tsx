import { Navigate, Outlet, useLocation } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useAuth } from './AuthContext';
import { api } from '../lib/api';

export function RequireAuth() {
  const { user, isLoading } = useAuth();
  const location = useLocation();

  if (api.isMockMode) return <Outlet />;
  if (isLoading) return <div className="auth-loading">Restoring your secure session…</div>;
  if (!user) {
    return <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />;
  }
  return <Outlet />;
}

interface GuestOnlyProps {
  children: ReactNode;
}

export function GuestOnly({ children }: GuestOnlyProps) {
  const { user, isLoading } = useAuth();
  if (api.isMockMode) return <Navigate to="/" replace />;
  if (isLoading) return <div className="auth-loading">Restoring your secure session…</div>;
  if (user) return <Navigate to="/" replace />;
  return children;
}
