"use client";

import React, { Suspense } from "react";
import { RegisterForm } from "@/features/auth/components/RegisterForm";

export default function RegisterPage() {
  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-[#FAF9F5]">
      <Suspense fallback={<div className="text-xs text-[#6B6A64]">Loading...</div>}>
        <RegisterForm />
      </Suspense>
    </div>
  );
}
