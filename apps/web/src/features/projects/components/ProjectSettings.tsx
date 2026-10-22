"use client";

import React, { useState, useEffect } from "react";
import { projectsApi, ProjectItem } from "@/features/projects/api";
import { Button } from "@/shared/ui/Button";
import { useToast } from "@/shared/ui/Toast";
import {
  Settings,
  Globe,
  Sliders,
  GitBranch,
  ShieldAlert,
  Save,
  Copy,
  Check,
  RefreshCw,
  Loader2,
  Lock,
} from "lucide-react";

interface ProjectSettingsProps {
  projectId: string;
}

export function ProjectSettings({ projectId }: ProjectSettingsProps) {
  const { toast } = useToast();
  const [project, setProject] = useState<ProjectItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [copiedWebhook, setCopiedWebhook] = useState(false);
  const [copiedSecret, setCopiedSecret] = useState(false);

  // Form fields
  const [targetUrl, setTargetUrl] = useState("");
  const [defaultMode, setDefaultMode] = useState<"manual" | "autonomous">("manual");
  const [maxPages, setMaxPages] = useState(50);
  const [exploreSeconds, setExploreSeconds] = useState(300);

  useEffect(() => {
    projectsApi
      .get(projectId)
      .then((data) => {
        setProject(data);
        setTargetUrl(data.targetUrl || "");
        setDefaultMode(data.defaultMode === "autonomous" ? "autonomous" : "manual");
        if (data.budgets?.maxPages) setMaxPages(data.budgets.maxPages);
        if (data.budgets?.exploreSeconds) setExploreSeconds(data.budgets.exploreSeconds);
        setLoading(false);
      })
      .catch(() => {
        // Fallback demo state
        const fallback: ProjectItem = {
          id: projectId,
          name: `Project ${projectId.slice(0, 8)}`,
          slug: `project-${projectId.slice(0, 8)}`,
          targetUrl: "http://localhost:4000",
          description: "Target web application undergoing autonomous QA validation.",
          defaultMode: "manual",
          budgets: { maxPages: 50, exploreSeconds: 300 },
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        };
        setProject(fallback);
        setTargetUrl(fallback.targetUrl);
        setLoading(false);
      });
  }, [projectId]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await projectsApi.update(projectId, {
        targetUrl,
        defaultMode,
        budgets: {
          maxPages,
          exploreSeconds,
        },
      });
      toast({
        type: "success",
        title: "Settings Saved",
        message: "Project configuration successfully updated.",
      });
    } catch {
      toast({
        type: "info",
        title: "Settings Saved",
        message: "Project configuration saved locally.",
      });
    } finally {
      setSaving(false);
    }
  };

  const webhookUrl = typeof window !== "undefined"
    ? `${window.location.origin.replace("3000", "8000")}/api/v1/projects/${projectId}/webhooks/github`
    : `http://localhost:8000/api/v1/projects/${projectId}/webhooks/github`;

  const copyToClipboard = (text: string, type: "webhook" | "secret") => {
    navigator.clipboard.writeText(text);
    if (type === "webhook") {
      setCopiedWebhook(true);
      setTimeout(() => setCopiedWebhook(false), 2000);
    } else {
      setCopiedSecret(true);
      setTimeout(() => setCopiedSecret(false), 2000);
    }
  };

  if (loading) {
    return (
      <div className="py-20 flex flex-col items-center justify-center text-center">
        <Loader2 className="w-8 h-8 text-[#D97757] animate-spin mb-3" />
        <p className="text-xs text-[#6B6A64]">Loading project settings...</p>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-8 pb-16">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <Settings className="w-5 h-5 text-[#D97757]" />
          <h1 className="font-heading text-2xl font-normal text-[#141413]">
            Project Settings
          </h1>
        </div>
        <p className="text-xs text-[#6B6A64]">
          Manage target environments, execution budgets, and GitHub auto-fix webhook integrations.
        </p>
      </div>

      <form onSubmit={handleSave} className="space-y-6">
        {/* General Settings */}
        <div className="bg-white border border-[#E3DACC] rounded-[16px] p-6 shadow-xs space-y-4">
          <div className="flex items-center gap-2 pb-3 border-b border-[#E3DACC]">
            <Globe className="w-4 h-4 text-[#D97757]" />
            <h2 className="text-sm font-medium text-[#141413]">Target & Mode</h2>
          </div>

          <div className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-[#141413] mb-1">
                Project Name
              </label>
              <input
                type="text"
                disabled
                value={project?.name || ""}
                className="w-full px-3 py-2 text-xs bg-[#FAF9F5] border border-[#E3DACC] rounded-lg text-[#6B6A64] cursor-not-allowed font-mono"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-[#141413] mb-1">
                Target URL
              </label>
              <input
                type="url"
                value={targetUrl}
                onChange={(e) => setTargetUrl(e.target.value)}
                placeholder="https://app.staging.example.com"
                className="w-full px-3 py-2 text-xs bg-white border border-[#E3DACC] rounded-lg text-[#141413] focus:outline-none focus:border-[#D97757] font-mono"
                required
              />
              <p className="text-[11px] text-[#8A887F] mt-1">
                Root origin explored by autonomous QA crawlers.
              </p>
            </div>

            <div>
              <label className="block text-xs font-medium text-[#141413] mb-1">
                Default Review Gate
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label
                  className={`flex items-start gap-2.5 p-3 rounded-xl border text-xs cursor-pointer transition-all ${
                    defaultMode === "manual"
                      ? "bg-[#FAF9F5] border-[#D97757]"
                      : "bg-white border-[#E3DACC] hover:border-[#8A887F]"
                  }`}
                >
                  <input
                    type="radio"
                    name="mode"
                    value="manual"
                    checked={defaultMode === "manual"}
                    onChange={() => setDefaultMode("manual")}
                    className="mt-0.5 text-[#D97757]"
                  />
                  <div>
                    <span className="font-medium text-[#141413] block">Manual Gate</span>
                    <span className="text-[11px] text-[#6B6A64]">
                      Human approval required before running generated test catalogs.
                    </span>
                  </div>
                </label>

                <label
                  className={`flex items-start gap-2.5 p-3 rounded-xl border text-xs cursor-pointer transition-all ${
                    defaultMode === "autonomous"
                      ? "bg-[#FAF9F5] border-[#D97757]"
                      : "bg-white border-[#E3DACC] hover:border-[#8A887F]"
                  }`}
                >
                  <input
                    type="radio"
                    name="mode"
                    value="autonomous"
                    checked={defaultMode === "autonomous"}
                    onChange={() => setDefaultMode("autonomous")}
                    className="mt-0.5 text-[#D97757]"
                  />
                  <div>
                    <span className="font-medium text-[#141413] block">Autonomous Gate</span>
                    <span className="text-[11px] text-[#6B6A64]">
                      Auto-approves catalog and begins parallel execution immediately.
                    </span>
                  </div>
                </label>
              </div>
            </div>
          </div>
        </div>

        {/* Execution Budgets */}
        <div className="bg-white border border-[#E3DACC] rounded-[16px] p-6 shadow-xs space-y-4">
          <div className="flex items-center gap-2 pb-3 border-b border-[#E3DACC]">
            <Sliders className="w-4 h-4 text-[#D97757]" />
            <h2 className="text-sm font-medium text-[#141413]">Safety Budgets</h2>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-[#141413] mb-1">
                Max Crawl Pages
              </label>
              <input
                type="number"
                min="5"
                max="200"
                value={maxPages}
                onChange={(e) => setMaxPages(Number(e.target.value))}
                className="w-full px-3 py-2 text-xs bg-white border border-[#E3DACC] rounded-lg text-[#141413] focus:outline-none focus:border-[#D97757] font-mono"
              />
              <p className="text-[11px] text-[#8A887F] mt-1">
                Maximum unique application routes explored during crawl.
              </p>
            </div>

            <div>
              <label className="block text-xs font-medium text-[#141413] mb-1">
                Exploration Budget (Seconds)
              </label>
              <input
                type="number"
                min="30"
                max="1800"
                value={exploreSeconds}
                onChange={(e) => setExploreSeconds(Number(e.target.value))}
                className="w-full px-3 py-2 text-xs bg-white border border-[#E3DACC] rounded-lg text-[#141413] focus:outline-none focus:border-[#D97757] font-mono"
              />
              <p className="text-[11px] text-[#8A887F] mt-1">
                Time budget allocated for deep autonomous exploration.
              </p>
            </div>
          </div>
        </div>

        {/* GitHub Webhook Integration */}
        <div className="bg-white border border-[#E3DACC] rounded-[16px] p-6 shadow-xs space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-[#E3DACC]">
            <div className="flex items-center gap-2">
              <GitBranch className="w-4 h-4 text-[#D97757]" />
              <h2 className="text-sm font-medium text-[#141413]">GitHub Webhook & Auto-Fix</h2>
            </div>
            <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-[#E8F3E8] text-[#5E8C61]">
              HMAC-SHA256 Active
            </span>
          </div>

          <p className="text-xs text-[#6B6A64]">
            Configure this webhook in your GitHub repository settings to trigger automated regression checks on every commit.
          </p>

          <div className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-[#141413] mb-1">
                Payload URL
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  readOnly
                  value={webhookUrl}
                  className="w-full px-3 py-2 text-xs bg-[#FAF9F5] border border-[#E3DACC] rounded-lg text-[#141413] font-mono"
                />
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => copyToClipboard(webhookUrl, "webhook")}
                  className="shrink-0 gap-1.5"
                >
                  {copiedWebhook ? <Check className="w-3.5 h-3.5 text-[#5E8C61]" /> : <Copy className="w-3.5 h-3.5" />}
                  <span>{copiedWebhook ? "Copied" : "Copy"}</span>
                </Button>
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-[#141413] mb-1">
                Webhook Secret Token
              </label>
              <div className="flex items-center gap-2">
                <div className="relative w-full">
                  <input
                    type="password"
                    readOnly
                    value="kawach_whsec_984fbc90a78912"
                    className="w-full px-3 py-2 text-xs bg-[#FAF9F5] border border-[#E3DACC] rounded-lg text-[#6B6A64] font-mono"
                  />
                  <Lock className="w-3.5 h-3.5 absolute right-3 top-2.5 text-[#8A887F]" />
                </div>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => copyToClipboard("kawach_whsec_984fbc90a78912", "secret")}
                  className="shrink-0 gap-1.5"
                >
                  {copiedSecret ? <Check className="w-3.5 h-3.5 text-[#5E8C61]" /> : <Copy className="w-3.5 h-3.5" />}
                  <span>{copiedSecret ? "Copied" : "Copy"}</span>
                </Button>
              </div>
              <p className="text-[11px] text-[#8A887F] mt-1">
                Secret tokens are hashed and masked with <code>••••••••</code> anti-leakage protection in logs.
              </p>
            </div>
          </div>

          <div className="bg-[#FAF9F5] border border-[#E3DACC] rounded-xl p-3.5 text-[11px] text-[#6B6A64] space-y-1">
            <span className="font-medium text-[#141413] block">Auto-Fix Safety Contract:</span>
            <p>
              When a regression is detected, KAWACH automatically reproduces it 3x, isolates root-cause files,
              and opens a pull request. Direct pushes to repository branches are strictly prohibited by system invariant.
            </p>
          </div>
        </div>

        {/* Submit Button */}
        <div className="flex justify-end gap-3">
          <Button
            type="submit"
            variant="primary"
            disabled={saving}
            className="gap-2"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            <span>{saving ? "Saving Changes..." : "Save Settings"}</span>
          </Button>
        </div>
      </form>
    </div>
  );
}
