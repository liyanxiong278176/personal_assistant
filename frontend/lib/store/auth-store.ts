import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { User, AuthState, LoginRequest, RegisterRequest } from "../types";

interface AuthStore extends AuthState {
  login: (credentials: LoginRequest) => Promise<void>;
  register: (data: RegisterRequest) => Promise<void>;
  logout: () => Promise<void>;
  refreshAccessToken: () => Promise<void>;
  setUser: (user: User | null) => void;
  setToken: (token: string | null) => void;
  clearAuth: () => void;
  fetchCurrentUser: () => Promise<void>;
  initializeAuth: () => Promise<void>;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Helper to normalize backend user data to frontend User type
function normalizeUser(backendUser: any): User {
  return {
    id: backendUser.user_id || backendUser.id,
    email: backendUser.email || "",
    username: backendUser.username,
    avatar_url: backendUser.avatar_url,
    email_verified: backendUser.email_verified,
    phone: backendUser.phone,
    phone_verified: backendUser.phone_verified,
    created_at: backendUser.created_at,
    updated_at: backendUser.updated_at,
  };
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: false,

      initializeAuth: async () => {
        const token = get().token;
        if (!token) {
          set({ isLoading: false });
          return;
        }

        try {
          const response = await fetch(`${API_BASE}/api/v1/auth/me`, {
            headers: {
              Authorization: `Bearer ${token}`,
            },
          });

          if (!response.ok) {
            get().clearAuth();
            return;
          }

          const backendUser = await response.json();
          set({
            user: normalizeUser(backendUser),
            isAuthenticated: true,
            isLoading: false,
          });
        } catch (error) {
          get().clearAuth();
          set({ isLoading: false });
        }
      },

      login: async (credentials: LoginRequest) => {
        set({ isLoading: true });
        try {
          const response = await fetch(`${API_BASE}/api/v1/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(credentials),
          });

          if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || "Login failed");
          }

          const data = await response.json();
          set({
            user: normalizeUser(data.user),
            token: data.access_token,
            refreshToken: data.refresh_token,
            isAuthenticated: true,
            isLoading: false,
          });
        } catch (error) {
          set({ isLoading: false });
          throw error;
        }
      },

      register: async (data: RegisterRequest) => {
        set({ isLoading: true });
        try {
          const response = await fetch(`${API_BASE}/api/v1/auth/register`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data),
          });

          if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || "Registration failed");
          }

          const result = await response.json();
          // Set auth state after successful registration
          set({
            user: normalizeUser(result.user),
            token: result.access_token,
            refreshToken: result.refresh_token,
            isAuthenticated: true,
            isLoading: false,
          });
        } catch (error) {
          set({ isLoading: false });
          throw error;
        }
      },

      logout: async () => {
        const refreshToken = get().refreshToken;
        try {
          await fetch(`${API_BASE}/api/v1/auth/logout`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ refresh_token: refreshToken }),
          });
        } catch (error) {
          console.error("Logout error:", error);
        } finally {
          set({
            user: null,
            token: null,
            refreshToken: null,
            isAuthenticated: false,
          });
        }
      },

      refreshAccessToken: async () => {
        const refreshToken = get().refreshToken;
        if (!refreshToken) {
          get().clearAuth();
          return;
        }

        try {
          const response = await fetch(`${API_BASE}/api/v1/auth/refresh-token`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ refresh_token: refreshToken }),
          });

          if (!response.ok) {
            get().clearAuth();
            return;
          }

          const data = await response.json();
          set({
            token: data.access_token,
            refreshToken: data.refresh_token,
          });
        } catch (error) {
          get().clearAuth();
        }
      },

      setUser: (user: User | null) => set({ user }),
      setToken: (token: string | null) => set({ token }),

      clearAuth: () => {
        set({
          user: null,
          token: null,
          refreshToken: null,
          isAuthenticated: false,
        });
      },

      fetchCurrentUser: async () => {
        const token = get().token;
        if (!token) return;

        set({ isLoading: true });
        try {
          const response = await fetch(`${API_BASE}/api/v1/auth/me`, {
            headers: {
              Authorization: `Bearer ${token}`,
            },
          });

          if (!response.ok) {
            get().clearAuth();
            return;
          }

          const backendUser = await response.json();
          set({
            user: normalizeUser(backendUser),
            isAuthenticated: true,
            isLoading: false,
          });
        } catch (error) {
          get().clearAuth();
          set({ isLoading: false });
        }
      },
    }),
    {
      name: "auth-storage",
      partialize: (state) => ({
        user: state.user,
        token: state.token,
        refreshToken: state.refreshToken,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);
