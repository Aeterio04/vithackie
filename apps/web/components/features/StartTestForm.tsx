"use client";

import React, { useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  useConfigDefaults,
  useTargetCheck,
  useUploadSpec,
  useCreateRun,
  useStartRun,
  useProjects,
} from "@/lib/api/hooks";
import { useUiStore } from "@/lib/store/uiStore";
import { useToast } from "@/components/ui/Toast";
import { Button } from "@/components/ui/Button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/Tabs";
import { FileDropzone } from "@/components/ui/FileDropzone";
import { Checkbox } from "@/components/ui/Checkbox";
import {
  Link as LinkIcon,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Lock,
  ChevronDown,
  ChevronUp,
  Sliders,
  Eye,
  EyeOff,
  Sparkles,
  FolderKanban,
} from "lucide-react";

const StartFormSchema = z.object({
  project_id: z.string().optional(),
  target_url: z
    .string()
    .min(1, "Target URL is required")
    .url("Must be a valid URL with http:// or https://"),
  prompt: z.string().min(1, "Please provide a plain-English test objective"),
  spec_text: z.string().optional(),
  username: z.string().optional(),
  password: z.string().optional(),
  review_mode: z.enum(["manual", "autonomous"]),
  max_pages: z.number().min(1).max(100),
  max_steps_per_test: z.number().min(5).max(100),
  max_run_minutes: z.number().min(1).max(60),
  parallel_workers: z.number().min(1).max(4),
  is_authorized: z.boolean().refine((val) => val === true, {
    message: "You must confirm you are authorized to test this target",
  }),
});

type StartFormValues = z.infer<typeof StartFormSchema>;

interface StartTestFormProps {
  onSuccess?: (runId: string) => void;
  className?: string;
  defaultProjectId?: string;
}

