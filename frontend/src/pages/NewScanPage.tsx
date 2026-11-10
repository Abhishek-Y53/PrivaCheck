import { useEffect, useState, type FormEvent } from 'react';
import { ArrowLeft, ArrowRight, Globe, Info, LockKeyhole, ShieldCheck } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../lib/api';
import type { FrameworkOption } from '../types/api';

function validateWebsite(value: string): string | null {
  try {
    const url = new URL(value.trim());
    if (!['http:', 'https:'].includes(url.protocol)) return 'Only HTTP and HTTPS websites are supported.';
    if (!url.hostname.includes('.') || url.hostname === 'localhost') return 'Enter a public website hostname.';
    if (url.username || url.password) return 'URLs containing credentials are not allowed.';
    return null;
  } catch {
    return 'Enter a valid URL, including https://';
  }
}

export function NewScanPage() {
  const navigate = useNavigate();
  const [website, setWebsite] = useState('https://');
  const [framework, setFramework] = useState('gdpr');
  const [frameworks, setFrameworks] = useState<FrameworkOption[]>([]);
  const [loadingFrameworks, setLoadingFrameworks] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    api.listFrameworks()
      .then((items) => { if (active) {
        setFrameworks(items);
        setFramework(current => items.some(item => item.id === current && item.enabled)
          ? current : (items.find(item => item.enabled)?.id ?? ''));
      } })
      .catch((err: Error) => { if (active) setError(err.message); })
      .finally(() => { if (active) setLoadingFrameworks(false); });
    return () => { active = false; };
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const validationError = validateWebsite(website);
    if (validationError) {
      setError(validationError);
      return;
    }
    if (!frameworks.some((item) => item.id === framework && item.enabled)) {
      setError('Select an enabled compliance framework.');
      return;
    }

    setSubmitting(true);
    setError('');
    try {
      const created = await api.createScan({
        website: new URL(website.trim()).toString(),
        framework,
      });
      navigate(`/scans/${created.scan_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to create scan.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page-stack narrow-page">
      <Link to="/" className="back-link"><ArrowLeft size={15} /> Back to overview</Link>
      <section className="page-heading"><div className="eyebrow">NEW ASSESSMENT</div><h1>Scan a website</h1><p className="page-subtitle">Configure a technical compliance assessment. PrivaCheck will process it in the background.</p></section>
      <form className="panel scan-form" onSubmit={handleSubmit}>
        <div className="form-section-heading"><div className="form-section-icon"><Globe size={18} /></div><div><h2>Target website</h2><p>Enter the public URL you want PrivaCheck to inspect.</p></div></div>
        <label className="field-label" htmlFor="website">Website URL</label>
        <div className="input-with-icon"><Globe size={17} /><input id="website" type="url" value={website} onChange={(event) => setWebsite(event.target.value)} placeholder="https://example.com" autoComplete="url" required /></div>
        <div className="field-hint">Use a public website that you are authorized to assess. Private, local and restricted network destinations are rejected by the backend.</div>
        <div className="form-divider" />
        <div className="form-section-heading"><div className="form-section-icon"><ShieldCheck size={18} /></div><div><h2>Compliance framework</h2><p>Select the configured rule set for this assessment.</p></div></div>
        <label className="field-label" htmlFor="framework">Framework</label>
        <select id="framework" className="select-input" value={framework} onChange={(event) => setFramework(event.target.value)} disabled={loadingFrameworks || frameworks.length === 0}>
          {frameworks.map((item) => <option key={item.id} value={item.id} disabled={!item.enabled}>{item.name}{item.enabled ? '' : ' (coming soon)'}</option>)}
        </select>
        {frameworks.map((item) => item.id === framework && <div className="field-hint" key={item.id}>{item.description}</div>)}
        <div className="form-divider" />
        <div className="scan-safety-note"><LockKeyhole size={16} /><span><strong>Safe scanning:</strong> PrivaCheck validates public destinations and applies request controls. Only scan websites you have permission to assess.</span></div>
        {error && <div className="alert alert-error">{error}</div>}
        <div className="form-actions"><Link to="/" className="button button-secondary">Cancel</Link><button type="submit" className="button button-primary" disabled={submitting || loadingFrameworks || frameworks.length === 0}>{submitting ? 'Submitting scan…' : 'Submit scan'} <ArrowRight size={16} /></button></div>
      </form>
      <div className="subtle-note"><Info size={14} /> The API returns a scan ID immediately. You can follow crawler progress and open the persisted report when processing finishes.</div>
    </div>
  );
}
