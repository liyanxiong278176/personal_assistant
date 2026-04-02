"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/lib/store/auth-store";
import { LoginForm } from "./login-form";
import { RegisterForm } from "./register-form";
import { LogOut, User, Mail } from "lucide-react";

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
      <div className="flex items-center gap-3 p-3 rounded-xl bg-card/80 border border-border/50 backdrop-blur-sm">
        <div className="flex items-center gap-2">
          {user.avatar_url ? (
            <img
              src={user.avatar_url}
              alt={user.username || user.email}
              className="w-8 h-8 rounded-full object-cover ring-2 ring-primary/20"
            />
          ) : (
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-primary to-accent flex items-center justify-center">
              <span className="text-sm font-semibold text-white">
                {(user.username || user.email)?.[0]?.toUpperCase() || "U"}
              </span>
            </div>
          )}
          <div className="hidden sm:block">
            <div className="flex items-center gap-1.5">
              {user.username ? (
                <span className="text-sm font-medium text-foreground">{user.username}</span>
              ) : (
                <>
                  <Mail className="w-3 h-3 text-muted-foreground" />
                  <span className="text-sm text-muted-foreground">{user.email}</span>
                </>
              )}
            </div>
          </div>
        </div>
        <button
          onClick={handleLogout}
          className="p-2 rounded-lg hover:bg-muted/60 text-muted-foreground hover:text-destructive transition-all"
          title="退出登录"
        >
          <LogOut className="w-4 h-4" />
        </button>
      </div>
    );
  }

  if (!showModal) {
    return (
      <button
        onClick={() => setShowModal(true)}
        className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-primary to-[hsl(220,38%,32%)] text-white font-medium text-sm shadow-glow-primary hover:shadow-glow transition-all active:scale-[0.98]"
      >
        <User className="w-4 h-4" />
        <span className="hidden sm:inline">登录 / 注册</span>
      </button>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-background/60 backdrop-blur-md"
        onClick={handleClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-md animate-scale-in">
        {/* Decorative glow */}
        <div className="absolute -inset-1 bg-gradient-to-br from-primary/20 to-accent/20 rounded-3xl blur-xl" />

        <div className="relative bg-card/95 border border-border/60 rounded-2xl shadow-soft-xl p-8 backdrop-blur-md overflow-hidden">
          {/* Decorative top bar */}
          <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-primary via-accent to-primary" />

          {/* Close button */}
          <button
            onClick={handleClose}
            className="absolute right-4 top-4 p-1.5 hover:bg-muted/60 rounded-lg text-muted-foreground hover:text-foreground transition-colors"
            aria-label="关闭"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>

          {/* Header */}
          <div className="mb-7 text-center">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-br from-primary to-accent mb-4 shadow-glow">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                <circle cx="12" cy="7" r="4"/>
              </svg>
            </div>
            <h2 className="font-display text-2xl font-bold text-gradient-warm">
              {view === "login" ? "欢迎回来" : "开启旅程"}
            </h2>
            <p className="text-sm text-muted-foreground mt-1.5">
              {view === "login"
                ? "登录账号，同步你的旅行偏好和历史"
                : "注册账号，保存你的旅行规划和偏好"}
            </p>
          </div>

          {/* Toggle tabs */}
          <div className="flex gap-1 p-1 bg-muted/50 rounded-xl mb-6">
            <button
              type="button"
              onClick={() => setView("login")}
              className={`flex-1 py-2.5 text-sm font-medium rounded-lg transition-all ${
                view === "login"
                  ? "bg-card shadow-soft text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              登录
            </button>
            <button
              type="button"
              onClick={() => setView("register")}
              className={`flex-1 py-2.5 text-sm font-medium rounded-lg transition-all ${
                view === "register"
                  ? "bg-card shadow-soft text-foreground"
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
    </div>
  );
}
