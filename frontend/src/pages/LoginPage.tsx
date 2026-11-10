import { useLocation } from 'react-router-dom';
import { LogIn } from 'lucide-react';
import { AuthPageFrame } from '../components/AuthPageFrame';
import { useAuth } from '../auth/AuthContext';

const messages: Record<string, string> = {
  google_denied: 'Google Sign-In could not be completed. Please try again.',
  not_allowed: 'This Google account is not on the PrivaCheck access list.',
  temporarily_unavailable: 'Sign-In is temporarily unavailable. Please try again later.',
};

export function LoginPage() {
  const { beginGoogleSignIn, initializationError } = useAuth();
  const location = useLocation();
  const errorCode = new URLSearchParams(location.search).get('error') ?? '';
  const error = messages[errorCode] ?? initializationError;
  return (
    <AuthPageFrame
      eyebrow="SECURE ACCOUNT ACCESS"
      title="Welcome to PrivaCheck"
      subtitle="Sign in with a Google account approved by your PrivaCheck administrator."
    >
      {error && <div className="auth-alert" role="alert">{error}</div>}
      <button className="button button-primary auth-submit" type="button" onClick={beginGoogleSignIn}>
        <LogIn size={16} /> Continue with Google
      </button>
      <p className="auth-switch">Your Workspace domain or email must be allowlisted. No separate PrivaCheck password is needed.</p>
    </AuthPageFrame>
  );
}
