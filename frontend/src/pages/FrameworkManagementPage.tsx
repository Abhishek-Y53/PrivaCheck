import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, CheckCircle, FileCode2, LockKeyhole, Plus, ShieldCheck } from 'lucide-react';
import { frameworkAdminApi } from '../lib/api';
import type { GovernedFramework } from '../types/frameworks';

const EMPTY_YAML = `rules:
  - id: CUSTOM-001
    name: Example privacy control
    description: Looks for a visible privacy control.
    category: PRIVACY
    source:
      observation: dom_button
      match: any
    evaluator: declarative
    conditions:
      any:
        - field: text
          operator: contains
          value: privacy
    result:
      pass: PASS
      fail: FAIL
    severity: MEDIUM
    recommendation: Provide clear privacy controls.
`;

function lines(value: string): string[] {
  return value.split(/[\r\n,]+/).map(x => x.trim()).filter(Boolean);
}

export function FrameworkManagementPage() {
  const [frameworks, setFrameworks] = useState<GovernedFramework[]>([]);
  const [selected, setSelected] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [newSlug, setNewSlug] = useState('');
  const [newName, setNewName] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [everyone, setEveryone] = useState(false);
  const [domains, setDomains] = useState('');
  const [emails, setEmails] = useState('');
  const [yamlText, setYamlText] = useState(EMPTY_YAML);
  const [draftId, setDraftId] = useState<string | null>(null);
  const [loadedVersion, setLoadedVersion] = useState<string | null>(null);
  const [yamlDirty, setYamlDirty] = useState(false);
  const [validation, setValidation] = useState('');
  const [sampleJson, setSampleJson] = useState('[{"category":"dom_button","data":{"text":"privacy settings"}}]');
  const [preview, setPreview] = useState<{id:string; name:string; status:string}[]>([]);

  const fw = frameworks.find(item => item.id === selected);
  const refresh = useCallback(async () => {
    const items = await frameworkAdminApi.list();
    setFrameworks(items);
    setSelected(previous => items.some(f => f.id === previous) ? previous : (items[0]?.id ?? ''));
  }, []);

  useEffect(() => {
    let active = true;
    frameworkAdminApi.list()
      .then(items => { if (active) { setFrameworks(items); setSelected(items[0]?.id ?? ''); } })
      .catch((err: Error) => { if (active) setError(err.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!fw) return;
    setName(fw.name);
    setDescription(fw.description);
    setEveryone(fw.access.everyone);
    setDomains(fw.access.domains.join('\n'));
    setEmails(fw.access.emails.join('\n'));
    setYamlText(EMPTY_YAML);
    setDraftId(null);
    setLoadedVersion(null);
    setYamlDirty(false);
    setValidation(''); setPreview([]);
  // Reinitialize editors only when framework selection changes, not on every save.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);

  async function perform(action: () => Promise<unknown>, notice: string) {
    setBusy(true); setMessage(''); setError('');
    try {
      await action();
      await refresh();
      setMessage(notice);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to save.');
    } finally {
      setBusy(false);
    }
  }

  function create(e: FormEvent) {
    e.preventDefault();
    const slug = newSlug.trim().toLowerCase();
    void perform(async () => {
      await frameworkAdminApi.create({slug, name: newName.trim(), description: ''});
      setNewSlug(''); setNewName(''); setSelected(slug);
    }, `Framework ${slug} created. Add a ruleset draft before publishing.`);
  }

  async function loadVersion(id: string) {
    if (!fw || (yamlDirty && !window.confirm('Discard unsaved YAML edits?'))) return;
    setBusy(true); setError('');
    try {
      const version = await frameworkAdminApi.version(fw.id, id);
      setYamlText(version.yaml_content);
      setLoadedVersion(version.id);
      setDraftId(version.status === 'DRAFT' ? version.id : null);
      setValidation(''); setYamlDirty(false);
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to load ruleset.'); }
    finally { setBusy(false); }
  }

  function startDraft() {
    if (yamlDirty && !window.confirm('Discard unsaved YAML edits?')) return;
    setDraftId(null); setLoadedVersion(null); setYamlText(EMPTY_YAML); setYamlDirty(false); setValidation(''); setPreview([]);
  }

  async function validate() {
    await perform(async () => {
      const result = await frameworkAdminApi.validate(yamlText);
      setValidation(`${result.rule_count} valid declarative rules`);
    }, 'YAML and rule schema are valid.');
  }

  async function testSample() {
    await perform(async () => {
      const parsed: unknown = JSON.parse(sampleJson);
      if (!Array.isArray(parsed) || parsed.length === 0) throw new Error('Provide a JSON array of synthetic observations.');
      const result = await frameworkAdminApi.preview(yamlText, parsed);
      setPreview(result.results);
    }, 'Synthetic sample evaluation completed. This does not confirm real compliance.');
  }

  async function saveDraft() {
    if (!fw) return;
    await perform(async () => {
      const result = await frameworkAdminApi.saveDraft(fw.id, yamlText, draftId);
      setDraftId(result.id);
      setLoadedVersion(result.id);
      setYamlDirty(false);
      setValidation(`${result.rule_count} validated rules`);
    }, 'Draft saved. Published versions remain unchanged.');
  }

  async function publishDraft() {
    if (!fw || !draftId) return;
    if (!window.confirm('Publish this immutable ruleset? It will apply to NEW scans. Existing queued scans remain pinned to their original versions.')) return;
    await perform(async () => {
      await frameworkAdminApi.publish(fw.id, draftId);
      setDraftId(null);
      setYamlDirty(false);
    }, 'New ruleset version published.');
  }

  return (
    <div className="page-stack framework-management">
      <Link to="/admin" className="back-link"><ArrowLeft size={15}/> Back to administration</Link>
      <section className="page-heading"><div className="eyebrow">FRAMEWORK GOVERNANCE</div><h1>Compliance frameworks</h1>
        <p className="page-subtitle">Create and publish versioned YAML rules, then decide who can run scans and open reports. Changes are audited.</p></section>
      {error && <div className="alert alert-error" role="alert">{error}</div>}
      {message && <div className="admin-alert-success" role="status">{message}</div>}
      {loading && <p>Loading frameworks…</p>}
      <div className="framework-columns">
        <aside className="panel framework-list">
          <h2>Frameworks</h2>
          {frameworks.map(item => <button type="button" key={item.id} onClick={() => { if (!yamlDirty || window.confirm('Discard unsaved YAML edits?')) setSelected(item.id); }}
            className={`framework-list-item ${selected === item.id ? 'selected' : ''}`}>
            <strong>{item.name}</strong><small>{item.id} · {item.status.toLowerCase()} · {item.versions.length} versions</small>
          </button>)}
          <form onSubmit={create} className="framework-create-form">
            <h3><Plus size={16}/> New framework</h3>
            <label className="field-label" htmlFor="new-framework-slug">Unique ID</label>
            <input id="new-framework-slug" required minLength={2} maxLength={64} placeholder="cookie_audit" value={newSlug} onChange={e=>setNewSlug(e.target.value.toLowerCase())}/>
            <label className="field-label" htmlFor="new-framework-name">Name</label>
            <input id="new-framework-name" required maxLength={160} placeholder="Cookie Privacy Audit" value={newName} onChange={e=>setNewName(e.target.value)}/>
            <button className="button button-primary button-small" disabled={busy} type="submit">Create draft framework</button>
          </form>
        </aside>
        {fw && <div className="framework-workspace">
          <section className="panel framework-editor-panel">
            <h2><ShieldCheck size={18}/> {fw.name} <span className="framework-chip">{fw.status}</span></h2>
            <p className="field-hint">Published version: {fw.versions.find(v=>v.id === fw.active_version_id)?.version_no ?? 'None'}. Archived frameworks are unavailable to users; admins retain historical reports.</p>
            <label className="field-label" htmlFor="edit-framework-name">Framework name</label>
            <input id="edit-framework-name" value={name} maxLength={160} onChange={e=>setName(e.target.value)}/>
            <label className="field-label" htmlFor="edit-framework-desc">Description</label>
            <textarea id="edit-framework-desc" rows={2} maxLength={2000} value={description} onChange={e=>setDescription(e.target.value)}/>
            <div className="framework-action-row">
              <button type="button" disabled={busy} className="button button-secondary button-small" onClick={()=>void perform(()=>frameworkAdminApi.edit(fw.id, {name,description}), 'Framework details saved.')}>Save details</button>
              <button type="button" disabled={busy} className="button button-secondary button-small" onClick={()=>{if(window.confirm(`${fw.status==='ARCHIVED'?'Restore':'Archive'} ${fw.name}?`)) void perform(()=>frameworkAdminApi.archive(fw.id, fw.status!=='ARCHIVED'), 'Framework availability updated.');}}>{fw.status === 'ARCHIVED' ? 'Restore' : 'Archive'}</button>
            </div>
          </section>
          <section className="panel framework-editor-panel">
            <h2><LockKeyhole size={18}/> Who can use this framework?</h2>
            <label className="framework-check"><input type="checkbox" checked={everyone} onChange={e=>setEveryone(e.target.checked)}/> Everyone admitted to PrivaCheck</label>
            <p className="field-hint">Selectors are combined with OR. ADMIN bypasses these selectors. Users must still pass platform admission.</p>
            <label className="field-label" htmlFor="framework-domains">Google Workspace domains (one per line)</label>
            <textarea id="framework-domains" rows={3} placeholder="iiitg.ac.in" value={domains} onChange={e=>setDomains(e.target.value)}/>
            <label className="field-label" htmlFor="framework-emails">Specific Google emails (one per line)</label>
            <textarea id="framework-emails" rows={3} placeholder="student@gmail.com" value={emails} onChange={e=>setEmails(e.target.value)}/>
            <div className="framework-action-row"><button type="button" disabled={busy} className="button button-primary button-small" onClick={()=>void perform(()=>frameworkAdminApi.access(fw.id,{everyone,domains:lines(domains),emails:lines(emails)}),'Framework access policy saved and immediately enforced.')}>Save access policy</button></div>
            <p className="admin-security-note">Revoking access also blocks that user's previous reports for this framework. The data remains stored for administrators.</p>
          </section>
          <section className="panel framework-editor-panel">
            <h2><FileCode2 size={18}/> YAML rule editor</h2>
            <p className="field-hint">Read an existing version, or create a new draft. Never overwrite an immutable published version. Only implemented declarative operators can be published.</p>
            <div className="framework-action-row"><button type="button" disabled={busy} className="button button-secondary button-small" onClick={startDraft}>New blank draft</button></div>
            <div className="framework-version-list">
              {fw.versions.map(version => <button type="button" key={version.id} disabled={busy}
                className={`button button-secondary button-small ${loadedVersion===version.id?'framework-version-selected':''}`}
                onClick={()=>void loadVersion(version.id)}>v{version.version_no} · {version.status.toLowerCase()} · {version.rule_count} rules</button>)}
            </div>
            <label className="field-label" htmlFor="framework-yaml">{draftId ? 'Editing draft' : loadedVersion ? 'Published version (copy to new draft)' : 'New unsaved draft'} · YAML</label>
            <textarea id="framework-yaml" className="framework-yaml" spellCheck={false} value={yamlText} onChange={e=>{setYamlText(e.target.value);setYamlDirty(true);setValidation('');}}/>
            <div className="framework-action-row">
              <button type="button" disabled={busy} className="button button-secondary button-small" onClick={()=>void validate()}>Validate</button>
              <button type="button" disabled={busy} className="button button-primary button-small" onClick={()=>void saveDraft()}>{draftId ? 'Save draft changes' : 'Save new draft'}</button>
              <button type="button" disabled={busy || !draftId || yamlDirty} className="button button-primary button-small" onClick={()=>void publishDraft()}>Publish saved draft</button>
            </div>
            {validation && <p className="framework-valid"><CheckCircle size={15}/>{validation}</p>}
            <label className="field-label" htmlFor="framework-sample">Optional sample observations (JSON)</label>
            <textarea id="framework-sample" className="framework-sample" spellCheck={false} rows={3} value={sampleJson} onChange={e=>setSampleJson(e.target.value)}/>
            <button type="button" className="button button-secondary button-small" disabled={busy} onClick={()=>void testSample()}>Test with sample evidence</button>
            {preview.length > 0 && <div className="framework-preview" role="status"><strong>Synthetic test only — not legal compliance evidence</strong><ul>{preview.map(item=><li key={item.id}>{item.id}: {item.status} — {item.name}</li>)}</ul></div>}
            {yamlDirty && <p className="field-hint">Unsaved YAML edits. Save and validate before publishing.</p>}
          </section>
        </div>}
      </div>
      <p className="admin-security-note"><ShieldCheck size={16}/> Editing and publishing require a recent Google sign-in. Reports represent technical evidence, not legal certification.</p>
    </div>
  );
}
