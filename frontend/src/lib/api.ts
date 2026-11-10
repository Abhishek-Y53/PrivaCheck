import type {
  ApiScanList,
  ApiScanReport,
  ApiScanStatus,
  CreateScanRequest,
  CreateScanResponse,
  FrameworkOption,
  PaginatedScans,
  ScanReport,
  ScanSummary,
} from '../types/api';
import { demoReport, frameworks, initialScans } from '../mock/data';
import type { AuthUser, CsrfResponse } from '../types/auth';
import type { GovernedFramework, FrameworkVersionContent } from '../types/frameworks';
import type { AdminAuditList, AdminScanList, AdminUser, AdminUserList, AdmissionEntry, AdmissionList } from '../types/admin';

// Mock mode is opt-in. A fresh install uses the real API unless the developer
// explicitly sets VITE_USE_MOCK_DATA=true.
const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === 'true';
// The current FastAPI routes are mounted at /scans, not /api/v1/scans.
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '');
const STORAGE_KEY = 'privacheck.mock.scans.v1';

export class ApiError extends Error {
  readonly status: number;
  readonly detail?: unknown;

  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

function readMockScans(): ScanSummary[] {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) return JSON.parse(stored) as ScanSummary[];
  } catch {
    // Fall back to the bundled demonstration dataset.
  }
  return [...initialScans];
}

function writeMockScans(scans: ScanSummary[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(scans));
}

function mockReportFor(scan: ScanSummary): ScanReport {
  // The bundled BBC report is an illustrative sample. Newly simulated scans
  // must not inherit those findings or imply that the crawler actually ran.
  if (scan.scan_id === demoReport.scan_id) return demoReport;

  return {
    scan_id: scan.scan_id,
    website: scan.website,
    framework: scan.framework,
    overall_status: scan.overall_status ?? 'MANUAL_REVIEW',
    total_checks: scan.total_checks ?? 0,
    passed_checks: scan.passed_checks ?? 0,
    failed_checks: scan.failed_checks ?? 0,
    warning_checks: scan.warning_checks ?? 0,
    manual_review_checks: scan.manual_review_checks ?? 0,
    not_applicable_checks: scan.not_applicable_checks ?? 0,
    observation_count: scan.observation_count ?? 0,
    duration_seconds: scan.duration_seconds ?? 0,
    risk_score: scan.risk_score ?? null,
    risk_score_interpretation: 'Simulated demonstration result; no live website scan was executed.',
    created_at: scan.created_at,
    started_at: scan.started_at,
    completed_at: scan.completed_at,
    results: [],
    metadata: { demo_data: true, simulated: true },
  };
}

function describeApiError(status: number, body: unknown): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) => item && typeof item === 'object' && 'msg' in item
          ? String((item as { msg: unknown }).msg)
          : '')
        .filter(Boolean);
      if (messages.length) return messages.join('; ');
    }
    if (detail && typeof detail === 'object' && 'message' in detail) {
      return String((detail as { message: unknown }).message);
    }
  }
  if (body && typeof body === 'object' && 'message' in body) {
    return String((body as { message: unknown }).message);
  }
  return `The API request failed (${status}).`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set('Accept', 'application/json');
  if (init?.body !== undefined && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers,
      // The backend authenticates with HttpOnly cookies. Never move session
      // credentials into JavaScript storage or manually read Set-Cookie.
      credentials: 'include',
      cache: 'no-store',
    });
  } catch {
    throw new Error(
      'Cannot reach the PrivaCheck API. Confirm that FastAPI is running and VITE_API_BASE_URL points to it.',
    );
  }

  if (response.status === 401 && !path.startsWith('/auth/')) {
    window.dispatchEvent(new Event('privacheck:unauthorized'));
  }

  if (response.status === 204) return undefined as T;

  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(describeApiError(response.status, body), response.status, body);
  }
  if (body === null) {
    throw new Error('The API returned an empty or invalid JSON response.');
  }
  return body as T;
}

let csrfBootstrapPromise: Promise<string> | null = null;