export function StartTestForm({ onSuccess, className, defaultProjectId }: StartTestFormProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const paramProjectId = searchParams.get("projectId") || defaultProjectId || "";

  const { toast } = useToast();
  const { setSelectedRunId } = useUiStore();
  const { data: config } = useConfigDefaults();
  const { data: projects = [], isLoading: isLoadingProjects } = useProjects();

  const [specFile, setSpecFile] = useState<File | null>(null);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [showBudgets, setShowBudgets] = useState(false);
  const [submissionStep, setSubmissionStep] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    control,
    formState: { errors },
  } = useForm<StartFormValues>({
    resolver: zodResolver(StartFormSchema),
    defaultValues: {
      project_id: paramProjectId,
      target_url: "",
      prompt: "",
      spec_text: "",
      username: "",
      password: "",
      review_mode: "manual",
      max_pages: 20,
      max_steps_per_test: 30,
      max_run_minutes: 15,
      parallel_workers: 2,
      is_authorized: false,
    },
  });

  // Apply default config when loaded
  useEffect(() => {
    if (config?.default_budgets) {
      setValue("max_pages", config.default_budgets.max_pages);
      setValue("max_steps_per_test", config.default_budgets.max_steps_per_test);
      setValue("max_run_minutes", config.default_budgets.max_run_minutes);
      setValue("parallel_workers", config.default_budgets.parallel_workers);
    }
  }, [config, setValue]);

  // Pre-fill target_url if project is selected or given via query param
  useEffect(() => {
    const selectedPid = paramProjectId || watch("project_id");
    if (selectedPid && projects && projects.length > 0) {
      setValue("project_id", selectedPid);
      const proj = projects.find((p: any) => p.id === selectedPid);
      if (proj) {
        const url = proj.targetUrl || proj.testUrl || proj.target_url;
        if (url && !watch("target_url")) {
          setValue("target_url", url, { shouldValidate: true });
        }
        if (proj.defaultMode || proj.default_mode) {
          setValue("review_mode", (proj.defaultMode || proj.default_mode) as any);
        }
      }
    }
  }, [paramProjectId, projects, setValue, watch]);


  const watchedTargetUrl = watch("target_url");
  const watchedReviewMode = watch("review_mode");

  // Pre-flight target check
  const {
    mutate: checkTarget,
    data: checkResult,
    isPending: isCheckingTarget,
    reset: resetTargetCheck,
  } = useTargetCheck();

  const handleCheckTarget = () => {
    if (!watchedTargetUrl) return;
    try {
      new URL(watchedTargetUrl);
      checkTarget({ target_url: watchedTargetUrl });
    } catch {
      toast({
        type: "error",
        title: "Invalid URL",
        message: "Please enter a valid URL including http:// or https://",
      });
    }
  };

  // Pipeline mutations
  const { mutateAsync: uploadSpec } = useUploadSpec();
  const { mutateAsync: createRun } = useCreateRun();
  const { mutateAsync: startRun } = useStartRun();

  const isFormSubmitting = Boolean(submissionStep);

  const onSubmit = async (data: StartFormValues) => {
    // Ensure target was verified and not blocked
    if (checkResult && !checkResult.allowed) {
      toast({
        type: "error",
        title: "Target blocked",
        message:
          checkResult.reason ||
          "Target is blocked by the allowlist. Only authorized staging/local domains are allowed.",
      });
      return;
    }

    try {
      let uploadedSpecId: string | undefined = undefined;

      // 1. Upload spec if file or text provided
      if (specFile) {
        setSubmissionStep("Uploading spec file...");
        const res = await uploadSpec({
          file: specFile,
          onProgress: (p) => setUploadProgress(p),
        });
        uploadedSpecId = res.spec_id;
      } else if (data.spec_text && data.spec_text.trim()) {
        setSubmissionStep("Saving spec text...");
        const res = await uploadSpec({
          spec_text: data.spec_text.trim(),
        });
        uploadedSpecId = res.spec_id;
      }

      // 2. Create Run
      setSubmissionStep("Creating test run...");
      const created = await createRun({
        project_id: data.project_id || undefined,
        target_url: data.target_url,
        prompt: data.prompt,
        spec_id: uploadedSpecId,
        spec_text: uploadedSpecId ? undefined : data.spec_text,
        review_mode: data.review_mode,
        budgets: {
          max_pages: data.max_pages,
          max_steps_per_test: data.max_steps_per_test,
          max_run_minutes: data.max_run_minutes,
          parallel_workers: data.parallel_workers,
        },
        credentials:
          data.username || data.password
            ? {
                username: data.username,
                password: data.password,
              }
            : undefined,
      });

      // 3. Start Run pipeline
      setSubmissionStep("Initializing Explorer & Planner agents...");
      await startRun(created.id);

      setSelectedRunId(created.id);

      toast({
        type: "success",
        title: "Test run started",
        message: `Pipeline active for ${data.target_url}`,
      });

      // Clear password field immediately after submit for security
      setValue("password", "");
      setSubmissionStep(null);
      setUploadProgress(null);
      setSpecFile(null);
      resetTargetCheck();

      if (onSuccess) {
        onSuccess(created.id);
      } else {
        router.push(`/execution/${created.id}`);
      }
    } catch (err: unknown) {
      setSubmissionStep(null);
      setUploadProgress(null);
      const message =
        err instanceof Error
          ? err.message
          : "Failed to initialize test run. Please check target connectivity.";
      toast({
        type: "error",
        title: "Start failed",
        message,
        action: {
          label: "Retry",
          onClick: () => onSubmit(data),
        },
      });
    }
  };

  const isTargetBlocked = checkResult ? !checkResult.allowed : false;

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      className={`bg-white border border-[#E3DACC] rounded-[16px] p-6 shadow-[0_1px_2px_rgba(20,20,19,0.05)] space-y-6 ${className || ""}`}
    >
      {/* 0. Project Selector Dropdown */}
      <div className="space-y-2">
        <label
          htmlFor="project-select"
          className="text-xs font-semibold text-[#141413] flex items-center justify-between"
        >
          <span className="flex items-center gap-1.5">
            <FolderKanban className="w-3.5 h-3.5 text-[#D97757]" />
            <span>Link to Project</span>
          </span>
          <span className="text-[11px] font-normal text-[#8A887F]">
            {projects && projects.length > 0
              ? `${projects.length} project${projects.length > 1 ? "s" : ""} available`
              : "No projects created yet"}
          </span>
        </label>

        <div className="relative">
          <select
            id="project-select"
            {...register("project_id")}
            onChange={(e) => {
              register("project_id").onChange(e);
              const pId = e.target.value;
              if (pId && projects && projects.length > 0) {
                const selected = projects.find((p: any) => p.id === pId);
                if (selected) {
                  const pUrl = selected.targetUrl || selected.testUrl || selected.target_url;
                  if (pUrl) {
                    setValue("target_url", pUrl, { shouldValidate: true });
                    if (checkResult) resetTargetCheck();
                  }
                  if (selected.defaultMode || selected.default_mode) {
                    setValue("review_mode", (selected.defaultMode || selected.default_mode) as any);
                  }
                }
              }
            }}
            className="w-full h-11 px-3.5 py-2.5 text-xs bg-[#FAF9F5] border border-[#E3DACC] rounded-xl text-[#141413] focus:outline-none focus:ring-2 focus:ring-[#D97757] focus:bg-white transition-all cursor-pointer font-sans appearance-none pr-9"
          >
            <option value="">-- None (Standalone Run) --</option>
            {projects.map((proj: any) => (
              <option key={proj.id} value={proj.id}>
                {proj.name} ({proj.targetUrl || proj.testUrl || proj.target_url || "No URL"})
              </option>
            ))}
          </select>
          <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none text-[#8A887F]">
            <ChevronDown className="w-4 h-4" />
          </div>
        </div>
      </div>

      {/* 1. Target URL + Pre-flight Check */}
      <div className="space-y-2">
        <label
          htmlFor="target-url-input"
          className="text-xs font-semibold text-[#141413] flex items-center justify-between"
        >
          <span>Application Target URL</span>
          <span className="text-[11px] font-normal text-[#8A887F]">
            Staging, preview, or local environments only
          </span>
        </label>

        <div className="flex gap-2">
          <div className="relative flex-1">
            <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-[#8A887F]">
              <LinkIcon className="w-4 h-4" />
            </div>
            <input
              id="target-url-input"
              type="url"
              placeholder="https://staging.yourapp.com"
              {...register("target_url")}
              onChange={(e) => {
                register("target_url").onChange(e);
                if (checkResult) resetTargetCheck();
              }}
              className="w-full pl-10 pr-3 py-2.5 text-sm bg-[#FAF9F5] border border-[#E3DACC] rounded-xl text-[#141413] placeholder-[#8A887F] font-mono focus:outline-none focus:ring-2 focus:ring-[#D97757] focus:bg-white transition-all"
            />
          </div>

          <Button
            type="button"
            variant="secondary"
            size="md"
            onClick={handleCheckTarget}
            isLoading={isCheckingTarget}
            disabled={!watchedTargetUrl || isFormSubmitting}
            className="shrink-0"
          >
            Check target
          </Button>
        </div>

        {errors.target_url && (
          <p className="text-xs text-[#C4473A] flex items-center gap-1 mt-1">
            <AlertCircle className="w-3.5 h-3.5" />
            <span>{errors.target_url.message}</span>
          </p>
        )}

        {/* Pre-flight Check Feedback */}
        {checkResult && (
          <div
            className={`p-3 rounded-xl border text-xs flex flex-col sm:flex-row sm:items-center justify-between gap-2 transition-all ${
              checkResult.allowed && checkResult.reachable
                ? "bg-[#EBF2EB] border-[#D2E3D3] text-[#47704A]"
                : "bg-[#FAEBE9] border-[#F2CAC5] text-[#B83E31]"
            }`}
          >
            <div className="flex items-center gap-2">
              {checkResult.allowed && checkResult.reachable ? (
                <CheckCircle2 className="w-4 h-4 shrink-0 text-[#5E8C61]" />
              ) : (
                <XCircle className="w-4 h-4 shrink-0 text-[#C4473A]" />
              )}
              <span>
                {checkResult.reachable ? "Reachable" : "Unreachable"} •{" "}
                {checkResult.allowed ? "Allowed target" : "Blocked by allowlist"}
                {checkResult.reason ? `: ${checkResult.reason}` : ""}
              </span>
            </div>

            <div className="flex items-center gap-2 text-[11px] font-mono">
              <span>
                TLS: {checkResult.tls_valid ? "Valid" : "Not verified"}
              </span>
              {checkResult.status_code && (
                <span>HTTP {checkResult.status_code}</span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* 2. Plain-English Prompt */}
      <div className="space-y-1.5">
        <label
          htmlFor="prompt-input"
          className="text-xs font-semibold text-[#141413] flex items-center justify-between"
        >
          <span>Plain-English Testing Prompt</span>
          <span className="text-[11px] font-normal text-[#8A887F]">
            Instruct the Explorer & Planner agents
          </span>
        </label>
        <textarea
          id="prompt-input"
          rows={3}
          placeholder="Test sign-up, user onboarding flow, and password reset for functional bugs and edge-case validation."
          {...register("prompt")}
          className="w-full px-3.5 py-2.5 text-sm bg-[#FAF9F5] border border-[#E3DACC] rounded-xl text-[#141413] placeholder-[#8A887F] focus:outline-none focus:ring-2 focus:ring-[#D97757] focus:bg-white transition-all leading-relaxed"
        />
        {errors.prompt && (
          <p className="text-xs text-[#C4473A] flex items-center gap-1 mt-1">
            <AlertCircle className="w-3.5 h-3.5" />
            <span>{errors.prompt.message}</span>
          </p>
        )}
      </div>

      {/* 3. Spec: Tabs Upload and Paste text */}
      <div className="space-y-2">
        <label className="text-xs font-semibold text-[#141413] flex items-center justify-between">
          <span>Feature Specification (Optional)</span>
          <span className="text-[11px] font-normal text-[#8A887F]">
            Linked to test catalog and coverage metrics
          </span>
        </label>

        <Tabs defaultValue="upload" className="w-full">
          <TabsList className="mb-2">
            <TabsTrigger value="upload">Upload File</TabsTrigger>
            <TabsTrigger value="paste">Paste Text</TabsTrigger>
          </TabsList>

          <TabsContent value="upload">
            <FileDropzone
              selectedFile={specFile}
              onFileSelect={(f) => setSpecFile(f)}
              acceptedExtensions={config?.accepted_spec_extensions}
              maxSizeMb={config?.max_spec_file_size_mb}
              uploadProgress={uploadProgress}
              disabled={isFormSubmitting}
            />
          </TabsContent>

          <TabsContent value="paste">
            <textarea
              rows={4}
              placeholder="Paste Markdown, OpenAPI spec, PRD, or acceptance criteria here..."
              {...register("spec_text")}
              className="w-full px-3.5 py-2.5 text-xs font-mono bg-[#FAF9F5] border border-[#E3DACC] rounded-xl text-[#141413] placeholder-[#8A887F] focus:outline-none focus:ring-2 focus:ring-[#D97757] focus:bg-white transition-all"
            />
          </TabsContent>
        </Tabs>
      </div>

      {/* 4. Target App Credentials (Optional) */}
      <div className="p-4 rounded-xl border border-[#E3DACC] bg-[#FAF9F5]/50 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs font-semibold text-[#141413]">
            <Lock className="w-4 h-4 text-[#8A887F]" />
            <span>Target App Credentials (Optional)</span>
          </div>
          <span className="text-[11px] text-[#8A887F]">
            For gated staging areas
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className="text-[11px] text-[#6B6A64]">Username</label>
            <input
              type="text"
              placeholder="test_user"
              autoComplete="off"
              {...register("username")}
              className="w-full px-3 py-1.5 text-xs bg-white border border-[#E3DACC] rounded-lg text-[#141413] font-mono focus:outline-none focus:ring-1 focus:ring-[#D97757]"
            />
          </div>

          <div className="space-y-1">
            <label className="text-[11px] text-[#6B6A64]">Password</label>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                placeholder="••••••••"
                autoComplete="off"
                {...register("password")}
                className="w-full pl-3 pr-8 py-1.5 text-xs bg-white border border-[#E3DACC] rounded-lg text-[#141413] focus:outline-none focus:ring-1 focus:ring-[#D97757]"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute inset-y-0 right-0 pr-2 flex items-center text-[#8A887F] hover:text-[#141413] cursor-pointer"
              >
                {showPassword ? (
                  <EyeOff className="w-3.5 h-3.5" />
                ) : (
                  <Eye className="w-3.5 h-3.5" />
                )}
              </button>
            </div>
          </div>
        </div>

        <p className="text-[11px] text-[#8A887F] italic leading-tight">
          Credentials are never sent to the AI model. CAPTCHA and 2FA are not
          supported in V1.
        </p>
      </div>

      {/* 5. Review Mode Segmented Control */}
      <div className="space-y-2">
        <label className="text-xs font-semibold text-[#141413]">
          Review Gate Mode
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label
            onClick={() => setValue("review_mode", "manual")}
            className={`border rounded-xl p-3.5 flex items-start gap-3 cursor-pointer transition-all ${
              watchedReviewMode === "manual"
                ? "border-[#D97757] bg-[#F6EDE8]/40 shadow-xs"
                : "border-[#E3DACC] bg-[#FAF9F5] hover:bg-[#F0EEE6]/50"
            }`}
          >
            <input
              type="radio"
              value="manual"
              {...register("review_mode")}
              className="mt-0.5 text-[#D97757] focus:ring-[#D97757]"
            />
            <div>
              <p className="text-xs font-semibold text-[#141413]">
                Manual (Human review)
              </p>
              <p className="text-[11px] text-[#6B6A64] mt-0.5 leading-snug">
                Execution pauses after Planner creates the test catalog. You
                approve, edit, or reject tests.
              </p>
            </div>
          </label>

          <label
            onClick={() => setValue("review_mode", "autonomous")}
            className={`border rounded-xl p-3.5 flex items-start gap-3 cursor-pointer transition-all ${
              watchedReviewMode === "autonomous"
                ? "border-[#D97757] bg-[#F6EDE8]/40 shadow-xs"
                : "border-[#E3DACC] bg-[#FAF9F5] hover:bg-[#F0EEE6]/50"
            }`}
          >
            <input
              type="radio"
              value="autonomous"
              {...register("review_mode")}
              className="mt-0.5 text-[#D97757] focus:ring-[#D97757]"
            />
            <div>
              <p className="text-xs font-semibold text-[#141413]">
                Autonomous (Reviewer agent)
              </p>
              <p className="text-[11px] text-[#6B6A64] mt-0.5 leading-snug">
                Reviewer agent inspects and filters test catalog autonomously
                against your prompt & spec.
              </p>
            </div>
          </label>
        </div>
      </div>

      {/* 6. Run Budgets Collapsible Section */}
      <div className="border border-[#E3DACC] rounded-xl overflow-hidden">
        <button
          type="button"
          onClick={() => setShowBudgets(!showBudgets)}
          className="w-full px-4 py-3 bg-[#FAF9F5] flex items-center justify-between text-xs font-semibold text-[#141413] hover:bg-[#F0EEE6] transition-colors cursor-pointer"
        >
          <div className="flex items-center gap-2">
            <Sliders className="w-4 h-4 text-[#D97757]" />
            <span>Run Budgets & Worker Configuration</span>
          </div>
          {showBudgets ? (
            <ChevronUp className="w-4 h-4 text-[#8A887F]" />
          ) : (
            <ChevronDown className="w-4 h-4 text-[#8A887F]" />
          )}
        </button>

        {showBudgets && (
          <div className="p-4 grid grid-cols-2 sm:grid-cols-4 gap-4 bg-white border-t border-[#E3DACC]">
            <div>
              <label className="text-[11px] text-[#6B6A64] block mb-1">
                Max Pages
              </label>
              <input
                type="number"
                {...register("max_pages", { valueAsNumber: true })}
                className="w-full px-2.5 py-1.5 text-xs bg-[#FAF9F5] border border-[#E3DACC] rounded-lg font-mono"
              />
            </div>

            <div>
              <label className="text-[11px] text-[#6B6A64] block mb-1">
                Steps per Test
              </label>
              <input
                type="number"
                {...register("max_steps_per_test", { valueAsNumber: true })}
                className="w-full px-2.5 py-1.5 text-xs bg-[#FAF9F5] border border-[#E3DACC] rounded-lg font-mono"
              />
            </div>

            <div>
              <label className="text-[11px] text-[#6B6A64] block mb-1">
                Max Run Minutes
              </label>
              <input
                type="number"
                {...register("max_run_minutes", { valueAsNumber: true })}
                className="w-full px-2.5 py-1.5 text-xs bg-[#FAF9F5] border border-[#E3DACC] rounded-lg font-mono"
              />
            </div>

            <div>
              <label className="text-[11px] text-[#6B6A64] block mb-1">
                Workers (1-4)
              </label>
              <input
                type="number"
                min={1}
                max={4}
                {...register("parallel_workers", { valueAsNumber: true })}
                className="w-full px-2.5 py-1.5 text-xs bg-[#FAF9F5] border border-[#E3DACC] rounded-lg font-mono"
              />
            </div>
          </div>
        )}
      </div>

      {/* 7. Authorization Checkbox (Required) */}
      <div className="space-y-1">
        <label className="flex items-start gap-2.5 cursor-pointer">
          <Controller
            name="is_authorized"
            control={control}
            render={({ field }) => (
              <Checkbox
                id="is_authorized"
                checked={field.value}
                onCheckedChange={field.onChange}
                className="mt-0.5"
              />
            )}
          />
          <span className="text-xs text-[#141413] leading-snug">
            I confirm that I am authorized to test this application target and
            understand that KAWACH executes sandboxed browser interactions.
          </span>
        </label>
        {errors.is_authorized && (
          <p className="text-xs text-[#C4473A] flex items-center gap-1 pl-6">
            <AlertCircle className="w-3.5 h-3.5" />
            <span>{errors.is_authorized.message}</span>
          </p>
        )}
      </div>

      {/* 8. Large Clay 'Start Testing' Button */}
      <div>
        <Button
          type="submit"
          variant="primary"
          size="lg"
          className="w-full text-base py-3 font-semibold shadow-md gap-2"
          disabled={isFormSubmitting || isTargetBlocked}
          isLoading={isFormSubmitting}
        >
          {isFormSubmitting ? (
            <span>{submissionStep}</span>
          ) : (
            <>
              <Sparkles className="w-5 h-5 stroke-[2]" />
              <span>Start Testing Pipeline</span>
            </>
          )}
        </Button>
      </div>
    </form>
  );
}
