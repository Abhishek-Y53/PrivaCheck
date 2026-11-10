import { Navigate } from 'react-router-dom';
// Legacy password signup is deliberately disabled after Google-only OIDC.
export function RegisterPage() { return <Navigate to="/login" replace />; }
