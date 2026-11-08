import { useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { LockKeyhole, LogIn, Mail } from 'lucide-react';
import { AuthPageFrame } from '../components/AuthPageFrame';
import { useAuth } from '../auth/AuthContext';

export function LoginPage() {
  const { login, initializationError } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const destination = (location.state as { from?: unknown } | null)?.from;
  const returnTo = typeof destination === 'string' && destination.startsWith('/')
    && !destination.startsWith('//') ? destination : '/';

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    setIsSubmitting(true);
    try {
      await login(email.trim(), password);
      navigate(returnTo, { replace: true });
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Unable to sign in.');
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthPageFrame
      eyebrow="ACCOUNT ACCESS"
      title="Welcome back"
      subtitle="Sign in to access your website assessments and compliance reports."
    >
      {(initializationError || error) && (
        <div className="auth-alert" role="alert">{error || initializationError}</div>
      )}
      <form className="auth-form" onSubmit={handleSubmit}>
        <label className="auth-field">
          <span>Email address</span>
          <span className="auth-input-wrap"><Mail size={16} aria-hidden="true" />
            <input
              type="email"
              name="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              maxLength={320}
              placeholder="you@example.com"
              required
            />
          </span>
        </label>
        <label className="auth-field">
          <span>Password</span>
          <span className="auth-input-wrap"><LockKeyhole size={16} aria-hidden="true" />
            <input
              type="password"
              name="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              maxLength={128}
              placeholder="Enter your password"
              required
            />
          </span>
        </label>
        <button className="button button-primary auth-submit" type="submit" disabled={isSubmitting}>
          <LogIn size={16} /> {isSubmitting ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
      <p className="auth-switch">Don't have an account? <Link to="/register">Create an account</Link></p>
    </AuthPageFrame>
  );
}
