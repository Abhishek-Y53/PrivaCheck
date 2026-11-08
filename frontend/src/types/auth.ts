export interface AuthUser {
  id: string;
  email: string;
  is_active: boolean;
  created_at: string;
}

export interface AuthResponse {
  user: AuthUser;
  csrf_token: string;
}

export interface CsrfResponse {
  csrf_token: string;
}
