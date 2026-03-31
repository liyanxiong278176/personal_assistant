"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuthStore } from "@/lib/store/auth-store";

const registerSchema = z
  .object({
    email: z.string().email("请输入有效的邮箱地址"),
    username: z.string().min(2, "用户名至少2个字符").optional(),
    code: z.string().min(6, "验证码至少6位").max(6, "验证码为6位"),
  })
  .refine((data) => data.email && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email), {
    message: "请输入有效的邮箱地址",
    path: ["email"],
  });

type RegisterFormValues = z.infer<typeof registerSchema>;

interface RegisterFormProps {
  onSuccess?: () => void;
  onSwitchToLogin: () => void;
}

export function RegisterForm({ onSuccess, onSwitchToLogin }: RegisterFormProps) {
  const [error, setError] = useState<string | null>(null);
  const [resendDisabled, setResendDisabled] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const { register, sendCode, isLoading } = useAuthStore();

  const {
    register: registerField,
    handleSubmit,
    formState: { errors },
    watch,
  } = useForm<RegisterFormValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      email: "",
      username: "",
      code: "",
    },
  });

  const email = watch("email");

  const onSubmit = async (data: RegisterFormValues) => {
    setError(null);
    try {
      await register(data);
      onSuccess?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "注册失败，请重试");
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
        <Label htmlFor="reg-email">邮箱</Label>
        <Input
          id="reg-email"
          type="email"
          placeholder="your@email.com"
          {...registerField("email")}
          disabled={isLoading}
        />
        {errors.email && (
          <p className="text-sm text-destructive">{errors.email.message}</p>
        )}
      </div>

      <div className="space-y-2">
        <Label htmlFor="username">用户名（可选）</Label>
        <Input
          id="username"
          type="text"
          placeholder="旅行者"
          {...registerField("username")}
          disabled={isLoading}
        />
        {errors.username && (
          <p className="text-sm text-destructive">{errors.username.message}</p>
        )}
      </div>

      <div className="space-y-2">
        <Label htmlFor="reg-code">验证码</Label>
        <div className="flex gap-2">
          <Input
            id="reg-code"
            type="text"
            placeholder="6位验证码"
            maxLength={6}
            {...registerField("code")}
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
        {isLoading ? "注册中..." : "注册"}
      </Button>

      <div className="text-center text-sm text-muted-foreground">
        已有账号？
        <button
          type="button"
          onClick={onSwitchToLogin}
          className="ml-1 text-primary hover:underline"
          disabled={isLoading}
        >
          立即登录
        </button>
      </div>
    </form>
  );
}
