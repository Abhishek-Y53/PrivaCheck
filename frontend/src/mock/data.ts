import type { FrameworkOption, ScanReport, ScanSummary } from '../types/api';

const now = Date.now();
const iso = (offsetMinutes: number) => new Date(now - offsetMinutes * 60_000).toISOString();

export const frameworks: FrameworkOption[] = [
  { id: 'gdpr', name: 'GDPR', description: 'Technical website checks mapped to the configured GDPR rule set.', enabled: true },
];

export const initialScans: ScanSummary[] = [
  {
    scan_id: 'demo-7f42c9', website: 'https://www.bbc.com/', framework: 'gdpr',
    lifecycle_status: 'COMPLETED', overall_status: 'FAIL', created_at: iso(34), started_at: iso(34), completed_at: iso(33),
    duration_seconds: 23.1, total_checks: 42, passed_checks: 16, failed_checks: 11,
    warning_checks: 0, manual_review_checks: 0, not_applicable_checks: 15,
    observation_count: 1838, risk_score: 39.76,
  },
  {
    scan_id: 'demo-1a82de', website: 'https://www.iiitg.ac.in/', framework: 'gdpr',
    lifecycle_status: 'COMPLETED', overall_status: 'WARNING', created_at: iso(165), started_at: iso(165), completed_at: iso(163),
    duration_seconds: 18.4, total_checks: 42, passed_checks: 21, failed_checks: 0,
    warning_checks: 5, manual_review_checks: 2, not_applicable_checks: 14,
    observation_count: 912, risk_score: 17.5,
  },
  {
    scan_id: 'demo-9c512b', website: 'https://example.com/', framework: 'gdpr',
    lifecycle_status: 'COMPLETED', overall_status: 'MANUAL_REVIEW', created_at: iso(390), started_at: iso(390), completed_at: iso(387),
    duration_seconds: 12.8, total_checks: 42, passed_checks: 10, failed_checks: 0,
    warning_checks: 2, manual_review_checks: 24, not_applicable_checks: 6,
    observation_count: 246, risk_score: 25,
  },
  {
    scan_id: 'demo-5d330e', website: 'https://www.wikipedia.org/', framework: 'gdpr',
    lifecycle_status: 'FAILED', created_at: iso(1440), started_at: iso(1440), completed_at: iso(1439),
    error: 'The demonstration scan represents a failed worker execution.',
  },
];

const resultRows = [
  { check_id: 'GDPR-024', name: 'HTTPS with valid TLS certificate', status: 'PASS' as const, severity: 'HIGH' as const, confidence: 1, explanation: 'A TLS certificate was observed and certificate verification succeeded.', recommendation: null, evidence: [{ category: 'tls_certificate', source_url: 'https://www.bbc.com/', timestamp: now / 1000, data: { protocol: 'https', verified: true, tls_version: 'TLSv1.3' } }] },
  { check_id: 'GDPR-006', name: 'Privacy Policy link exists', status: 'PASS' as const, severity: 'MEDIUM' as const, confidence: 0.92, explanation: 'A link labelled Privacy Policy was detected in the footer.', recommendation: null, evidence: [{ category: 'link', source_url: 'https://www.bbc.com/', timestamp: now / 1000, data: { text: 'Privacy Policy', href: 'https://www.bbc.com/pages/privacy-policy', region: 'footer' } }] },
  { check_id: 'GDPR-009', name: 'Data export mechanism exists', status: 'FAIL' as const, severity: 'MEDIUM' as const, confidence: 0.74, explanation: 'No matching data-export mechanism was identified in the collected links.', recommendation: 'Provide users with a clear mechanism to export or download their personal data.', evidence: [] },
  { check_id: 'GDPR-027-CSP', name: 'HTTPS navigation response includes CSP', status: 'FAIL' as const, severity: 'MEDIUM' as const, confidence: 0.86, explanation: 'The observed HTML navigation response did not contain a Content-Security-Policy header.', recommendation: 'Define and test a suitable Content-Security-Policy for the website.', evidence: [{ category: 'network_response', source_url: 'https://www.bbc.com/', timestamp: now / 1000, data: { status: 200, header_missing: 'content-security-policy' } }] },
  { check_id: 'GDPR-003', name: 'Reject All consent option', status: 'NOT_APPLICABLE' as const, severity: 'HIGH' as const, confidence: 1, explanation: 'The applicability conditions were not satisfied in this scan.', recommendation: null, evidence: [] },
  { check_id: 'GDPR-014', name: 'Data protection officer contact information detected', status: 'MANUAL_REVIEW' as const, severity: 'MEDIUM' as const, confidence: 0.3, explanation: 'Automated text matching cannot establish whether a DPO is legally required or designated.', recommendation: 'Review the organisation-specific requirement and the privacy notice manually.', evidence: [] },
];

export const demoReport: ScanReport = {
  scan_id: 'demo-7f42c9', website: 'https://www.bbc.com/', framework: 'gdpr', overall_status: 'FAIL',
  total_checks: 42, passed_checks: 16, failed_checks: 11, warning_checks: 0,
  manual_review_checks: 0, not_applicable_checks: 15, observation_count: 1838,
  duration_seconds: 23.1, risk_score: 39.76,
  risk_score_interpretation: 'Project heuristic score; not a probability, legal determination, or certification.',
  created_at: iso(34), results: resultRows, metadata: { crawler_status: 'COMPLETED', framework: 'gdpr', demo_data: true },
};
