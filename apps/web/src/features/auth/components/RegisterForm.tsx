"use client";

import React, { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import Link from "next/link";
import { authApi } from "@/features/auth/api";
import { useToast } from "@/shared/ui/Toast";
import { Button } from "@/shared/ui/Button";
import { Shield, Eye, EyeOff, Lock, Mail, User, AlertCircle } from "lucide-react";

const RegisterSchema = z
  .object({
    email: z.string().trim().min(1, "Email is required").email("Enter a valid email address"),
    password: z.string().min(8, "Password must be at least 8 characters").max(128, "Password is too long"),
    confirm_password: z.string().min(1, "Please confirm your password"),
    display_name: z.string().optional(),
  })
  .refine((v) => v.password === v.confirm_password, {
    message: "Passwords do not match",
    path: ["confirm_password"],
  });
type RegisterFormValues = z.infer<typeof RegisterSchema>;

export function RegisterForm() {
  const { toast } = useToast();

  const [showPassword, setShowPassword] = useState(false);
  const [isPending, setIsPending] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterFormValues>({
    resolver: zodResolver(RegisterSchema),
    defaultValues: {
      email: "",
      password: "",
      confirm_password: "",
      display_name: "",
    },
  });

  const onSubmit = async (data: RegisterFormValues) => {
    setIsPending(true);
    setFormError(null);
    try {
      // The backend signs the new user in (httpOnly cookie) as part of registration.
      await authApi.register({ email: data.email, password: data.password, name: data.display_name });
      toast({
        type: "success",
        title: "Account created",
        message: "Welcome to KAWACH. Your workspace is ready.",
      });
      // Full navigation (not router.push): Next may have prefetched this route while signed out and cached the
      // redirect to /login; a real page load makes the server see the new session cookie.
      window.location.assign("/projects");
    } catch (err: any) {
      setFormError(
        err?.status === 409
          ? "An account with this email already exists. Try signing in instead."
          : err?.message || "Failed to create account. Please try again."
      );
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
      </div>

      {/* Register Card */}
      <div className="bg-white border border-[#E3DACC] rounded-[16px] p-8 shadow-[0_1px_2px_rgba(20,20,19,0.05)]">
        <div className="mb-6">
          <h2 className="text-base font-semibold text-[#141413]">
            Create your account
          </h2>
          <p className="text-xs text-[#6B6A64] mt-0.5">
            Your projects and runs are private to this account
          </p>
        </div>

        {formError && (
          <div role="alert" className="mb-4 flex items-start gap-2 rounded-xl border border-[#E8C4BE] bg-[#FBEFED] px-3 py-2 text-xs text-[#C4473A]">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{formError}</span>
          </div>
        )}

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {/* Email */}
          <div className="space-y-1.5">
            <label htmlFor="email" className="text-xs font-medium text-[#141413]">
              Work Email
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-[#8A887F]">
                <Mail className="w-4 h-4" />
              </div>
              <input
                id="email"
                type="email"
                placeholder="engineer@company.com"
                autoComplete="email"
                {...register("email")}
                className="w-full pl-9 pr-3 py-2 text-sm bg-[#FAF9F5] border border-[#E3DACC] rounded-xl text-[#141413] placeholder-[#8A887F] focus:outline-none focus:ring-2 focus:ring-[#D97757] focus:bg-white transition-all font-mono"
              />
            </div>
            {errors.email && (
              <div className="flex items-center gap-1 text-[11px] text-[#C4473A] mt-1">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                <span>{errors.email.message}</span>
              </div>
            )}
          </div>

          {/* Display Name */}
          <div className="space-y-1.5">
            <label htmlFor="display_name" className="text-xs font-medium text-[#141413]">
              Name (optional)
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-[#8A887F]">
                <User className="w-4 h-4" />
              </div>
              <input
                id="display_name"
                type="text"
                placeholder="Alex Vance"
                {...register("display_name")}
                className="w-full pl-9 pr-3 py-2 text-sm bg-[#FAF9F5] border border-[#E3DACC] rounded-xl text-[#141413] placeholder-[#8A887F] focus:outline-none focus:ring-2 focus:ring-[#D97757] focus:bg-white transition-all"
              />
            </div>
          </div>

          {/* Password */}
          <div className="space-y-1.5">
            <label htmlFor="password" className="text-xs font-medium text-[#141413]">
              Password
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-[#8A887F]">
                <Lock className="w-4 h-4" />
              </div>
              <input
                id="password"
                type={showPassword ? "text" : "password"}
                placeholder="Min 8 characters"
                autoComplete="new-password"
                {...register("password")}
                className="w-full pl-9 pr-10 py-2 text-sm bg-[#FAF9F5] border border-[#E3DACC] rounded-xl text-[#141413] placeholder-[#8A887F] focus:outline-none focus:ring-2 focus:ring-[#D97757] focus:bg-white transition-all"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute inset-y-0 right-0 pr-3 flex items-center text-[#8A887F] hover:text-[#141413]"
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            {errors.password && (
              <div className="flex items-center gap-1 text-[11px] text-[#C4473A] mt-1">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                <span>{errors.password.message}</span>
              </div>
            )}
          </div>

          {/* Confirm password */}
          <div className="space-y-1.5">
            <label htmlFor="confirm_password" className="text-xs font-medium text-[#141413]">
              Confirm password
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-[#8A887F]">
                <Lock className="w-4 h-4" />
              </div>
              <input
                id="confirm_password"
                type={showPassword ? "text" : "password"}
                placeholder="Repeat your password"
                autoComplete="new-password"
                {...register("confirm_password")}
                className="w-full pl-9 pr-3 py-2 text-sm bg-[#FAF9F5] border border-[#E3DACC] rounded-xl text-[#141413] placeholder-[#8A887F] focus:outline-none focus:ring-2 focus:ring-[#D97757] focus:bg-white transition-all"
              />
            </div>
            {errors.confirm_password && (
              <div className="flex items-center gap-1 text-[11px] text-[#C4473A] mt-1">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                <span>{errors.confirm_password.message}</span>
              </div>
            )}
          </div>

          <Button
            type="submit"
            variant="primary"
            className="w-full justify-center py-2.5 mt-2"
            disabled={isPending}
          >
            {isPending ? "Creating account..." : "Create account"}
          </Button>
        </form>

        <div className="mt-6 pt-4 border-t border-[#E3DACC]/60 text-center text-xs text-[#6B6A64]">
          Already have an account?{" "}
          <Link href="/login" className="text-[#D97757] hover:underline font-medium">
            Sign in
          </Link>
        </div>
      </div>
    </div>
  );
}
