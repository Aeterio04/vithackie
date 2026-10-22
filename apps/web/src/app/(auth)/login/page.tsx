"use client";

import React, { Suspense } from "react";
import { LoginForm } from "@/features/auth/components/LoginForm";

export default function LoginPage() {
  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-[#FAF9F5]">
      <Suspense fallback={<div className="text-xs text-[#6B6A64]">Loading...</div>}>
        <LoginForm />
      </Suspense>
    </div>
  );
}
