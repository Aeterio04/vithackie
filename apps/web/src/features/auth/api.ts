import { apiClient } from "@/shared/lib/api/client";

export interface LoginPayload {
  email?: string;
  username_or_email?: string;
  password: string;
}

export interface RegisterPayload {
  email: string;
  password: string;
  name?: string;
}

export interface AuthUser {
  id: string;
  email: string;
  displayName?: string | null;
  name?: string | null;
  isActive: boolean;
  createdAt?: string | null;
}

/** Shape returned by POST /auth/login and /auth/register. The JWT is ALSO set as an httpOnly cookie; the website
 * never reads or stores the token itself, it relies on that cookie (`credentials: "include"`). */
export interface AuthSession extends AuthUser {
  token: string;
  access_token: string;
  token_type: string;
  user: AuthUser;
}

export const authApi = {
  login: async (payload: LoginPayload): Promise<AuthSession> => {
    const email = (payload.email || payload.username_or_email || "").trim();
    return apiClient.post<AuthSession>("/api/v1/auth/login", { email, password: payload.password });
  },

  register: async (payload: RegisterPayload): Promise<AuthSession> => {
    return apiClient.post<AuthSession>("/api/v1/auth/register", {
      email: payload.email.trim(),
      password: payload.password,
      name: payload.name?.trim() || undefined,
    });
  },

  getMe: async (): Promise<AuthUser> => {
    return apiClient.get<AuthUser>("/api/v1/auth/me");
  },

  logout: async (): Promise<{ ok: boolean }> => {
    return apiClient.post<{ ok: boolean }>("/api/v1/auth/logout", {});
  },
};
