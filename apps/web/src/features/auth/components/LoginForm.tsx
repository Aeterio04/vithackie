"use client";

import React, { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import Link from "next/link";
import { authApi } from "@/features/auth/api";
import { useToast } from "@/shared/ui/Toast";
import { Button } from "@/shared/ui/Button";
import { Shield, Eye, EyeOff, Lock, User, AlertCircle } from "lucide-react";

const LoginSchema = z.object({
  username_or_email: z.string().min(1, "Username or email is required"),
  password: z.string().min(1, "Password is required"),
});
type LoginFormValues = z.infer<typeof LoginSchema>;

export function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const returnUrl = searchParams.get("returnUrl") || "/projects";
  const { toast } = useToast();

  const [showPassword, setShowPassword] = useState(false);
  const [isPending, setIsPending] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(LoginSchema),
    defaultValues: {
      username_or_email: "",
      password: "",
    },
  });

  const onSubmit = async (data: LoginFormValues) => {
    setIsPending(true);
    try {
      await authApi.login(data);
      toast({
        type: "success",
        title: "Authenticated successfully",
        message: "Welcome to KAWACH QA Pipeline.",
      });
      router.push(returnUrl);
      router.refresh();
    } catch (err: any) {
      toast({
        type: "error",
        title: "Authentication failed",
        message: err.message || "Invalid credentials. Please verify and retry.",
      });
    } finally {
      setIsPending(false);
    }
  };

  return (
    <div className="w-full max-w-md">
      {/* Wordmark Header */}
      <div className="text-center mb-8">
        <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-white border border-[#E3DACC] shadow-xs text-[#D97757] mb-3">
          <Shield className="w-7 h-7 fill-[#D97757]/15 stroke-[1.75]" />
        </div>
        <h1 className="font-heading text-3xl font-normal text-[#141413] tracking-tight">
          KAWACH
        </h1>
        <p className="text-xs font-mono text-[#8A887F] uppercase tracking-widest mt-0.5">
          Autonomous QA Testing Agent
        </p>
        <p className="text-sm text-[#6B6A64] italic mt-2">
          &ldquo;It doesn&apos;t just report bugs. It proves them.&rdquo;
        </p>
      </div>

      {/* Login Card */}
      <div className="bg-white border border-[#E3DACC] rounded-[16px] p-8 shadow-[0_1px_2px_rgba(20,20,19,0.05)]">
        <div className="mb-6">
          <h2 className="text-base font-semibold text-[#141413]">
            Sign in to your instance
          </h2>
          <p className="text-xs text-[#6B6A64] mt-0.5">
            Enter your test engineer or team credentials
          </p>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {/* Username or Email */}
          <div className="space-y-1.5">
            <label
              htmlFor="username_or_email"
              className="text-xs font-medium text-[#141413]"
            >
              Username or Email
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-[#8A887F]">
                <User className="w-4 h-4" />
              </div>
              <input
                id="username_or_email"
                type="text"
                placeholder="engineer@company.com"
                autoComplete="username"
                {...register("username_or_email")}
                className="w-full pl-9 pr-3 py-2 text-sm bg-[#FAF9F5] border border-[#E3DACC] rounded-xl text-[#141413] placeholder-[#8A887F] focus:outline-none focus:ring-2 focus:ring-[#D97757] focus:bg-white transition-all font-mono"
              />
            </div>
            {errors.username_or_email && (
              <div className="flex items-center gap-1 text-[11px] text-[#C4473A] mt-1">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                <span>{errors.username_or_email.message}</span>
              </div>
            )}
          </div>

          {/* Password */}
          <div className="space-y-1.5">
            <label
              htmlFor="password"
              className="text-xs font-medium text-[#141413]"
            >
              Password
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-[#8A887F]">
                <Lock className="w-4 h-4" />
              </div>
              <input
                id="password"
                type={showPassword ? "text" : "password"}
                placeholder="••••••••"
                autoComplete="current-password"
                {...register("password")}
                className="w-full pl-9 pr-10 py-2 text-sm bg-[#FAF9F5] border border-[#E3DACC] rounded-xl text-[#141413] placeholder-[#8A887F] focus:outline-none focus:ring-2 focus:ring-[#D97757] focus:bg-white transition-all"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute inset-y-0 right-0 pr-3 flex items-center text-[#8A887F] hover:text-[#141413]"
              >
                {showPassword ? (
                  <EyeOff className="w-4 h-4" />
                ) : (
                  <Eye className="w-4 h-4" />
                )}
              </button>
            </div>
            {errors.password && (
              <div className="flex items-center gap-1 text-[11px] text-[#C4473A] mt-1">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                <span>{errors.password.message}</span>
              </div>
            )}
          </div>

          <Button
            type="submit"
            variant="primary"
            className="w-full justify-center py-2.5 mt-2"
            disabled={isPending}
          >
            {isPending ? "Signing in..." : "Sign in"}
          </Button>
        </form>

        <div className="mt-6 pt-4 border-t border-[#E3DACC]/60 text-center text-xs text-[#6B6A64]">
          Don&apos;t have an account?{" "}
          <Link href="/register" className="text-[#D97757] hover:underline font-medium">
            Register here
          </Link>
        </div>
      </div>
    </div>
  );
}