async function refreshCsrfToken(): Promise<string> {
  // React StrictMode can mount the auth provider twice in development.
  // Coalesce concurrent bootstrap calls to avoid racing Set-Cookie responses.
  if (csrfBootstrapPromise) return csrfBootstrapPromise;

  csrfBootstrapPromise = request<CsrfResponse>('/auth/csrf')
    .then((result) => result.csrf_token)
    .finally(() => {
      csrfBootstrapPromise = null;
    });

  return csrfBootstrapPromise;
}

async function requestWithCsrf<T>(path: string, init: RequestInit): Promise<T> {
  // Refresh on every unsafe request. CSRF cookies expire independently from
  // the server-side session, and the cookie itself is HttpOnly by design.
  const token = await refreshCsrfToken();
  const headers = new Headers(init.headers);
  headers.set('X-CSRF-Token', token);
  return request<T>(path, { ...init, headers });
}

export const authApi = {
  async initialize(): Promise<AuthUser | null> {
    await refreshCsrfToken();
    try {
      return await request<AuthUser>('/auth/me');
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) return null;
      throw error;
    }
  },

  beginGoogleSignIn(): void {
    window.location.assign(`${API_BASE_URL}/auth/google/start`);
  },

  async linkLegacyAccount(password: string): Promise<AuthUser> {
    return requestWithCsrf<AuthUser>('/auth/google/link', {
      method: 'POST',
      body: JSON.stringify({ password }),
    });
  },

  async logout(): Promise<void> {
    await requestWithCsrf<void>('/auth/logout', { method: 'POST' });
  },
};

function durationBetween(startedAt?: string | null, completedAt?: string | null): number | undefined {
  if (!startedAt || !completedAt) return undefined;
  const start = Date.parse(startedAt);
  const end = Date.parse(completedAt);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return undefined;
  return (end - start) / 1000;
}

function mapScanStatus(scan: ApiScanStatus): ScanSummary {
  return {
    scan_id: scan.scan_id,
    website: scan.website,
    framework: scan.framework,
    ruleset_version_id: scan.ruleset_version_id,
    lifecycle_status: scan.lifecycle_status,
    overall_status: scan.compliance_status ?? undefined,
    created_at: scan.created_at,
    started_at: scan.started_at,
    completed_at: scan.completed_at,
    duration_seconds: durationBetween(scan.started_at, scan.completed_at),
    total_checks: scan.total_checks,
    passed_checks: scan.passed_checks,
    failed_checks: scan.failed_checks,
    observation_count: scan.observation_count,
    risk_score: scan.risk_score,
    error: scan.error,
  };
}

function getRiskScoreInterpretation(metadata: Record<string, unknown>): string {
  const policy = metadata.risk_scoring_policy;
  if (policy && typeof policy === 'object' && 'interpretation' in policy) {
    const interpretation = (policy as { interpretation?: unknown }).interpretation;
    if (typeof interpretation === 'string' && interpretation.trim()) return interpretation;
  }
  return 'Project heuristic score; not a probability, legal determination, or certification.';
}

function mapReport(report: ApiScanReport): ScanReport {
  const counts = {
    PASS: 0,
    FAIL: 0,
    WARNING: 0,
    MANUAL_REVIEW: 0,
    NOT_APPLICABLE: 0,
  };
  for (const result of report.results) counts[result.status] += 1;

  return {
    scan_id: report.scan_id,
    website: report.website,
    framework: report.framework,
    ruleset_version_id: report.ruleset_version_id,
    overall_status: report.compliance_status,
    total_checks: report.total_checks,
    passed_checks: report.passed_checks,
    failed_checks: report.failed_checks,
    warning_checks: counts.WARNING,
    manual_review_checks: counts.MANUAL_REVIEW,
    not_applicable_checks: counts.NOT_APPLICABLE,
    observation_count: report.observation_count,
    duration_seconds: durationBetween(report.started_at, report.completed_at) ?? 0,
    risk_score: report.risk_score,
    risk_score_interpretation: getRiskScoreInterpretation(report.metadata),
    created_at: report.created_at,
    started_at: report.started_at,
    completed_at: report.completed_at,
    results: report.results,
    metadata: report.metadata,
  };
}

