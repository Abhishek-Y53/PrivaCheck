import { useEffect, useState } from 'react';
import { ArrowRight, ArrowUpRight, CheckCircle2, CircleAlert, Clock3, FileSearch, Plus, ShieldCheck, XCircle } from 'lucide-react';
import { Link } from 'react-router-dom';
import { api } from '../lib/api';
import { formatNumber } from '../lib/format';
import type { ScanSummary } from '../types/api';
import { MetricCard } from '../components/MetricCard';
import { ScanTable } from '../components/ScanTable';

export function DashboardPage() {
  const [scans, setScans] = useState<ScanSummary[]>([]);
  const [totalScans, setTotalScans] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    api.listScans(1, 20)
      .then((data) => {
        if (!active) return;
        setScans(data.items);
        setTotalScans(data.total);
      })
      .catch((err: Error) => { if (active) setError(err.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const completed = scans.filter((scan) => scan.lifecycle_status === 'COMPLETED');
  const passed = completed.reduce((sum, scan) => sum + (scan.passed_checks ?? 0), 0);
  const failed = completed.reduce((sum, scan) => sum + (scan.failed_checks ?? 0), 0);
  const activeScans = scans.filter((scan) => scan.lifecycle_status === 'QUEUED' || scan.lifecycle_status === 'RUNNING').length;
  const latest = scans.slice(0, 5);

  return (
    <div className="page-stack">
      <section className="page-heading heading-with-action"><div><div className="eyebrow">OVERVIEW</div><h1>Good work starts with visibility.</h1><p className="page-subtitle">Monitor website assessments and review compliance evidence from one workspace.</p></div><Link to="/scans/new" className="button button-primary"><Plus size={16} /> New scan</Link></section>
      {error && <div className="alert alert-error">Unable to load scans: {error}</div>}
      <section className="metrics-grid">
        <MetricCard label="Total scans" value={loading ? '—' : formatNumber(totalScans)} detail="Assessments in this workspace" icon={FileSearch} tone="blue" />
        <MetricCard label="Checks passed" value={loading ? '—' : formatNumber(passed)} detail="Across the latest completed scans" icon={CheckCircle2} tone="green" />
        <MetricCard label="Checks failed" value={loading ? '—' : formatNumber(failed)} detail="Across the latest completed scans" icon={XCircle} tone="red" />
        <MetricCard label="In progress" value={loading ? '—' : activeScans} detail="Queued or running scans in latest results" icon={Clock3} tone="amber" />
      </section>
      <section className="dashboard-grid">
        <div className="panel recent-panel"><div className="panel-heading"><div><h2>Recent assessments</h2><p>Your latest website scans</p></div><Link to="/scans" className="text-link">View all <ArrowRight size={14} /></Link></div>{loading ? <div className="loading-row">Loading assessments…</div> : <ScanTable scans={latest} compact />}</div>
        <div className="panel launch-panel"><div className="launch-art"><div className="launch-orbit orbit-one" /><div className="launch-orbit orbit-two" /><div className="launch-shield"><ShieldCheck size={30} /></div></div><div className="launch-copy"><div className="eyebrow">GET STARTED</div><h2>Assess a website</h2><p>Submit a public website and choose a compliance framework to generate an evidence-backed assessment.</p><Link to="/scans/new" className="button button-primary button-full">Start new scan <ArrowUpRight size={15} /></Link></div><div className="launch-foot"><CircleAlert size={14} /> Results are technical indicators, not legal certification.</div></div>
      </section>
      <section className="info-strip"><div className="info-strip-icon"><ShieldCheck size={18} /></div><div><strong>Evidence-first assessment</strong><span>PrivaCheck separates browser observations from configurable rule evaluation. Interpret each result alongside its supporting evidence.</span></div><a href="https://github.com/Abhishek-Y53/PrivaCheck" target="_blank" rel="noreferrer" aria-label="Open project repository"><ArrowUpRight size={17} /></a></section>
    </div>
  );
}
