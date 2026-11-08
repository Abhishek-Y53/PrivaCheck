import { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import {
  Activity,
  ArrowUpRight,
  ClipboardList,
  LayoutDashboard,
  LogOut,
  Plus,
  ShieldCheck,
} from 'lucide-react';
import { useAuth } from '../auth/AuthContext';

export function AppShell() {
  const mockMode = import.meta.env.VITE_USE_MOCK_DATA === 'true';
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [logoutError, setLogoutError] = useState('');
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  async function handleLogout() {
    setLogoutError('');
    setIsLoggingOut(true);
    try {
      await logout();
      navigate('/login', { replace: true });
    } catch (error) {
      setLogoutError(error instanceof Error ? error.message : 'Unable to sign out. Please retry.');
    } finally {
      setIsLoggingOut(false);
    }
  }

  const avatarLabel = user?.email.trim().charAt(0).toUpperCase() || 'D';

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup">
          <div className="brand-mark"><ShieldCheck size={21} strokeWidth={2.2} /></div>
          <div><div className="brand-name">PrivaCheck</div><div className="brand-caption">COMPLIANCE WORKSPACE</div></div>
        </div>
        <div className="sidebar-section-label">WORKSPACE</div>
        <nav className="side-nav">
          <NavLink to="/" end className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}><LayoutDashboard size={17} />Overview</NavLink>
          <NavLink to="/scans/new" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}><Plus size={17} />New scan</NavLink>
          <NavLink to="/scans" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}><ClipboardList size={17} />Scan history</NavLink>
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-status"><span className="online-dot" /><span>{mockMode ? 'Demo workspace' : 'Authenticated workspace'}</span></div>
          <div className="sidebar-version">PrivaCheck <span>v0.1.0</span></div>
        </div>
      </aside>

      <main className="main-column">
        <header className="topbar">
          <div className="breadcrumb"><span>Workspace</span><span className="breadcrumb-separator">/</span><strong>Assessment platform</strong></div>
          <div className="topbar-right">
            <span className="environment-pill"><Activity size={13} /> {mockMode ? 'Demo environment' : 'Connected environment'}</span>
            {user && <span className="topbar-user-email" title={user.email}>{user.email}</span>}
            {user && (
              <button
                type="button"
                className="logout-button"
                onClick={handleLogout}
                disabled={isLoggingOut}
                aria-label="Sign out"
              >
                <LogOut size={14} /> <span>{isLoggingOut ? 'Signing out…' : 'Sign out'}</span>
              </button>
            )}
            <div className="avatar" title={user?.email ?? 'Demo user'}>{avatarLabel}</div>
          </div>
        </header>
        {logoutError && <div className="logout-error" role="alert">{logoutError}</div>}
        {mockMode && <div className="demo-notice"><span className="demo-notice-dot" /> Demo mode is active. Scans and reports use sample data, not live website assessments. <a href="https://github.com/Abhishek-Y53/PrivaCheck" target="_blank" rel="noreferrer">Project repository <ArrowUpRight size={12} /></a></div>}
        <div className="page-content"><Outlet /></div>
        <footer className="app-footer"><span>PrivaCheck · Technical website assessment</span><span>Automated findings are indicators, not legal advice.</span></footer>
      </main>
    </div>
  );
}
