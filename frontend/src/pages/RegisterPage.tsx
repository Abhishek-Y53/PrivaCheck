import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { LockKeyhole, Mail, UserPlus } from 'lucide-react';
import { AuthPageFrame } from '../components/AuthPageFrame';
import { useAuth } from '../auth/AuthContext';

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    if (password !== confirmPassword) {
      setError('The passwords do not match.');
      return;
    }
    if (password.length < 12) {
      setError('Use a password containing at least 12 characters.');
      return;
    }

    setIsSubmitting(true);
    try {
      await register(email.trim(), password);
      navigate('/', { replace: true });
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Unable to create your account.');
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthPageFrame
      eyebrow="CREATE AN ACCOUNT"
      title="Set up your workspace"
      subtitle="Create an account to keep your scans and reports private to you."
    >
      {error && <div className="auth-alert" role="alert">{error}</div>}
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
              name="new-password"
              autoComplete="new-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              minLength={12}
              maxLength={128}
              placeholder="At least 12 characters"
              required
            />
          </span>
        </label>
        <label className="auth-field">
          <span>Confirm password</span>
          <span className="auth-input-wrap"><LockKeyhole size={16} aria-hidden="true" />
            <input
              type="password"
              name="confirm-password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              minLength={12}
              maxLength={128}
              placeholder="Re-enter your password"
              required
            />
          </span>
        </label>
        <p className="auth-password-note">Passwords must contain at least 12 characters. Your password is never stored in browser storage.</p>
        <button className="button button-primary auth-submit" type="submit" disabled={isSubmitting}>
          <UserPlus size={16} /> {isSubmitting ? 'Creating account…' : 'Create account'}
        </button>
      </form>
      <p className="auth-switch">Already have an account? <Link to="/login">Sign in</Link></p>
    </AuthPageFrame>
  );
}
