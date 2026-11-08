import type { LucideIcon } from 'lucide-react';

export function MetricCard({ label, value, detail, icon: Icon, tone = 'blue' }: {
  label: string; value: string | number; detail: string; icon: LucideIcon; tone?: 'blue' | 'green' | 'red' | 'amber';
}) {
  return <div className="metric-card"><div className={`metric-icon metric-${tone}`}><Icon size={18} /></div><div className="metric-label">{label}</div><div className="metric-value">{value}</div><div className="metric-detail">{detail}</div></div>;
}
