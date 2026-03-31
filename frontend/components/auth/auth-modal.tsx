"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/lib/store/auth-store";
import { LoginForm } from "./login-form";
import { RegisterForm } from "./register-form";

type AuthView = "login" | "register";

interface AuthModalProps {
  isOpen?: boolean;
  onClose?: () => void;
}

export function AuthModal({ isOpen = true, onClose }: AuthModalProps) {
  const { user, isAuthenticated, logout, fetchCurrentUser } = useAuthStore();
  const [view, setView] = useState<AuthView>("login");
  const [showModal, setShowModal] = useState(isOpen);

  useEffect(() => {
    // Initialize auth state on mount
    fetchCurrentUser();
  }, [fetchCurrentUser]);

  useEffect(() => {
    setShowModal(isOpen);
  }, [isOpen]);

  const handleClose = () => {
    setShowModal(false);
    onClose?.();
  };

  const handleAuthSuccess = () => {
    setShowModal(false);
    onClose?.();
  };

  const handleLogout = async () => {
    await logout();
  };

  // If user is authenticated, show user menu instead of auth modal
  if (isAuthenticated && user) {
    return (
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          {user.avatar_url ? (
            <img
              src={user.avatar_url}
              alt={user.username || user.email}
              className="w-8 h-8 rounded-full object-cover"
            />
          ) : (
            <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
              <span className="text-sm font-medium text-primary">
                {(user.username || user.email)?.[0]?.toUpperCase() || "U"}
              </span>
            </div>
          )}
          <span className="text-sm text-muted-foreground hidden sm:inline">
            {user.username || user.email}
          </span>
        </div>
        <Button variant="ghost" size="sm" onClick={handleLogout}>
          退出登录
        </Button>
      </div>
    );
  }

  if (!showModal) {
    return (
      <Button variant="outline" size="sm" onClick={() => setShowModal(true)}>
        登录 / 注册
      </Button>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-background/80 backdrop-blur-sm"
        onClick={handleClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-md bg-background border border-border rounded-lg shadow-lg p-6 m-4">
        {/* Close button */}
        <button
          onClick={handleClose}
          className="absolute right-4 top-4 text-muted-foreground hover:text-foreground transition-colors"
          aria-label="Close"
        >
          <svg
            className="w-5 h-5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </button>

        {/* Header */}
        <div className="mb-6">
          <h2 className="text-xl font-semibold">
            {view === "login" ? "登录" : "注册"}
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            {view === "login"
              ? "使用邮箱验证码登录您的账号"
              : "创建一个新账号开始使用"}
          </p>
        </div>

        {/* Toggle between login and register */}
        <div className="flex gap-2 mb-6 p-1 bg-muted rounded-lg">
          <button
            type="button"
            onClick={() => setView("login")}
            className={`flex-1 py-2 text-sm font-medium rounded-md transition-colors ${
              view === "login"
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            登录
          </button>
          <button
            type="button"
            onClick={() => setView("register")}
            className={`flex-1 py-2 text-sm font-medium rounded-md transition-colors ${
              view === "register"
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            注册
          </button>
        </div>

        {/* Forms */}
        {view === "login" ? (
          <LoginForm
            onSuccess={handleAuthSuccess}
            onSwitchToRegister={() => setView("register")}
          />
        ) : (
          <RegisterForm
            onSuccess={handleAuthSuccess}
            onSwitchToLogin={() => setView("login")}
          />
        )}
      </div>
    </div>
  );
}
