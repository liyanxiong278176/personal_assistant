import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { User, AuthState, LoginRequest, RegisterRequest, SendCodeRequest } from "../types";

interface AuthStore extends AuthState {
  login: (credentials: LoginRequest) => Promise<void>;
  register: (data: RegisterRequest) => Promise<void>;
  logout: () => Promise<void>;
  sendCode: (request: SendCodeRequest) => Promise<void>;
  refreshToken: () => Promise<void>;
  setUser: (user: User | null) => void;
  setToken: (token: string | null) => void;
  clearAuth: () => void;
  fetchCurrentUser: () => Promise<void>;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const useAuthStore = create<AuthStore>()(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      isAuthenticated: false,
      isLoading: false,

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
            user: data.user,
            token: data.access_token,
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
          set({ isLoading: false });
          return result;
        } catch (error) {
          set({ isLoading: false });
          throw error;
        }
      },

      logout: async () => {
        const token = get().token;
        try {
          await fetch(`${API_BASE}/api/v1/auth/logout`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${token}`,
            },
          });
        } catch (error) {
          console.error("Logout error:", error);
        } finally {
          set({
            user: null,
            token: null,
            isAuthenticated: false,
          });
        }
      },

      sendCode: async (request: SendCodeRequest) => {
        const response = await fetch(`${API_BASE}/api/v1/auth/send-code`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(request),
        });

        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.detail || "Failed to send code");
        }
      },

      refreshToken: async () => {
        const token = get().token;
        if (!token) return;

        try {
          const response = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${token}`,
            },
          });

          if (!response.ok) {
            get().clearAuth();
            return;
          }

          const data = await response.json();
          set({
            token: data.access_token,
            user: data.user,
            isAuthenticated: true,
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

          const user = await response.json();
          set({
            user,
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
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);
