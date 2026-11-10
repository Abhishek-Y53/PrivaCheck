export interface AuthUser {
  id: string;
  email: string;
  role: 'USER' | 'ADMIN';
  display_name: string | null;
  is_active: boolean;
  created_at: string;
}

export interface CsrfResponse {
  csrf_token: string;
}
