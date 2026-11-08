import { ArrowUpRight, Globe2 } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { ScanSummary } from '../types/api';
import { formatDate, formatDuration, getHostname } from '../lib/format';
import { StatusBadge } from './StatusBadge';

export function ScanTable({ scans, compact = false }: { scans: ScanSummary[]; compact?: boolean }) {
  if (!scans.length) return <div className="empty-state"><div className="empty-state-icon"><Globe2 size={22} /></div><strong>No scans yet</strong><span>Start your first website assessment to see results here.</span><Link className="button button-primary button-small" to="/scans/new">Create a scan</Link></div>;
  return (
    <div className="table-wrap"><table className="data-table"><thead><tr><th>WEBSITE</th><th>FRAMEWORK</th><th>STATUS</th>{!compact && <th>CHECKS</th>}<th>DATE</th>{!compact && <th>DURATION</th>}<th /></tr></thead>
      <tbody>{scans.map((scan) => <tr key={scan.scan_id}>
        <td><div className="website-cell"><div className="website-favicon"><Globe2 size={15} /></div><div><Link to={`/scans/${scan.scan_id}`} className="website-name">{getHostname(scan.website)}</Link><div className="website-url">{scan.website}</div></div></div></td>
        <td><span className="framework-chip">{scan.framework.toUpperCase()}</span></td>
        <td><StatusBadge status={scan.lifecycle_status === 'COMPLETED' ? (scan.overall_status ?? 'MANUAL_REVIEW') : scan.lifecycle_status} /></td>
        {!compact && <td><span className="table-number">{scan.total_checks ?? '—'}</span></td>}
        <td><span className="table-muted">{formatDate(scan.created_at)}</span></td>
        {!compact && <td><span className="table-muted">{formatDuration(scan.duration_seconds)}</span></td>}
        <td><Link className="icon-link" to={`/scans/${scan.scan_id}`} aria-label={`Open ${scan.website} report`}><ArrowUpRight size={16} /></Link></td>
      </tr>)}</tbody></table></div>
  );
}
