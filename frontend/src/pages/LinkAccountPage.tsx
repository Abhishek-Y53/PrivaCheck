import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { LockKeyhole } from 'lucide-react';
import { AuthPageFrame } from '../components/AuthPageFrame';
import { useAuth } from '../auth/AuthContext';

export function LinkAccountPage() {
  const { linkLegacyAccount } = useAuth();
  const navigate = useNavigate();
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    setPending(true);
    try {
      await linkLegacyAccount(password);
      setPassword('');
      navigate('/', { replace: true });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Account linking failed. Please try Google Sign-In again.');
      setPassword('');
    } finally {
      setPending(false);
    }
  }

  return (
    <AuthPageFrame
      eyebrow="ONE-TIME ACCOUNT MIGRATION"
      title="Preserve your existing scans"
      subtitle="A PrivaCheck account already uses this email. Confirm its previous password to securely link it to Google and retain your reports."
    >
      {error && <div className="auth-alert" role="alert">{error}</div>}
      <form className="auth-form" onSubmit={handleSubmit}>
        <label className="auth-field">
          <span>Your previous PrivaCheck password</span>
          <span className="auth-input-wrap"><LockKeyhole size={16} aria-hidden="true" />
            <input type="password" autoComplete="current-password" value={password}
              onChange={(event) => setPassword(event.target.value)} minLength={1} maxLength={128} required />
          </span>
        </label>
        <button className="button button-primary auth-submit" disabled={pending} type="submit">
          {pending ? 'Linking…' : 'Link existing account'}
        </button>
      </form>
      <p className="auth-switch">Forgot the previous password? Ask the administrator for controlled account recovery. We will not link accounts by email alone.</p>
    </AuthPageFrame>
  );
}
