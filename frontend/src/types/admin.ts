import type { ScanSummary } from './api';

export interface AdminUser {
  id: string;
  email: string;
  display_name: string | null;
  role: 'USER' | 'ADMIN';
  is_active: boolean;
  google_linked: boolean;
  created_at: string;
}

export interface AdminUserList {
  items: AdminUser[];
  total: number;
  limit: number;
  offset: number;
}

export interface AdmissionEntry {
  id: string;
  value: string;
  is_active: boolean;
  created_at: string;
}

export interface AdmissionList {
  domains: AdmissionEntry[];
  emails: AdmissionEntry[];
}

export interface AdminScan {
  scan: ScanSummary;
  owner_email: string | null;
}

export interface AdminScanList {
  items: AdminScan[];
  total: number;
  limit: number;
  offset: number;
}

export interface AdminAuditEntry {
  id: string;
  actor_user_id: string;
  action: string;
  target_type: string;
  target_id: string;
  before_data: Record<string, unknown> | null;
  after_data: Record<string, unknown> | null;
  created_at: string;
}

export interface AdminAuditList {
  items: AdminAuditEntry[];
  total: number;
  limit: number;
  offset: number;
}
