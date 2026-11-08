import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, ChevronDown, ChevronUp, Database, Download, FileJson, FileText, Info, Printer } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { StatusBadge } from '../components/StatusBadge';
import { api } from '../lib/api';
import { formatDate, formatDuration, getHostname } from '../lib/format';
import type { CheckResult, ComplianceStatus, ScanReport, ScanSummary } from '../types/api';

const statusFilters: Array<'ALL' | ComplianceStatus> = ['ALL', 'FAIL', 'WARNING', 'MANUAL_REVIEW', 'PASS', 'NOT_APPLICABLE'];

function EvidencePanel({ result }: { result: CheckResult }) {
  const [open, setOpen] = useState(false);
  if (!result.evidence.length) return null;
  return (
    <div className="evidence-block">
      <button className="evidence-toggle" onClick={() => setOpen(!open)} type="button"><Database size={14} /> {result.evidence.length} evidence item{result.evidence.length === 1 ? '' : 's'} {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}</button>
      {open && <div className="evidence-list">{result.evidence.map((item, index) => <div className="evidence-item" key={`${item.category}-${index}`}><div className="evidence-meta"><span className="framework-chip">{item.category}</span><span>{item.source_url}</span></div><pre>{JSON.stringify(item.data, null, 2)}</pre></div>)}</div>}
    </div>
  );
}

function ResultRow({ result }: { result: CheckResult }) {
  return (
    <div className="result-row">
      <div className="result-main">
        <div className="result-title-line"><span className="result-id">{result.check_id}</span><StatusBadge status={result.status} /><span className={`severity severity-${result.severity.toLowerCase()}`}>{result.severity}</span></div>
        <h3>{result.name}</h3><p>{result.explanation}</p>
        {result.recommendation && <div className="recommendation"><strong>Recommendation</strong><span>{result.recommendation}</span></div>}
        <EvidencePanel result={result} />
      </div>
      <div className="confidence"><strong>{Math.round(result.confidence * 100)}%</strong><span>confidence*</span></div>
    </div>
  );
}


