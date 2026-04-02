"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuthStore } from "@/lib/store/auth-store";
import { Mail, Lock, Eye, EyeOff, User } from "lucide-react";

const registerSchema = z
  .object({
    email: z.string().email("请输入有效的邮箱地址"),
    username: z.string().min(2, "用户名至少2个字符").optional(),
    password: z.string().min(6, "密码至少6位"),
    confirmPassword: z.string(),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "两次密码输入不一致",
    path: ["confirmPassword"],
  });

type RegisterFormValues = z.infer<typeof registerSchema>;

interface RegisterFormProps {
  onSuccess?: () => void;
  onSwitchToLogin: () => void;
}

export function RegisterForm({ onSuccess, onSwitchToLogin }: RegisterFormProps) {
  const [error, setError] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const { register: authRegister, isLoading } = useAuthStore();

  const {
    register: registerField,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterFormValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      email: "",
      username: "",
      password: "",
      confirmPassword: "",
    },
  });

  const onSubmit = async (data: RegisterFormValues) => {
    setError(null);
    try {
      const { confirmPassword, ...registerData } = data;
      await authRegister(registerData);
      onSuccess?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "注册失败，请稍后重试");
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="reg-email" className="text-sm font-medium text-foreground/80">邮箱</Label>
        <div className="relative">
          <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/60 z-10" />
          <Input
            id="reg-email"
            type="email"
            placeholder="your@email.com"
            autoComplete="email"
            {...registerField("email")}
            disabled={isLoading}
            className="pl-10 h-11 bg-card/60 border-border/60 rounded-xl focus:ring-primary/30 focus:border-primary/40"
          />
        </div>
        {errors.email && (
          <p className="text-xs text-destructive mt-1">{errors.email.message}</p>
        )}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="username" className="text-sm font-medium text-foreground/80">用户名（可选）</Label>
        <div className="relative">
          <User className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/60 z-10" />
          <Input
            id="username"
            type="text"
            placeholder="给自己起个旅行昵称"
            autoComplete="username"
            {...registerField("username")}
            disabled={isLoading}
            className="pl-10 h-11 bg-card/60 border-border/60 rounded-xl focus:ring-primary/30 focus:border-primary/40"
          />
        </div>
        {errors.username && (
          <p className="text-xs text-destructive mt-1">{errors.username.message}</p>
        )}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="password" className="text-sm font-medium text-foreground/80">密码</Label>
        <div className="relative">
          <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/60 z-10" />
          <Input
            id="password"
            type={showPassword ? "text" : "password"}
            placeholder="至少6位密码"
            autoComplete="new-password"
            {...registerField("password")}
            disabled={isLoading}
            className="pl-10 pr-10 h-11 bg-card/60 border-border/60 rounded-xl focus:ring-primary/30 focus:border-primary/40"
          />
          <button
            type="button"
            onClick={() => setShowPassword(!showPassword)}
            className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-muted-foreground/50 hover:text-muted-foreground transition-colors"
          >
            {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        </div>
        {errors.password && (
          <p className="text-xs text-destructive mt-1">{errors.password.message}</p>
        )}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="confirmPassword" className="text-sm font-medium text-foreground/80">确认密码</Label>
        <div className="relative">
          <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/60 z-10" />
          <Input
            id="confirmPassword"
            type={showConfirm ? "text" : "password"}
            placeholder="再次输入密码"
            autoComplete="new-password"
            {...registerField("confirmPassword")}
            disabled={isLoading}
            className="pl-10 pr-10 h-11 bg-card/60 border-border/60 rounded-xl focus:ring-primary/30 focus:border-primary/40"
          />
          <button
            type="button"
            onClick={() => setShowConfirm(!showConfirm)}
            className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-muted-foreground/50 hover:text-muted-foreground transition-colors"
          >
            {showConfirm ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        </div>
        {errors.confirmPassword && (
          <p className="text-xs text-destructive mt-1">{errors.confirmPassword.message}</p>
        )}
      </div>

      {error && (
        <div className="p-3 rounded-xl bg-red-50/80 border border-red-200/50 text-red-600 text-sm animate-slide-in-up dark:bg-red-900/20 dark:border-red-700/30 dark:text-red-300">
          <div className="flex items-center gap-2">
            <svg className="w-4 h-4 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="8" x2="12" y2="12"/>
              <line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            {error}
          </div>
        </div>
      )}

      <button
        type="submit"
        disabled={isLoading}
        className="w-full h-11 bg-gradient-to-r from-accent to-[hsl(15,65%,52%)] text-white rounded-xl font-semibold text-sm shadow-ember hover:shadow-glow transition-all active:scale-[0.98] disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center gap-2"
      >
        {isLoading ? (
          <>
            <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            注册中...
          </>
        ) : (
          <>
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
              <circle cx="8.5" cy="7" r="4"/>
              <line x1="20" y1="8" x2="20" y2="14"/>
              <line x1="23" y1="11" x2="17" y2="11"/>
            </svg>
            创建账号
          </>
        )}
      </button>

      <div className="text-center text-sm text-muted-foreground">
        已有账号？
        <button
          type="button"
          onClick={onSwitchToLogin}
          className="ml-1 text-primary hover:text-primary/80 font-medium transition-colors"
          disabled={isLoading}
        >
          立即登录
        </button>
      </div>
    </form>
  );
}
