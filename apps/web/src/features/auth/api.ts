import { apiClient } from "@/shared/lib/api/client";

export interface LoginPayload {
  email?: string;
  username_or_email?: string;
  password: string;
}

export interface RegisterPayload {
  email: string;
  password: string;
  display_name?: string;
}

export interface AuthUser {
  id: string;
  email: string;
  displayName?: string | null;
  isActive: boolean;
  createdAt: string;
}

export const authApi = {
  login: async (payload: LoginPayload): Promise<{ access_token: string; token_type: string; user: AuthUser }> => {
    const email = payload.email || payload.username_or_email || "";
    return apiClient.post<{ access_token: string; token_type: string; user: AuthUser }>(
      "/api/v1/auth/login",
      { email, password: payload.password }
    );
  },

  register: async (payload: RegisterPayload): Promise<{ access_token: string; token_type: string; user: AuthUser }> => {
    return apiClient.post<{ access_token: string; token_type: string; user: AuthUser }>(
      "/api/v1/auth/register",
      payload
    );
  },

  getMe: async (): Promise<AuthUser> => {
    return apiClient.get<AuthUser>("/api/v1/auth/me");
  },

  logout: async (): Promise<{ message: string }> => {
    return apiClient.post<{ message: string }>("/api/v1/auth/logout", {});
  },
};
