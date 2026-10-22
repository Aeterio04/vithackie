"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import Link from "next/link";
import { authApi } from "@/features/auth/api";
import { useToast } from "@/shared/ui/Toast";
import { Button } from "@/shared/ui/Button";
import { Shield, Eye, EyeOff, Lock, Mail, User, AlertCircle } from "lucide-react";

const RegisterSchema = z.object({
  email: z.string().email("Valid email address required"),
  password: z.string().min(8, "Password must be at least 8 characters"),
  display_name: z.string().optional(),
});
type RegisterFormValues = z.infer<typeof RegisterSchema>;

export function RegisterForm() {
  const router = useRouter();
  const { toast } = useToast();

  const [showPassword, setShowPassword] = useState(false);
  const [isPending, setIsPending] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterFormValues>({
    resolver: zodResolver(RegisterSchema),
    defaultValues: {
      email: "",
      password: "",
      display_name: "",
    },
  });

  const onSubmit = async (data: RegisterFormValues) => {
    setIsPending(true);
    try {
      await authApi.register(data);
      toast({
        type: "success",
        title: "Account created",
        message: "Welcome to KAWACH. Your workspace is ready.",
      });
      router.push("/projects");
      router.refresh();
    } catch (err: any) {
      toast({
        type: "error",
        title: "Registration failed",
        message: err.message || "Failed to create account. Please try again.",
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
      </div>

      {/* Register Card */}
      <div className="bg-white border border-[#E3DACC] rounded-[16px] p-8 shadow-[0_1px_2px_rgba(20,20,19,0.05)]">
        <div className="mb-6">
          <h2 className="text-base font-semibold text-[#141413]">
            Create QA Engineer Account
          </h2>
          <p className="text-xs text-[#6B6A64] mt-0.5">
            Set up an isolated multi-tenant workspace
          </p>
        </div>

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
              Display Name (Optional)
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