export const api = {
  isMockMode: USE_MOCK_DATA,

  async listFrameworks(): Promise<FrameworkOption[]> {
    if (USE_MOCK_DATA) return frameworks;
    return request<FrameworkOption[]>('/frameworks');
  },

  async listScans(page = 1, pageSize = 10): Promise<PaginatedScans> {
    if (USE_MOCK_DATA) {
      const items = readMockScans().sort((a, b) => b.created_at.localeCompare(a.created_at));
      const start = (page - 1) * pageSize;
      return { items: items.slice(start, start + pageSize), page, page_size: pageSize, total: items.length };
    }

    const offset = (page - 1) * pageSize;
    const result = await request<ApiScanList>(`/scans?limit=${pageSize}&offset=${offset}`);
    return {
      items: result.items.map(mapScanStatus),
      page,
      page_size: result.limit,
      total: result.total,
    };
  },

  async createScan(payload: CreateScanRequest): Promise<CreateScanResponse> {
    if (!USE_MOCK_DATA) {
      return requestWithCsrf<CreateScanResponse>('/scans', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    }

    const scanId = `demo-${crypto.randomUUID().slice(0, 8)}`;
    const createdAt = new Date().toISOString();
    const scan: ScanSummary = {
      scan_id: scanId,
      website: payload.website,
      framework: payload.framework,
      lifecycle_status: 'QUEUED',
      created_at: createdAt,
    };
    const scans = [scan, ...readMockScans()];
    writeMockScans(scans);
    window.setTimeout(() => {
      const current = readMockScans();
      writeMockScans(current.map((item) => item.scan_id === scanId
        ? { ...item, lifecycle_status: 'RUNNING', started_at: new Date().toISOString() }
        : item));
    }, 1200);
    window.setTimeout(() => {
      const current = readMockScans();
      writeMockScans(current.map((item) => item.scan_id === scanId
        ? {
          ...item,
          lifecycle_status: 'COMPLETED',
          overall_status: 'MANUAL_REVIEW',
          completed_at: new Date().toISOString(),
          duration_seconds: 8.4,
          total_checks: 42,
          passed_checks: 0,
          failed_checks: 0,
          warning_checks: 0,
          manual_review_checks: 42,
          not_applicable_checks: 0,
          observation_count: 0,
          risk_score: 25,
        }
        : item));
    }, 5500);
    return {
      scan_id: scanId,
      website: payload.website,
      framework: payload.framework,
      lifecycle_status: 'QUEUED',
      created_at: createdAt,
      task_id: `demo-task-${scanId}`,
      status_url: `/scans/${scanId}`,
      report_url: `/scans/${scanId}/report`,
    };
  },

  async getScan(scanId: string, adminView = false): Promise<ScanSummary> {
    if (USE_MOCK_DATA) {
      const scan = readMockScans().find((item) => item.scan_id === scanId);
      if (!scan) throw new Error('Scan not found.');
      return scan;
    }
    const result = adminView
      ? (await request<{scan: ApiScanStatus}>(`/admin/scans/${encodeURIComponent(scanId)}`)).scan
      : await request<ApiScanStatus>(`/scans/${encodeURIComponent(scanId)}`);
    return mapScanStatus(result);
  },

  async getReport(scanId: string, adminView = false): Promise<ScanReport> {
    if (USE_MOCK_DATA) {
      const scan = await this.getScan(scanId);
      return mockReportFor(scan);
    }
    const prefix = adminView ? "/admin/scans" : "/scans";
    const result = await request<ApiScanReport>(`${prefix}/${encodeURIComponent(scanId)}/report`);
    return mapReport(result);
  },
};

/** Privileged API; the backend independently checks ADMIN on every operation. */
export const adminApi = {
  listUsers(q = '', offset = 0, limit = 50): Promise<AdminUserList> {
    return request(`/admin/users?limit=${limit}&offset=${offset}&q=${encodeURIComponent(q)}`);
  },
  changeRole(userId: string, role: 'USER' | 'ADMIN'): Promise<AdminUser> {
    return requestWithCsrf(`/admin/users/${encodeURIComponent(userId)}/role`, {
      method: 'POST', body: JSON.stringify({ role }),
    });
  },
  changeStatus(userId: string, is_active: boolean): Promise<AdminUser> {
    return requestWithCsrf(`/admin/users/${encodeURIComponent(userId)}/status`, {
      method: 'POST', body: JSON.stringify({ is_active }),
    });
  },
  listAllowlist(): Promise<AdmissionList> {
    return request('/admin/allowlist');
  },
  setAdmission(selectorType: 'domains' | 'emails', value: string, is_active: boolean): Promise<AdmissionEntry> {
    return requestWithCsrf(`/admin/allowlist/${selectorType}`, {
      method: 'POST', body: JSON.stringify({ value, is_active }),
    });
  },
  async listScans(offset = 0, limit = 50): Promise<AdminScanList> {
    const result = await request<{items: {scan: ApiScanStatus; owner_email: string | null}[]; total: number; offset: number; limit: number}>(
      `/admin/scans?limit=${limit}&offset=${offset}`,
    );
    return { ...result, items: result.items.map(({ scan, owner_email }) => ({ scan: mapScanStatus(scan), owner_email })) };
  },
  listAudit(offset = 0, limit = 50): Promise<AdminAuditList> {
    return request(`/admin/audit?limit=${limit}&offset=${offset}`);
  },
};

/** All mutation routes revalidate CSRF and the ADMIN session on the backend. */
export const frameworkAdminApi = {
  list(): Promise<GovernedFramework[]> {
    return request('/admin/frameworks');
  },
  create(payload: { slug: string; name: string; description: string }): Promise<GovernedFramework> {
    return requestWithCsrf('/admin/frameworks', { method: 'POST', body: JSON.stringify(payload) });
  },
  edit(slug: string, payload: {name: string; description: string}): Promise<GovernedFramework> {
    return requestWithCsrf(`/admin/frameworks/${encodeURIComponent(slug)}`, { method: 'PUT', body: JSON.stringify(payload) });
  },
  archive(slug: string, archived: boolean): Promise<GovernedFramework> {
    return requestWithCsrf(`/admin/frameworks/${encodeURIComponent(slug)}/archive`, {
      method: 'POST', body: JSON.stringify({ archived }),
    });
  },
  access(slug: string, policy: {everyone: boolean; domains: string[]; emails: string[]}): Promise<GovernedFramework> {
    return requestWithCsrf(`/admin/frameworks/${encodeURIComponent(slug)}/access`, {
      method: 'PUT', body: JSON.stringify(policy),
    });
  },
  version(slug: string, id: string): Promise<FrameworkVersionContent> {
    return request(`/admin/frameworks/${encodeURIComponent(slug)}/versions/${encodeURIComponent(id)}`);
  },
  validate(yaml_content: string): Promise<{valid: boolean; rule_count: number}> {
    return requestWithCsrf('/admin/frameworks/validate', {
      method: 'POST', body: JSON.stringify({yaml_content}),
    });
  },
  preview(yaml_content: string, observations: {category: string; data: Record<string, unknown>}[]): Promise<{
    sample_only: boolean; rule_count: number; results: {id: string; name: string; status: string}[]; warning: string;
  }> {
    return requestWithCsrf('/admin/frameworks/preview', {
      method: 'POST', body: JSON.stringify({yaml_content, observations}),
    });
  },
  saveDraft(slug: string, yaml_content: string, version_id: string | null): Promise<{id: string; version_no: number; rule_count: number}> {
    return requestWithCsrf(`/admin/frameworks/${encodeURIComponent(slug)}/draft`, {
      method: 'POST', body: JSON.stringify({yaml_content, version_id}),
    });
  },
  publish(slug: string, id: string): Promise<GovernedFramework> {
    return requestWithCsrf(`/admin/frameworks/${encodeURIComponent(slug)}/publish/${encodeURIComponent(id)}`, {
      method: 'POST',
    });
  },
};
