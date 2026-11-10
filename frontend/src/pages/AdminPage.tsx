import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { ClipboardList, FileClock, LockKeyhole, Search, ShieldCheck, Users } from 'lucide-react';
import { adminApi } from '../lib/api';
import type { AdminAuditList, AdminScanList, AdminUser, AdminUserList, AdmissionEntry, AdmissionList } from '../types/admin';
import { useAuth } from '../auth/AuthContext';
import { formatDate } from '../lib/format';

type Tab = 'users' | 'access' | 'scans' | 'audit';
const PAGE_SIZE = 50;

function Pager({ offset, total, onChange }: { offset: number; total: number; onChange: (offset: number) => void }) {
  return (
    <div className="admin-pager">
      <span>{total === 0 ? 'No records' : `${offset + 1}–${Math.min(offset + PAGE_SIZE, total)} of ${total}`}</span>
      <button className="button button-secondary button-small" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - PAGE_SIZE))}>Previous</button>
      <button className="button button-secondary button-small" disabled={offset + PAGE_SIZE >= total} onClick={() => onChange(offset + PAGE_SIZE)}>Next</button>
    </div>
  );
}

export function AdminPage() {
  const { user } = useAuth();
  const [tab, setTab] = useState<Tab>('users');
  const [users, setUsers] = useState<AdminUserList | null>(null);
  const [access, setAccess] = useState<AdmissionList | null>(null);
  const [scans, setScans] = useState<AdminScanList | null>(null);
  const [audit, setAudit] = useState<AdminAuditList | null>(null);
  const [query, setQuery] = useState('');
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [selector, setSelector] = useState<'emails' | 'domains'>('emails');
  const [selectorValue, setSelectorValue] = useState('');

  const load = useCallback(async (section: Tab, page: number, filter: string) => {
    setLoading(true);
    setError('');
    try {
      if (section === 'users') setUsers(await adminApi.listUsers(filter, page, PAGE_SIZE));
      if (section === 'access') setAccess(await adminApi.listAllowlist());
      if (section === 'scans') setScans(await adminApi.listScans(page, PAGE_SIZE));
      if (section === 'audit') setAudit(await adminApi.listAudit(page, PAGE_SIZE));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to retrieve administrator data.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(tab, offset, query); }, [tab, offset, query, load]);

  function changeTab(next: Tab) {
    setTab(next);
    setOffset(0);
    setError('');
    setNotice('');
  }

  async function perform(work: () => Promise<unknown>, message: string) {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await work();
      setNotice(message);
      await load(tab, offset, query);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to save administrator change.');
    } finally {
      setBusy(false);
    }
  }

  function changeRole(target: AdminUser) {
    const next = target.role === 'ADMIN' ? 'USER' : 'ADMIN';
    if (!window.confirm(`${next === 'ADMIN' ? 'Promote' : 'Demote'} ${target.email} to ${next}? Their existing sessions will be revoked.`)) return;
    void perform(() => adminApi.changeRole(target.id, next), `Role updated for ${target.email}.`);
  }

  function changeStatus(target: AdminUser) {
    const next = !target.is_active;
    if (!window.confirm(`${next ? 'Restore' : 'Suspend'} ${target.email}? Their current sessions will be revoked.`)) return;
    void perform(() => adminApi.changeStatus(target.id, next), `Account updated for ${target.email}.`);
  }

  function addAdmission(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const value = selectorValue.trim();
    if (!value) return;
    void perform(async () => {
      await adminApi.setAdmission(selector, value, true);
      setSelectorValue('');
    }, `Admission enabled for ${value}.`);
  }

  function toggleAdmission(kind: 'emails' | 'domains', entry: AdmissionEntry) {
    if (!window.confirm(`${entry.is_active ? 'Disable' : 'Enable'} ${entry.value}? Admission changes take effect at the next protected request.`)) return;
    void perform(() => adminApi.setAdmission(kind, entry.value, !entry.is_active), `Admission updated for ${entry.value}.`);
  }

  return (
    <div className="page-stack">
      <section className="page-heading">
        <div className="eyebrow">SECURE ADMINISTRATION</div>
        <h1>Platform administration</h1>
        <p className="page-subtitle">Manage approved accounts, access policies, user reports and audited administrative actions.</p>
      </section>
      <nav aria-label="Administration sections" className="admin-tabs">
        {([
          ['users', 'Users', Users],
          ['access', 'Platform access', LockKeyhole],
          ['scans', 'All scans', ClipboardList],
          ['audit', 'Audit history', FileClock],
        ] as const).map(([key, label, Icon]) => (
          <button key={key} type="button" className={`admin-tab ${tab === key ? 'active' : ''}`} onClick={() => changeTab(key)} aria-current={tab === key ? 'page' : undefined}>
            <Icon size={15} />{label}
          </button>
        ))}
      </nav>
      {notice && <div className="admin-alert-success" role="status">{notice}</div>}
      {error && <div className="alert alert-error" role="alert">{error}</div>}
      <section className="panel admin-panel">
        {tab === 'users' && <>
          <div className="admin-panel-heading"><h2>User management</h2><span>Promotions and suspensions revoke the user's sessions.</span></div>
          <label className="search-field admin-search"><Search size={16} /><input aria-label="Find accounts by email" placeholder="Filter email" value={query} onChange={e => { setQuery(e.target.value); setOffset(0); }} /></label>
          <div className="table-wrap"><table className="data-table">
            <thead><tr><th>Account</th><th>Role</th><th>State</th><th>Google</th><th>Actions</th></tr></thead>
            <tbody>{users?.items.map(account => <tr key={account.id}>
              <td><strong className="admin-cell-strong">{account.email}</strong><div className="table-muted">{account.display_name || formatDate(account.created_at)}</div></td>
              <td><span className="framework-chip">{account.role}</span></td>
              <td><span className={account.is_active ? 'admin-state-active' : 'admin-state-disabled'}>{account.is_active ? 'Active' : 'Suspended'}</span></td>
              <td className="table-muted">{account.google_linked ? 'Linked' : 'Legacy only'}</td>
              <td><div className="admin-actions">
                <button className="button button-secondary button-small" disabled={busy || user?.id === account.id || !account.google_linked || !account.is_active} onClick={() => changeRole(account)}>{account.role === 'ADMIN' ? 'Demote' : 'Promote'}</button>
                <button className="button button-secondary button-small" disabled={busy || user?.id === account.id} onClick={() => changeStatus(account)}>{account.is_active ? 'Suspend' : 'Restore'}</button>
              </div></td>
            </tr>)}</tbody>
          </table></div>
          {!loading && users?.items.length === 0 && <p className="admin-empty">No matching accounts.</p>}
          {users && <Pager offset={offset} total={users.total} onChange={setOffset} />}
        </>}
        {tab === 'access' && <>
          <div className="admin-panel-heading"><h2>Admission rules</h2><span>Exact Google email OR verified Workspace domain. ADMIN accounts bypass normal admission rules.</span></div>
          <form className="admin-add-form" onSubmit={addAdmission}>
            <select aria-label="Admission rule type" className="select-input" value={selector} onChange={e => setSelector(e.target.value as typeof selector)}>
              <option value="emails">Exact email</option><option value="domains">Workspace domain</option>
            </select>
            <input aria-label="Admission rule value" className="select-input" value={selectorValue} onChange={e => setSelectorValue(e.target.value)} placeholder={selector === 'emails' ? 'student@gmail.com' : 'iiitg.ac.in'} required maxLength={320}/>
            <button className="button button-primary" disabled={busy} type="submit">Allow</button>
          </form>
          {(['domains', 'emails'] as const).map(kind => <div key={kind} className="admin-list-section">
            <h3>{kind === 'domains' ? 'Workspace domains' : 'Individual Google emails'}</h3>
            <div className="table-wrap"><table className="data-table">
              <thead><tr><th>Exact selector</th><th>Admission</th><th>Action</th></tr></thead>
              <tbody>{access?.[kind].map(entry => <tr key={entry.id}>
                <td className="admin-cell-strong">{entry.value}</td>
                <td><span className={entry.is_active ? 'admin-state-active' : 'admin-state-disabled'}>{entry.is_active ? 'Allowed' : 'Disabled'}</span></td>
                <td><button className="button button-secondary button-small" disabled={busy} onClick={() => toggleAdmission(kind, entry)}>{entry.is_active ? 'Disable' : 'Enable'}</button></td>
              </tr>)}</tbody>
            </table></div>
            {!loading && access?.[kind].length === 0 && <p className="admin-empty">No {kind} configured.</p>}
          </div>)}
        </>}
        {tab === 'scans' && <>
          <div className="admin-panel-heading"><h2>Scans across accounts</h2><span>Access to another user's completed report is audited.</span></div>
          <div className="table-wrap"><table className="data-table">
            <thead><tr><th>Website</th><th>Owner</th><th>Framework</th><th>Status</th><th>Created</th><th>Report</th></tr></thead>
            <tbody>{scans?.items.map(({ scan, owner_email }) => <tr key={scan.scan_id}>
              <td className="admin-cell-strong">{scan.website}</td>
              <td className="table-muted">{owner_email ?? 'Legacy / unowned'}</td>
              <td><span className="framework-chip">{scan.framework.toUpperCase()}</span></td>
              <td className="table-muted">{scan.lifecycle_status}</td>
              <td className="table-muted">{formatDate(scan.created_at)}</td>
              <td><Link className="text-link" to={`/admin/scans/${scan.scan_id}`}>Open</Link></td>
            </tr>)}</tbody>
          </table></div>
          {!loading && scans?.items.length === 0 && <p className="admin-empty">No scans yet.</p>}
          {scans && <Pager offset={offset} total={scans.total} onChange={setOffset} />}
        </>}
        {tab === 'audit' && <>
          <div className="admin-panel-heading"><h2>Administration audit trail</h2><span>Append-only records of policy changes, account management and elevated report access.</span></div>
          <div className="table-wrap"><table className="data-table">
            <thead><tr><th>Time</th><th>Action</th><th>Target</th><th>Actor user ID</th><th>Change</th></tr></thead>
            <tbody>{audit?.items.map(event => <tr key={event.id}>
              <td className="table-muted">{formatDate(event.created_at)}</td>
              <td className="admin-cell-strong">{event.action}</td>
              <td className="table-muted">{event.target_type}: {event.target_id}</td>
              <td className="table-muted">{event.actor_user_id.slice(0, 8)}…</td>
              <td className="table-muted"><span title={JSON.stringify({ before: event.before_data, after: event.after_data })}>{JSON.stringify(event.after_data ?? {})}</span></td>
            </tr>)}</tbody>
          </table></div>
          {!loading && audit?.items.length === 0 && <p className="admin-empty">No administrator events yet.</p>}
          {audit && <Pager offset={offset} total={audit.total} onChange={setOffset} />}
        </>}
        {loading && <div className="loading-row">Loading {tab}…</div>}
      </section>
      <p className="admin-security-note"><ShieldCheck size={16} /> Sensitive changes require a Google sign-in within the last 30 minutes. If you see a reauthentication error, sign out and sign in again. User reports remain confidential and are not legal certifications.</p>
    </div>
  );
}
