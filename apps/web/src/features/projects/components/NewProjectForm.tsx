"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { projectsApi, CreateProjectPayload } from "../api";
import { useToast } from "@/shared/ui/Toast";
import { Button } from "@/shared/ui/Button";
import { Globe, Folder, AlignLeft, ShieldCheck, AlertCircle } from "lucide-react";

const NewProjectSchema = z.object({
  name: z.string().min(2, "Project name must be at least 2 characters"),
  targetUrl: z.string().url("Must be a valid URL with http:// or https://"),
  description: z.string().optional(),
  defaultMode: z.enum(["manual", "autonomous"]),
});
type NewProjectValues = z.infer<typeof NewProjectSchema>;


export function NewProjectForm() {
  const router = useRouter();
  const { toast } = useToast();
  const [isPending, setIsPending] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<NewProjectValues>({
    resolver: zodResolver(NewProjectSchema),
    defaultValues: {
      name: "",
      targetUrl: "http://localhost:4000",
      description: "",
      defaultMode: "manual",
    },
  });

  const onSubmit = async (data: NewProjectValues) => {
    setIsPending(true);
    try {
      const created = await projectsApi.create(data as CreateProjectPayload);
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
    <div className="bg-white border border-[#E3DACC] rounded-[16px] p-6 shadow-xs max-w-2xl">
      <div className="mb-6 pb-4 border-b border-[#E3DACC]/60">
        <h2 className="font-heading text-xl font-normal text-[#141413]">
          Create New QA Project
        </h2>
        <p className="text-xs text-[#6B6A64] mt-0.5">
          Define the target web application, default testing parameters, and budgets.
        </p>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
        {/* Project Name */}
        <div className="space-y-1.5">
          <label htmlFor="name" className="text-xs font-medium text-[#141413]">
            Project Name
          </label>
          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-[#8A887F]">
              <Folder className="w-4 h-4" />
            </div>
            <input
              id="name"
              type="text"
              placeholder="e.g. Acme Web Store"
              {...register("name")}
              className="w-full pl-9 pr-3 py-2 text-sm bg-[#FAF9F5] border border-[#E3DACC] rounded-xl text-[#141413] placeholder-[#8A887F] focus:outline-none focus:ring-2 focus:ring-[#D97757] focus:bg-white transition-all"
            />
          </div>
          {errors.name && (
            <div className="flex items-center gap-1 text-[11px] text-[#C4473A] mt-1">
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
              <span>{errors.name.message}</span>
            </div>
          )}
        </div>

        {/* Target URL */}
        <div className="space-y-1.5">
          <label htmlFor="targetUrl" className="text-xs font-medium text-[#141413]">
            Target Application Base URL
          </label>
          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-[#8A887F]">
              <Globe className="w-4 h-4" />
            </div>
            <input
              id="targetUrl"
              type="text"
              placeholder="http://localhost:4000"
              {...register("targetUrl")}
              className="w-full pl-9 pr-3 py-2 text-sm bg-[#FAF9F5] border border-[#E3DACC] rounded-xl text-[#141413] placeholder-[#8A887F] focus:outline-none focus:ring-2 focus:ring-[#D97757] focus:bg-white transition-all font-mono"
            />
          </div>
          {errors.targetUrl && (
            <div className="flex items-center gap-1 text-[11px] text-[#C4473A] mt-1">
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
              <span>{errors.targetUrl.message}</span>
            </div>
          )}
        </div>

        {/* Description */}
        <div className="space-y-1.5">
          <label htmlFor="description" className="text-xs font-medium text-[#141413]">
            Description (Optional)
          </label>
          <div className="relative">
            <div className="absolute top-2.5 left-0 pl-3 flex items-center pointer-events-none text-[#8A887F]">
              <AlignLeft className="w-4 h-4" />
            </div>
            <textarea
              id="description"
              rows={3}
              placeholder="Primary e-commerce catalog and checkout flow."
              {...register("description")}
              className="w-full pl-9 pr-3 py-2 text-sm bg-[#FAF9F5] border border-[#E3DACC] rounded-xl text-[#141413] placeholder-[#8A887F] focus:outline-none focus:ring-2 focus:ring-[#D97757] focus:bg-white transition-all"
            />
          </div>
        </div>

        {/* Mode Selector */}
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-[#141413]">
            Default Execution Mode
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="flex items-center gap-2 p-3 rounded-xl border border-[#E3DACC] bg-[#FAF9F5] cursor-pointer hover:bg-white">
              <input
                type="radio"
                value="manual"
                {...register("defaultMode")}
                className="text-[#D97757] focus:ring-[#D97757]"
              />
              <div>
                <span className="text-xs font-medium text-[#141413] block">Manual Mode</span>
                <span className="text-[11px] text-[#6B6A64] block">Human review gate before scripting</span>
              </div>
            </label>
            <label className="flex items-center gap-2 p-3 rounded-xl border border-[#E3DACC] bg-[#FAF9F5] cursor-pointer hover:bg-white">
              <input
                type="radio"
                value="autonomous"
                {...register("defaultMode")}
                className="text-[#D97757] focus:ring-[#D97757]"
              />
              <div>
                <span className="text-xs font-medium text-[#141413] block">Autonomous Mode</span>
                <span className="text-[11px] text-[#6B6A64] block">Autonomous Reviewer agent approves tests</span>
              </div>
            </label>
          </div>
        </div>

        <div className="pt-4 flex items-center justify-end gap-3 border-t border-[#E3DACC]/60">
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
            className="gap-2"
          >
            <ShieldCheck className="w-4 h-4" />
            <span>{isPending ? "Creating..." : "Create Project"}</span>
          </Button>
        </div>
      </form>
    </div>
  );
}
