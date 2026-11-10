import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './auth/AuthContext';
import { GuestOnly, RequireAdmin, RequireAuth } from './auth/RouteGuards';
import { AppShell } from './components/AppShell';
import { DashboardPage } from './pages/DashboardPage';
import { LoginPage } from './pages/LoginPage';
import { NewScanPage } from './pages/NewScanPage';
import { LinkAccountPage } from './pages/LinkAccountPage';
import { Navigate } from 'react-router-dom';
import { ScanHistoryPage } from './pages/ScanHistoryPage';
import { ScanDetailPage } from './pages/ScanDetailPage';
import { AdminPage } from './pages/AdminPage';
import { FrameworkManagementPage } from './pages/FrameworkManagementPage';

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<GuestOnly><LoginPage /></GuestOnly>} />
          <Route path="/register" element={<Navigate to="/login" replace />} />
          <Route path="/link-account" element={<GuestOnly><LinkAccountPage /></GuestOnly>} />
          <Route element={<RequireAuth />}>
            <Route element={<AppShell />}>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/scans/new" element={<NewScanPage />} />
              <Route path="/scans" element={<ScanHistoryPage />} />
              <Route path="/scans/:scanId" element={<ScanDetailPage />} />
              <Route element={<RequireAdmin />}>
                <Route path="/admin" element={<AdminPage />} />
                <Route path="/admin/frameworks" element={<FrameworkManagementPage />} />
                <Route path="/admin/scans/:scanId" element={<ScanDetailPage />} />
              </Route>
              <Route path="*" element={<div className="not-found"><h1>Page not found</h1><a href="/">Return to overview</a></div>} />
            </Route>
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
