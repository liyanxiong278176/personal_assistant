"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuthStore } from "@/lib/store/auth-store";

const loginSchema = z.object({
  email: z.string().email("请输入有效的邮箱地址"),
  code: z.string().min(6, "验证码至少6位").max(6, "验证码为6位"),
});

type LoginFormValues = z.infer<typeof loginSchema>;

interface LoginFormProps {
  onSuccess?: () => void;
  onSwitchToRegister: () => void;
}

export function LoginForm({ onSuccess, onSwitchToRegister }: LoginFormProps) {
  const [error, setError] = useState<string | null>(null);
  const [resendDisabled, setResendDisabled] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const { login, sendCode, isLoading } = useAuthStore();

  const {
    register,
    handleSubmit,
    formState: { errors },
    watch,
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      email: "",
      code: "",
    },
  });

  const email = watch("email");

  const onSubmit = async (data: LoginFormValues) => {
    setError(null);
    try {
      await login(data);
      onSuccess?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败，请重试");
    }
  };

  const handleSendCode = async () => {
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setError("请先输入有效的邮箱地址");
      return;
    }

    setError(null);
    try {
      await sendCode({ email });
      setResendDisabled(true);
      setCountdown(60);

      const timer = setInterval(() => {
        setCountdown((prev) => {
          if (prev <= 1) {
            clearInterval(timer);
            setResendDisabled(false);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "发送验证码失败，请重试");
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="email">邮箱</Label>
        <Input
          id="email"
          type="email"
          placeholder="your@email.com"
          {...register("email")}
          disabled={isLoading}
        />
        {errors.email && (
          <p className="text-sm text-destructive">{errors.email.message}</p>
        )}
      </div>

      <div className="space-y-2">
        <Label htmlFor="code">验证码</Label>
        <div className="flex gap-2">
          <Input
            id="code"
            type="text"
            placeholder="6位验证码"
            maxLength={6}
            {...register("code")}
            disabled={isLoading}
            className="flex-1"
          />
          <Button
            type="button"
            variant="outline"
            onClick={handleSendCode}
            disabled={resendDisabled || isLoading}
            className="whitespace-nowrap"
          >
            {countdown > 0 ? `${countdown}秒后重发` : "发送验证码"}
          </Button>
        </div>
        {errors.code && (
          <p className="text-sm text-destructive">{errors.code.message}</p>
        )}
      </div>

      {error && (
        <div className="p-3 rounded-md bg-destructive/10 text-destructive text-sm">
          {error}
        </div>
      )}

      <Button type="submit" className="w-full" disabled={isLoading}>
        {isLoading ? "登录中..." : "登录"}
      </Button>

      <div className="text-center text-sm text-muted-foreground">
        还没有账号？
        <button
          type="button"
          onClick={onSwitchToRegister}
          className="ml-1 text-primary hover:underline"
          disabled={isLoading}
        >
          立即注册
        </button>
      </div>
    </form>
  );
}
