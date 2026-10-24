"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { projectsApi } from "../api";
import { useToast } from "@/shared/ui/Toast";
import { Button } from "@/shared/ui/Button";
import {
  Globe,
  Folder,
  AlignLeft,
  AlertCircle,
  GitBranch,
  KeyRound,
  Eye,
  EyeOff,
  Lock,
} from "lucide-react";

const NewProjectSchema = z.object({
  name: z.string().min(2, "Project name must be at least 2 characters"),
  testUrl: z.string().url("Must be a valid URL with http:// or https://"),
  githubUrl: z
    .string()
    .optional()
    .refine(
      (val) => !val || val.startsWith("https://github.com/") || val.includes("/"),
      "Must be a valid GitHub repository URL (e.g. https://github.com/org/repo)"
    ),
  pat: z.string().optional(),
  description: z.string().optional(),
  defaultMode: z.enum(["manual", "autonomous"]),
});

type NewProjectValues = z.infer<typeof NewProjectSchema>;

export function NewProjectForm() {
  const router = useRouter();
  const { toast } = useToast();
  const [isPending, setIsPending] = useState(false);
  const [showPat, setShowPat] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<NewProjectValues>({
    resolver: zodResolver(NewProjectSchema),
    defaultValues: {
      name: "",
      testUrl: "http://localhost:4000",
      githubUrl: "",
      pat: "",
      description: "",
      defaultMode: "manual",
    },
  });

  const onSubmit = async (data: NewProjectValues) => {
    setIsPending(true);
    try {
      const created = await projectsApi.create({
        name: data.name,
        targetUrl: data.testUrl,
        testUrl: data.testUrl,
        githubUrl: data.githubUrl ? data.githubUrl.trim() : undefined,
        pat: data.pat ? data.pat.trim() : undefined,
        description: data.description,
        defaultMode: data.defaultMode,
      });

      toast({
        type: "success",
        title: "Project created",
        message: `Project "${created.name}" is ready for testing.`,
      });

      router.push(`/projects/${created.id}`);
      router.refresh();
    } catch (err: any) {
      toast({
        type: "error",
        title: "Failed to create project",
        message: err.message || "An unexpected error occurred.",
      });
    } finally {
      setIsPending(false);
    }
  };

  return (
    <div className="bg-white border border-card-border rounded-2xl p-6 shadow-xs max-w-2xl">
      <div className="mb-6 pb-4 border-b border-card-border">
        <h2 className="font-heading text-xl font-normal text-text-primary">
          Create New QA Project
        </h2>
        <p className="text-xs text-text-secondary mt-0.5">
          Configure application under test, optional GitHub integration, and testing defaults.
        </p>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
        {/* Project Name */}
        <div className="space-y-1.5">
          <label htmlFor="name" className="text-xs font-medium text-text-primary">
            Project Name <span className="text-status-failed">*</span>
          </label>
          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-text-tertiary">
              <Folder className="w-4 h-4" />
            </div>
            <input
              id="name"
              type="text"
              placeholder="e.g. Acme Web Store"
              {...register("name")}
              className="w-full pl-9 pr-3 py-2 text-sm bg-cloud/50 border border-card-border rounded-xl text-text-primary placeholder:text-text-tertiary focus:outline-none focus:ring-2 focus:ring-clay focus:bg-white transition-all"
            />
          </div>
          {errors.name && (
            <div className="flex items-center gap-1 text-[11px] text-status-failed mt-1">
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
              <span>{errors.name.message}</span>
            </div>
          )}
        </div>

        {/* Test Target URL */}
        <div className="space-y-1.5">
          <label htmlFor="testUrl" className="text-xs font-medium text-text-primary">
            Test URL (Application Base URL) <span className="text-status-failed">*</span>
          </label>
          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-text-tertiary">
              <Globe className="w-4 h-4" />
            </div>
            <input
              id="testUrl"
              type="text"
              placeholder="http://localhost:4000 or https://staging.myapp.com"
              {...register("testUrl")}
              className="w-full pl-9 pr-3 py-2 text-sm bg-cloud/50 border border-card-border rounded-xl text-text-primary placeholder:text-text-tertiary focus:outline-none focus:ring-2 focus:ring-clay focus:bg-white transition-all font-mono"
            />
          </div>
          {errors.testUrl && (
            <div className="flex items-center gap-1 text-[11px] text-status-failed mt-1">
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
              <span>{errors.testUrl.message}</span>
            </div>
          )}
        </div>

        {/* GitHub Link & PAT Section */}
        <div className="p-4 rounded-xl border border-card-border bg-cloud/30 space-y-4">
          <div className="flex items-center gap-2 pb-2 border-b border-card-border">
            <GitBranch className="w-4 h-4 text-clay" />
            <div>
              <h3 className="text-xs font-medium text-text-primary">
                GitHub Integration (Optional)
              </h3>
              <p className="text-[11px] text-text-secondary">
                Link your repository to inspect recent commits and trigger commit-aware regressions.
              </p>
            </div>
          </div>

          {/* GitHub URL */}
          <div className="space-y-1.5">
            <label htmlFor="githubUrl" className="text-xs font-medium text-text-primary">
              GitHub Repository URL
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-text-tertiary">
                <GitBranch className="w-4 h-4" />
              </div>
              <input
                id="githubUrl"
                type="text"
                placeholder="https://github.com/org/repo"
                {...register("githubUrl")}
                className="w-full pl-9 pr-3 py-2 text-sm bg-white border border-card-border rounded-xl text-text-primary placeholder:text-text-tertiary focus:outline-none focus:ring-2 focus:ring-clay transition-all font-mono"
              />
            </div>
            {errors.githubUrl && (
              <div className="flex items-center gap-1 text-[11px] text-status-failed mt-1">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                <span>{errors.githubUrl.message}</span>
              </div>
            )}
          </div>

          {/* Personal Access Token (PAT) */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label htmlFor="pat" className="text-xs font-medium text-text-primary flex items-center gap-1.5">
                <KeyRound className="w-3.5 h-3.5 text-text-tertiary" />
                <span>GitHub Personal Access Token (PAT)</span>
              </label>
              <div className="flex items-center gap-1 text-[10px] text-status-confirmed">
                <Lock className="w-3 h-3" />
                <span>Encrypted at rest</span>
              </div>
            </div>
            <div className="relative">
              <input
                id="pat"
                type={showPat ? "text" : "password"}
                placeholder="ghp_••••••••••••••••••••••••••••••••"
                {...register("pat")}
                className="w-full pl-3 pr-10 py-2 text-sm bg-white border border-card-border rounded-xl text-text-primary placeholder:text-text-tertiary focus:outline-none focus:ring-2 focus:ring-clay transition-all font-mono"
              />
              <button
                type="button"
                onClick={() => setShowPat(!showPat)}
                className="absolute inset-y-0 right-0 pr-3 flex items-center text-text-tertiary hover:text-text-primary cursor-pointer"
              >
                {showPat ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            <p className="text-[11px] text-text-tertiary">
              Stored securely with Fernet symmetric encryption and never returned in plaintext to the browser.
            </p>
          </div>
        </div>

        {/* Description */}
        <div className="space-y-1.5">
          <label htmlFor="description" className="text-xs font-medium text-text-primary">
            Description (Optional)
          </label>
          <div className="relative">
            <div className="absolute top-2.5 left-0 pl-3 flex items-center pointer-events-none text-text-tertiary">
              <AlignLeft className="w-4 h-4" />
            </div>
            <textarea
              id="description"
              rows={3}
              placeholder="Primary web application undergoing autonomous QA validation and regression verification."
              {...register("description")}
              className="w-full pl-9 pr-3 py-2 text-sm bg-cloud/50 border border-card-border rounded-xl text-text-primary placeholder:text-text-tertiary focus:outline-none focus:ring-2 focus:ring-clay focus:bg-white transition-all"
            />
          </div>
        </div>

        {/* Mode Selector */}
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-text-primary">
            Default Execution Mode
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="flex items-center gap-2 p-3 rounded-xl border border-card-border bg-cloud/30 cursor-pointer hover:bg-white transition-colors">
              <input
                type="radio"
                value="manual"
                {...register("defaultMode")}
                className="text-clay focus:ring-clay"
              />
              <div>
                <span className="text-xs font-medium text-text-primary block">
                  Manual Directed
                </span>
                <span className="text-[10px] text-text-secondary block">
                  Targeted exploratory tests
                </span>
              </div>
            </label>
            <label className="flex items-center gap-2 p-3 rounded-xl border border-card-border bg-cloud/30 cursor-pointer hover:bg-white transition-colors">
              <input
                type="radio"
                value="autonomous"
                {...register("defaultMode")}
                className="text-clay focus:ring-clay"
              />
              <div>
                <span className="text-xs font-medium text-text-primary block">
                  Autonomous
                </span>
                <span className="text-[10px] text-text-secondary block">
                  Full automatic crawl & defect proof
                </span>
              </div>
            </label>
          </div>
        </div>

        {/* Submit */}
        <div className="pt-2 flex items-center justify-end gap-3">
          <Button
            type="button"
            variant="secondary"
            onClick={() => router.back()}
            disabled={isPending}
          >
            Cancel
          </Button>
          <Button
            type="submit"
            variant="primary"
            disabled={isPending}
          >
            {isPending ? "Creating..." : "Create Project"}
          </Button>
        </div>
      </form>
    </div>
  );
}
