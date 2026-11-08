import type { ComplianceStatus, ScanLifecycleStatus } from '../types/api';

type Status = ComplianceStatus | ScanLifecycleStatus;

const labels: Record<Status, string> = {
  PASS: 'Passed',
  FAIL: 'Failed',
  WARNING: 'Warning',
  MANUAL_REVIEW: 'Manual review',
  NOT_APPLICABLE: 'Not applicable',
  QUEUED: 'Queued',
  RUNNING: 'Running',
  COMPLETED: 'Completed',
  FAILED: 'Failed',
  CANCELLED: 'Cancelled',
};

export function StatusBadge({ status }: { status: Status }) {
  return (
    <span className={`status-badge status-${status.toLowerCase().replaceAll('_', '-')}`}>
      {status === 'RUNNING' && <span className="pulse-dot" />}
      {labels[status]}
    </span>
  );
}
