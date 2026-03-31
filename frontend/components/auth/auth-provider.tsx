"use client";

import { useEffect, useState } from "react";
import { useAuthStore } from "@/lib/store/auth-store";
import { AuthModal } from "./auth-modal";

interface AuthProviderProps {
  children: React.ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const { isAuthenticated, user, fetchCurrentUser } = useAuthStore();
  const [isInitialized, setIsInitialized] = useState(false);

  useEffect(() => {
    // Initialize auth state on mount
    const initAuth = async () => {
      await fetchCurrentUser();
      setIsInitialized(true);
    };
    initAuth();
  }, [fetchCurrentUser]);

  // For now, we don't force the modal to be open
  // The chat page will control when to show the auth modal
  return <>{children}</>;
}
