export type ComplianceStatus =
  | 'PASS'
  | 'FAIL'
  | 'WARNING'
  | 'MANUAL_REVIEW'
  | 'NOT_APPLICABLE';

export type ScanLifecycleStatus =
  | 'QUEUED'
  | 'RUNNING'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED';

// Framework IDs are strings so adding a registered YAML framework does not
// require changing the frontend's TypeScript union every time.
export type FrameworkId = string;
export type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO';

export interface FrameworkOption {
  id: FrameworkId;
  name: string;
  description: string;
  enabled: boolean;
}

/** Frontend-normalized scan summary. The API's compliance_status is mapped
 * to overall_status by lib/api.ts so existing presentation components remain
 * simple and do not need to know the transport schema's field names.
 */
export interface ScanSummary {
  scan_id: string;
  website: string;
  framework: FrameworkId;
  lifecycle_status: ScanLifecycleStatus;
  overall_status?: ComplianceStatus;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  duration_seconds?: number;
  total_checks?: number;
  passed_checks?: number;
  failed_checks?: number;
  warning_checks?: number;
  manual_review_checks?: number;
  not_applicable_checks?: number;
  observation_count?: number;
  risk_score?: number | null;
  error?: string | null;
}

export interface ObservationEvidence {
  category: string;
  source_url: string;
  timestamp: number;
  data: Record<string, unknown>;
}

export interface CheckResult {
  check_id: string;
  name: string;
  status: ComplianceStatus;
  severity: Severity;
  confidence: number;
  explanation: string;
  recommendation?: string | null;
  evidence: ObservationEvidence[];
}

/** Frontend-normalized report. Counts not present in the backend response are
 * calculated from its persisted per-rule results in lib/api.ts.
 */
export interface ScanReport {
  scan_id: string;
  website: string;
  framework: FrameworkId;
  overall_status: ComplianceStatus;
  total_checks: number;
  passed_checks: number;
  failed_checks: number;
  warning_checks: number;
  manual_review_checks: number;
  not_applicable_checks: number;
  observation_count: number;
  duration_seconds: number;
  risk_score: number | null;
  risk_score_interpretation: string;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  results: CheckResult[];
  metadata: Record<string, unknown>;
}

export interface PaginatedScans {
  items: ScanSummary[];
  page: number;
  page_size: number;
  total: number;
}

export interface CreateScanRequest {
  website: string;
  framework: FrameworkId;
}

export interface CreateScanResponse {
  scan_id: string;
  website: string;
  framework: FrameworkId;
  lifecycle_status: 'QUEUED';
  created_at: string;
  task_id: string;
  status_url: string;
  report_url: string;
}

/** Exact transport shapes returned by the current FastAPI M6 endpoints. */
export interface ApiScanStatus {
  scan_id: string;
  website: string;
  framework: FrameworkId;
  lifecycle_status: ScanLifecycleStatus;
  compliance_status: ComplianceStatus | null;
  total_checks: number;
  passed_checks: number;
  failed_checks: number;
  observation_count: number;
  risk_score: number | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface ApiScanList {
  items: ApiScanStatus[];
  total: number;
  limit: number;
  offset: number;
}

export interface ApiScanReport {
  scan_id: string;
  website: string;
  framework: FrameworkId;
  lifecycle_status: 'COMPLETED';
  compliance_status: ComplianceStatus;
  total_checks: number;
  passed_checks: number;
  failed_checks: number;
  observation_count: number;
  risk_score: number;
  metadata: Record<string, unknown>;
  results: CheckResult[];
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}