function reportFileStem(report: ScanReport): string {
  const hostname = getHostname(report.website)
    .toLowerCase()
    .replace(/[^a-z0-9.-]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'website';
  return `privacheck-report-${hostname}-${report.scan_id}`;
}

function downloadReportJson(report: ScanReport): void {
  const exportPayload = {
    schema_version: '1.0',
    exported_at: new Date().toISOString(),
    report,
  };
  const blob = new Blob([JSON.stringify(exportPayload, null, 2)], {
    type: 'application/json;charset=utf-8',
  });
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = objectUrl;
  anchor.download = `${reportFileStem(report)}.json`;
  anchor.style.display = 'none';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}

function printReportAsPdf(report: ScanReport): void {
  const previousTitle = document.title;
  document.title = reportFileStem(report);
  const restoreTitle = () => {
    document.title = previousTitle;
    window.removeEventListener('afterprint', restoreTitle);
  };
  window.addEventListener('afterprint', restoreTitle, { once: true });
  window.print();
  // Some browsers do not consistently dispatch afterprint; avoid leaving the
  // application's document title changed after the print dialog is closed.
  window.setTimeout(restoreTitle, 60_000);
}

function formatEvidenceTimestamp(timestamp: number): string {
  if (!Number.isFinite(timestamp)) return '—';
  const date = new Date(timestamp * 1000);
  return Number.isNaN(date.getTime()) ? '—' : formatDate(date.toISOString());
}

function PrintableReport({ report }: { report: ScanReport }) {
  const metadataEntries = Object.entries(report.metadata).filter(([, value]) => value !== null && value !== undefined);

  return (
    <article className="print-report" aria-label="Printable compliance report">
      <header className="print-report-header">
        <div className="print-report-brand">PRIVACHECK <span>TECHNICAL COMPLIANCE ASSESSMENT</span></div>
        <h1>{getHostname(report.website)}</h1>
        <p className="print-report-url">{report.website}</p>
        <div className="print-report-meta-line">
          <span>Framework: <strong>{report.framework.toUpperCase()}</strong></span>
          <span>Scan ID: <strong>{report.scan_id}</strong></span>
          <span>Completed: <strong>{formatDate(report.completed_at ?? report.created_at)}</strong></span>
        </div>
      </header>

      <section className="print-report-summary">
        <div><span>Overall status</span><strong>{report.overall_status.replaceAll('_', ' ')}</strong></div>
        <div><span>Risk score</span><strong>{report.risk_score === null ? '—' : `${report.risk_score.toFixed(1)} / 100`}</strong></div>
        <div><span>Total checks</span><strong>{report.total_checks}</strong></div>
        <div><span>Passed</span><strong>{report.passed_checks}</strong></div>
        <div><span>Failed</span><strong>{report.failed_checks}</strong></div>
        <div><span>Warnings</span><strong>{report.warning_checks}</strong></div>
        <div><span>Manual review</span><strong>{report.manual_review_checks}</strong></div>
        <div><span>Not applicable</span><strong>{report.not_applicable_checks}</strong></div>
        <div><span>Observations</span><strong>{report.observation_count.toLocaleString()}</strong></div>
        <div><span>Duration</span><strong>{formatDuration(report.duration_seconds)}</strong></div>
      </section>

      <p className="print-report-interpretation">{report.risk_score_interpretation}</p>

      <section className="print-report-results">
        <h2>Assessment results ({report.results.length})</h2>
        {report.results.length === 0 ? (
          <p>No rule results are available in this report.</p>
        ) : report.results.map((result) => (
          <section className="print-report-result" key={result.check_id}>
            <div className="print-result-heading">
              <strong>{result.check_id} · {result.name}</strong>
              <span>{result.status.replaceAll('_', ' ')} · {result.severity}</span>
            </div>
            <div className="print-result-confidence">Confidence: {Math.round(result.confidence * 100)}%</div>
            <p>{result.explanation}</p>
            {result.recommendation && (
              <p className="print-recommendation"><strong>Recommendation: </strong>{result.recommendation}</p>
            )}
            {result.evidence.length > 0 && (
              <div className="print-evidence-list">
                <strong>Evidence ({result.evidence.length})</strong>
                {result.evidence.map((item, index) => (
                  <div className="print-evidence-item" key={`${item.category}-${index}`}>
                    <div><strong>{item.category}</strong> · {item.source_url}</div>
                    <div>Observed: {formatEvidenceTimestamp(item.timestamp)}</div>
                    <pre>{JSON.stringify(item.data, null, 2)}</pre>
                  </div>
                ))}
              </div>
            )}
          </section>
        ))}
      </section>

      {metadataEntries.length > 0 && (
        <section className="print-report-metadata">
          <h2>Technical metadata</h2>
          <dl>
            {metadataEntries.map(([key, value]) => (
              <div key={key}>
                <dt>{key.replaceAll('_', ' ')}</dt>
                <dd>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      <footer className="print-report-footer">
        This report contains technical indicators based on the collected evidence. Risk score and confidence are project heuristics, not statistically calibrated probabilities. This report is not legal advice, a legal determination, or a certification of compliance.
      </footer>
    </article>
  );
}

export function ScanDetailPage() {
  const { scanId = '' } = useParams();
  const [scan, setScan] = useState<ScanSummary | null>(null);
  const [report, setReport] = useState<ScanReport | null>(null);
  const [filter, setFilter] = useState<'ALL' | ComplianceStatus>('ALL');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    let timer: number | undefined;

    async function refresh() {
      try {
        const current = await api.getScan(scanId);
        if (!active) return;
        setScan(current);
        setError('');

        if (current.lifecycle_status === 'COMPLETED') {
          const nextReport = await api.getReport(scanId);
          if (active) setReport(nextReport);
          return;
        }

        if (current.lifecycle_status === 'QUEUED' || current.lifecycle_status === 'RUNNING') {
          timer = window.setTimeout(refresh, 1800);
        }
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : 'Unable to load scan.');
      } finally {
        if (active) setLoading(false);
      }
    }

    setLoading(true);
    setError('');
    setScan(null);
    setReport(null);
    refresh();

    return () => {
      active = false;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [scanId]);

  const filteredResults = useMemo(
    () => (report?.results ?? []).filter((result) => filter === 'ALL' || result.status === filter),
    [report, filter],
  );

  if (loading) return <div className="loading-page">Loading scan details…</div>;
  if (error || !scan) {
    return <div className="page-stack"><Link to="/scans" className="back-link"><ArrowLeft size={15} /> Back to scan history</Link><div className="alert alert-error">{error || 'Scan not found.'}</div></div>;
  }

  const isActive = scan.lifecycle_status === 'QUEUED' || scan.lifecycle_status === 'RUNNING';
  const displayStatus = isActive
    ? scan.lifecycle_status
    : (report?.overall_status ?? scan.overall_status ?? scan.lifecycle_status);

  return (
    <div className="page-stack">
      <Link to="/scans" className="back-link"><ArrowLeft size={15} /> Back to scan history</Link>
      <section className="page-heading report-heading"><div><div className="eyebrow">ASSESSMENT REPORT</div><div className="report-title-line"><h1>{getHostname(scan.website)}</h1><StatusBadge status={displayStatus} /></div><p className="page-subtitle">{scan.website}</p></div><div className="report-heading-actions">{report && <><button type="button" className="report-export-button" onClick={() => downloadReportJson(report)}><Download size={14} /><FileJson size={14} /> Download JSON</button><button type="button" className="report-export-button report-export-primary" onClick={() => printReportAsPdf(report)}><Printer size={14} /> Save as PDF</button></>}<span className="framework-chip framework-large">{scan.framework.toUpperCase()}</span></div></section>

      {isActive && <div className="panel progress-panel"><div className="progress-spinner" /><div><strong>{scan.lifecycle_status === 'QUEUED' ? 'Scan queued' : 'Assessment in progress'}</strong><p>PrivaCheck is processing this assessment. This page refreshes automatically.</p></div></div>}
      {scan.lifecycle_status === 'FAILED' && <div className="alert alert-error">{scan.error || 'The scan could not be completed.'}</div>}
      {scan.lifecycle_status === 'CANCELLED' && <div className="alert">This scan was cancelled before completion.</div>}

      {report && <>
        <section className="report-summary-grid">
          <div className="panel score-panel"><div className="score-heading"><span>RISK SCORE</span><Info size={14} /></div><div className="score-value">{report.risk_score === null ? '—' : report.risk_score.toFixed(1)}<small>/100</small></div><div className="score-bar"><span style={{ width: `${Math.min(100, Math.max(0, report.risk_score ?? 0))}%` }} /></div><p>{report.risk_score_interpretation}</p></div>
          <div className="panel summary-stat"><span>Checks passed</span><strong className="text-green">{report.passed_checks}</strong><small>of {report.total_checks} checks</small></div>
          <div className="panel summary-stat"><span>Checks failed</span><strong className="text-red">{report.failed_checks}</strong><small>Require investigation</small></div>
          <div className="panel summary-stat"><span>Observations</span><strong>{report.observation_count.toLocaleString()}</strong><small>Collected by crawler</small></div>
        </section>
        <section className="panel results-panel">
          <div className="panel-heading results-heading"><div><h2>Rule results</h2><p>Inspect each outcome and its supporting evidence.</p></div><span className="results-total">{report.results.length} rule results</span></div>
          <div className="result-filters">{statusFilters.map((item) => <button type="button" key={item} className={filter === item ? 'filter-tab active' : 'filter-tab'} onClick={() => setFilter(item)}>{item === 'ALL' ? 'All results' : item.replaceAll('_', ' ')}</button>)}</div>
          <div className="result-list">{report.results.length === 0 ? <div className="empty-filter">The completed report contains no rule results.</div> : filteredResults.length ? filteredResults.map((result) => <ResultRow key={result.check_id} result={result} />) : <div className="empty-filter">No results match this filter.</div>}</div>
        </section>
        <div className="report-footnote"><Info size={14} /> *Confidence is an implementation heuristic, not a statistically calibrated probability. This is a technical assessment, not legal advice.</div>
      </>}

      <section className="panel metadata-panel"><div className="metadata-heading"><FileText size={17} /><strong>Scan metadata</strong></div><div className="metadata-grid"><div><span>Scan ID</span><strong>{scan.scan_id}</strong></div><div><span>Created</span><strong>{formatDate(scan.created_at)}</strong></div><div><span>Duration</span><strong>{formatDuration(scan.duration_seconds)}</strong></div><div><span>Framework</span><strong>{scan.framework.toUpperCase()}</strong></div></div></section>
      {report && <PrintableReport report={report} />}
    </div>
  );
}
