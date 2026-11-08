import { useEffect, useMemo, useState } from 'react';
import { Search, SlidersHorizontal } from 'lucide-react';
import { api } from '../lib/api';
import type { ScanLifecycleStatus, ScanSummary } from '../types/api';
import { ScanTable } from '../components/ScanTable';

export function ScanHistoryPage() {
  const [scans, setScans] = useState<ScanSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<'ALL' | ScanLifecycleStatus>('ALL');
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    api.listScans(1, 100)
      .then((data) => { if (active) setScans(data.items); })
      .catch((err: Error) => { if (active) setError(err.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const filtered = useMemo(() => scans.filter((scan) => {
    const matchesText = scan.website.toLowerCase().includes(search.toLowerCase())
      || scan.scan_id.toLowerCase().includes(search.toLowerCase());
    const matchesStatus = filter === 'ALL' || scan.lifecycle_status === filter;
    return matchesText && matchesStatus;
  }), [scans, search, filter]);

  return (
    <div className="page-stack">
      <section className="page-heading"><div className="eyebrow">WORKSPACE</div><h1>Scan history</h1><p className="page-subtitle">Browse previous assessments and open their persisted reports.</p></section>
      <section className="panel history-panel">
        <div className="history-toolbar">
          <div className="search-field"><Search size={16} /><input aria-label="Search scans" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search website or scan ID" /></div>
          <div className="filter-control"><SlidersHorizontal size={15} /><select aria-label="Filter by lifecycle status" value={filter} onChange={(event) => setFilter(event.target.value as typeof filter)}><option value="ALL">All statuses</option><option value="QUEUED">Queued</option><option value="RUNNING">Running</option><option value="COMPLETED">Completed</option><option value="FAILED">Failed</option><option value="CANCELLED">Cancelled</option></select></div>
          <span className="result-count">{filtered.length} scans</span>
        </div>
        {error && <div className="alert alert-error">{error}</div>}
        {loading ? <div className="loading-row">Loading scan history…</div> : <ScanTable scans={filtered} />}
      </section>
    </div>
  );
}
