"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { projectsApi, ProjectItem } from "@/features/projects/api";
import { Button } from "@/shared/ui/Button";
import { useToast } from "@/shared/ui/Toast";
import {
  Settings,
  Globe,
  Sliders,
  GitBranch,
  Save,
  Trash2,
  KeyRound,
  Eye,
  EyeOff,
  Lock,
  Loader2,
  AlertTriangle,
} from "lucide-react";

interface ProjectSettingsProps {
  projectId: string;
}

export function ProjectSettings({ projectId }: ProjectSettingsProps) {
  const router = useRouter();
  const { toast } = useToast();
  const [project, setProject] = useState<ProjectItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showPat, setShowPat] = useState(false);

  // Form fields
  const [name, setName] = useState("");
  const [testUrl, setTestUrl] = useState("");
  const [githubUrl, setGithubUrl] = useState("");
  const [pat, setPat] = useState("");
  const [description, setDescription] = useState("");
  const [defaultMode, setDefaultMode] = useState<"manual" | "autonomous">("manual");

  useEffect(() => {
    projectsApi
      .get(projectId)
      .then((data) => {
        setProject(data);
        setName(data.name || "");
        setTestUrl(data.testUrl || data.targetUrl || "");
        setGithubUrl(data.githubUrl || "");
        setDescription(data.description || "");
        setDefaultMode(data.defaultMode === "autonomous" ? "autonomous" : "manual");
        setLoading(false);
      })
      .catch((err) => {
        toast({
          type: "error",
          title: "Failed to load project",
          message: err.message || "Could not retrieve settings.",
        });
        setLoading(false);
      });
  }, [projectId, toast]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      toast({ type: "error", title: "Project name is required" });
      return;
    }
    if (!testUrl.trim()) {
      toast({ type: "error", title: "Target URL is required" });
      return;
    }

    setSaving(true);
    try {
      const updated = await projectsApi.update(projectId, {
        name: name.trim(),
        targetUrl: testUrl.trim(),
        testUrl: testUrl.trim(),
        githubUrl: githubUrl.trim() || undefined,
        pat: pat.trim() || undefined,
        description: description.trim() || undefined,
        defaultMode,
      });

      setProject(updated);
      setPat(""); // reset pat input
      toast({
        type: "success",
        title: "Settings Saved",
        message: "Project configuration was updated successfully.",
      });
    } catch (err: any) {
      toast({
        type: "error",
        title: "Save Failed",
        message: err.message || "Could not update project settings.",
      });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await projectsApi.delete(projectId);
      toast({
        type: "success",
        title: "Project Deleted",
        message: `Project "${project?.name || projectId}" was deleted.`,
      });
      router.push("/projects");
      router.refresh();
    } catch (err: any) {
      toast({
        type: "error",
        title: "Delete Failed",
        message: err.message || "Could not delete project.",
      });
      setDeleting(false);
      setShowDeleteConfirm(false);
    }
  };

  if (loading) {
    return (
      <div className="py-20 flex flex-col items-center justify-center text-center">
        <Loader2 className="w-8 h-8 text-clay animate-spin mb-3" />
        <p className="text-xs text-text-secondary">Loading project settings...</p>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-8 pb-16">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <Settings className="w-5 h-5 text-clay" />
          <h1 className="font-heading text-2xl font-normal text-text-primary">
            Project Settings
          </h1>
        </div>
        <p className="text-xs text-text-secondary">
          Update test target URL, GitHub repository connection, Personal Access Token (PAT), or remove project.
        </p>
      </div>

      <form onSubmit={handleSave} className="space-y-6">
        {/* General Application Configuration */}
        <div className="bg-white border border-card-border rounded-2xl p-6 shadow-xs space-y-4">
          <div className="flex items-center gap-2 pb-3 border-b border-card-border">
            <Globe className="w-4 h-4 text-clay" />
            <h2 className="text-sm font-medium text-text-primary">Target Application</h2>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-text-primary mb-1">
                Project Name <span className="text-status-failed">*</span>
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full px-3 py-2 text-sm bg-cloud/40 border border-card-border rounded-xl text-text-primary focus:outline-none focus:ring-2 focus:ring-clay focus:bg-white transition-all"
                placeholder="Project Name"
                required
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-text-primary mb-1">
                Target Test URL <span className="text-status-failed">*</span>
              </label>
              <input
                type="text"
                value={testUrl}
                onChange={(e) => setTestUrl(e.target.value)}
                className="w-full px-3 py-2 text-sm bg-cloud/40 border border-card-border rounded-xl text-text-primary font-mono focus:outline-none focus:ring-2 focus:ring-clay focus:bg-white transition-all"
                placeholder="http://localhost:4000 or https://example.com"
                required
              />
              <p className="text-[11px] text-text-tertiary mt-1">
                The base URL of the target application to test against.
              </p>
            </div>

            <div>
              <label className="block text-xs font-medium text-text-primary mb-1">
                Description
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
                className="w-full px-3 py-2 text-sm bg-cloud/40 border border-card-border rounded-xl text-text-primary focus:outline-none focus:ring-2 focus:ring-clay focus:bg-white transition-all"
                placeholder="Add an optional description for this project..."
              />
            </div>
          </div>
        </div>

        {/* GitHub & PAT Integration */}
        <div className="bg-white border border-card-border rounded-2xl p-6 shadow-xs space-y-4">
          <div className="flex items-center gap-2 pb-3 border-b border-card-border">
            <GitBranch className="w-4 h-4 text-clay" />
            <h2 className="text-sm font-medium text-text-primary">GitHub Integration & PAT</h2>
          </div>

          <p className="text-xs text-text-secondary leading-relaxed">
            Link a GitHub repository to enable automatic commit tracking, diff-aware regressions, and pull request integration.
          </p>

          <div className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-text-primary mb-1">
                GitHub Repository URL
              </label>
              <input
                type="text"
                value={githubUrl}
                onChange={(e) => setGithubUrl(e.target.value)}
                className="w-full px-3 py-2 text-sm bg-cloud/40 border border-card-border rounded-xl text-text-primary font-mono focus:outline-none focus:ring-2 focus:ring-clay focus:bg-white transition-all"
                placeholder="https://github.com/organization/repository"
              />
            </div>

            <div className="p-4 rounded-xl border border-card-border bg-cloud/30 space-y-3">
              <div className="flex items-center justify-between">
                <label className="text-xs font-medium text-text-primary flex items-center gap-1.5">
                  <KeyRound className="w-3.5 h-3.5 text-text-tertiary" />
                  <span>Personal Access Token (PAT)</span>
                </label>
                {project?.patMasked ? (
                  <span className="inline-flex items-center gap-1 text-[11px] font-mono text-status-confirmed bg-status-confirmed-bg px-2 py-0.5 rounded border border-status-confirmed/30">
                    <Lock className="w-3 h-3" />
                    <span>Configured: {project.patMasked}</span>
                  </span>
                ) : (
                  <span className="text-[11px] text-text-tertiary italic">
                    Not configured
                  </span>
                )}
              </div>

              <div className="relative">
                <input
                  type={showPat ? "text" : "password"}
                  value={pat}
                  onChange={(e) => setPat(e.target.value)}
                  className="w-full pl-3 pr-10 py-2 text-sm bg-white border border-card-border rounded-xl text-text-primary placeholder:text-text-tertiary focus:outline-none focus:ring-2 focus:ring-clay transition-all font-mono"
                  placeholder={project?.patMasked ? "Enter new token to replace existing PAT" : "ghp_••••••••••••••••••••••••••••••••"}
                />
                <button
                  type="button"
                  onClick={() => setShowPat(!showPat)}
                  className="absolute inset-y-0 right-0 pr-3 flex items-center text-text-tertiary hover:text-text-primary cursor-pointer"
                >
                  {showPat ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>

              <p className="text-[11px] text-text-tertiary leading-relaxed">
                PAT is stored encrypted with Fernet symmetric keys and never returned to the frontend in plaintext.
              </p>
            </div>
          </div>
        </div>

        {/* Test Run Configuration */}
        <div className="bg-white border border-card-border rounded-2xl p-6 shadow-xs space-y-4">
          <div className="flex items-center gap-2 pb-3 border-b border-card-border">
            <Sliders className="w-4 h-4 text-clay" />
            <h2 className="text-sm font-medium text-text-primary">Execution Mode Defaults</h2>
          </div>

          <div>
            <label className="block text-xs font-medium text-text-primary mb-2">
              Default Mode
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label
                className={`flex items-center gap-2 p-3 rounded-xl border cursor-pointer transition-all ${
                  defaultMode === "manual"
                    ? "border-clay bg-clay-subtle"
                    : "border-card-border bg-cloud/30 hover:bg-white"
                }`}
              >
                <input
                  type="radio"
                  name="defaultMode"
                  value="manual"
                  checked={defaultMode === "manual"}
                  onChange={() => setDefaultMode("manual")}
                  className="text-clay focus:ring-clay"
                />
                <div>
                  <span className="text-xs font-medium text-text-primary block">
                    Manual Directed
                  </span>
                  <span className="text-[10px] text-text-secondary block">
                    User guides exploration scope
                  </span>
                </div>
              </label>

              <label
                className={`flex items-center gap-2 p-3 rounded-xl border cursor-pointer transition-all ${
                  defaultMode === "autonomous"
                    ? "border-clay bg-clay-subtle"
                    : "border-card-border bg-cloud/30 hover:bg-white"
                }`}
              >
                <input
                  type="radio"
                  name="defaultMode"
                  value="autonomous"
                  checked={defaultMode === "autonomous"}
                  onChange={() => setDefaultMode("autonomous")}
                  className="text-clay focus:ring-clay"
                />
                <div>
                  <span className="text-xs font-medium text-text-primary block">
                    Autonomous Mode
                  </span>
                  <span className="text-[10px] text-text-secondary block">
                    Full automatic exploration & defect proof
                  </span>
                </div>
              </label>
            </div>
          </div>
        </div>

        {/* Save Changes Button */}
        <div className="flex items-center justify-end gap-3 pt-2">
          <Button
            type="submit"
            variant="primary"
            disabled={saving}
            className="gap-2"
          >
            {saving ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            <span>{saving ? "Saving Changes..." : "Save Project Settings"}</span>
          </Button>
        </div>
      </form>

      {/* Danger Zone: Delete Project */}
      <div className="bg-status-failed-bg/30 border border-status-failed/30 rounded-2xl p-6 space-y-4">
        <div className="flex items-center gap-2 text-status-failed pb-3 border-b border-status-failed/20">
          <AlertTriangle className="w-5 h-5 shrink-0" />
          <h2 className="text-sm font-semibold text-text-primary">Danger Zone</h2>
        </div>

        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h3 className="text-xs font-semibold text-text-primary">
              Delete This Project
            </h3>
            <p className="text-xs text-text-secondary mt-0.5 max-w-lg">
              Once deleted, all runs, saved test suites, and defect artifacts associated with this project will be removed.
            </p>
          </div>

          <Button
            variant="danger"
            size="sm"
            onClick={() => setShowDeleteConfirm(true)}
            className="gap-1.5 shrink-0"
          >
            <Trash2 className="w-4 h-4" />
            <span>Delete Project</span>
          </Button>
        </div>

        {/* Confirmation Modal */}
        {showDeleteConfirm && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
            <div className="bg-white border border-card-border rounded-2xl p-6 max-w-md w-full shadow-xl space-y-4 animate-in fade-in zoom-in-95 duration-150">
              <div className="w-10 h-10 rounded-full bg-status-failed-bg flex items-center justify-center text-status-failed mx-auto">
                <AlertTriangle className="w-5 h-5" />
              </div>

              <div className="text-center">
                <h3 className="font-heading text-lg font-medium text-text-primary mb-1">
                  Confirm Project Deletion
                </h3>
                <p className="text-xs text-text-secondary">
                  Are you sure you want to delete{" "}
                  <strong className="text-text-primary">{project?.name}</strong>? This action cannot be undone.
                </p>
              </div>

              <div className="flex items-center justify-end gap-3 pt-2">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setShowDeleteConfirm(false)}
                  disabled={deleting}
                >
                  Cancel
                </Button>
                <Button
                  variant="danger"
                  size="sm"
                  onClick={handleDelete}
                  disabled={deleting}
                  className="gap-1.5"
                >
                  {deleting ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Trash2 className="w-3.5 h-3.5" />
                  )}
                  <span>{deleting ? "Deleting..." : "Permanently Delete"}</span>
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
