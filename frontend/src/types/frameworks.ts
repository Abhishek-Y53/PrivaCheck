export interface FrameworkVersion {
  id: string;
  version_no: number;
  status: 'DRAFT' | 'PUBLISHED';
  rule_count: number;
  sha256: string;
  created_at: string;
  published_at: string | null;
}

export interface GovernedFramework {
  id: string;
  name: string;
  description: string;
  status: 'DRAFT' | 'PUBLISHED' | 'ARCHIVED';
  active_version_id: string | null;
  versions: FrameworkVersion[];
  access: { everyone: boolean; domains: string[]; emails: string[] };
}

export interface FrameworkVersionContent {
  id: string;
  version_no: number;
  status: 'DRAFT' | 'PUBLISHED';
  rule_count: number;
  sha256: string;
  yaml_content: string;
}
