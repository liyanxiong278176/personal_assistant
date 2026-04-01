import type {
  User,
  LoginRequest,
  RegisterRequest,
  AuthResponse,
  RefreshTokenRequest,
} from "../types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(error.detail || "Request failed");
  }
  return response.json();
}

export const authApi = {
  /**
   * Login with email and password
   */
  async login(request: LoginRequest): Promise<AuthResponse> {
    const response = await fetch(`${API_BASE}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    return handleResponse<AuthResponse>(response);
  },

  /**
   * Register a new user
   */
  async register(request: RegisterRequest): Promise<AuthResponse> {
    const response = await fetch(`${API_BASE}/api/v1/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    return handleResponse<AuthResponse>(response);
  },

  /**
   * Logout current user
   */
  async logout(token: string): Promise<void> {
    const response = await fetch(`${API_BASE}/api/v1/auth/logout`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
    });
    return handleResponse<void>(response);
  },

  /**
   * Get current user profile
   */
  async getCurrentUser(token: string): Promise<User> {
    const response = await fetch(`${API_BASE}/api/v1/auth/me`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });
    return handleResponse<User>(response);
  },

  /**
   * Refresh access token
   */
  async refreshToken(request: RefreshTokenRequest): Promise<AuthResponse> {
    const response = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    return handleResponse<AuthResponse>(response);
  },
};
