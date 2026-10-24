"use client";

import React from "react";
import Link from "next/link";
import { ProjectItem } from "@/features/projects/api";
import { Button } from "@/shared/ui/Button";
import {
  Globe,
  GitBranch,
  KeyRound,
  Play,
  Bookmark,
  Layers,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
  ArrowRight,
  ExternalLink,
  Settings,
  Shield,
  Bug,
} from "lucide-react";

interface ProjectOverviewTabProps {
  project: ProjectItem;
  latestRun?: any | null;
  savedTestCount: number;
  onGoToSavedTests: () => void;
  onGoToSettings: () => void;
  onGoToRuns: () => void;
}

export function ProjectOverviewTab({
  project,
  latestRun,
  savedTestCount,
  onGoToSavedTests,
  onGoToSettings,
  onGoToRuns,
}: ProjectOverviewTabProps) {
  const targetUrl = project.testUrl || project.targetUrl;
  const passedCount = latestRun?.counts?.passed ?? latestRun?.counts?.passed_tests ?? 0;
  const defectCount = latestRun?.counts?.confirmed ?? latestRun?.counts?.confirmed_bugs ?? 0;
  const totalTests = latestRun?.counts?.tests ?? latestRun?.counts?.total_tests ?? 0;

  const renderStatusBadge = (status?: string, stage?: string) => {
    const s = (status || stage || "not run").toLowerCase();
    if (s === "completed" || s === "passed") {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-mono bg-status-confirmed-bg text-status-confirmed border border-status-confirmed/30 font-medium">
          <CheckCircle2 className="w-3.5 h-3.5" />
          <span>Completed</span>
        </span>
      );
    }
    if (s === "failed") {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-mono bg-status-failed-bg text-status-failed border border-status-failed/30 font-medium">
          <XCircle className="w-3.5 h-3.5" />
          <span>Failed</span>
        </span>
      );
    }
    if (s === "running" || s === "executing") {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-mono bg-clay-subtle text-clay border border-clay/30 font-medium">
          <Clock className="w-3.5 h-3.5 animate-spin" />
          <span>Running</span>
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-mono bg-cloud text-text-secondary border border-card-border font-medium">
        <Clock className="w-3.5 h-3.5" />
        <span>{s}</span>
      </span>
    );
  };

  const formatDuration = (sec?: number | string) => {
    if (sec === undefined || sec === null) return "--";
    const num = typeof sec === "string" ? parseFloat(sec) : sec;
    if (isNaN(num) || num <= 0) return "< 1s";
    const m = Math.floor(num / 60);
    const s = Math.floor(num % 60);
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
  };

  return (
    <div className="space-y-6">
      {/* 3 Metric Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Card 1: Saved Tests */}
        <div className="bg-white border border-card-border rounded-2xl p-5 shadow-xs flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-mono uppercase text-text-tertiary tracking-wider">
                Saved Regression Suite
              </span>
              <Bookmark className="w-4 h-4 text-clay" />
            </div>
            <div className="text-3xl font-heading font-medium text-text-primary">
              {savedTestCount}
            </div>
            <p className="text-xs text-text-secondary mt-1">
              Deterministic Playwright tests run as-is without AI.
            </p>
          </div>
          <div className="mt-4 pt-3 border-t border-card-border flex items-center justify-between">
            <button
              onClick={onGoToSavedTests}
              className="text-xs font-semibold text-clay hover:underline flex items-center gap-1 cursor-pointer"
            >
              <span>Manage & Run Tests</span>
              <ArrowRight className="w-3 h-3" />
            </button>
          </div>
        </div>

        {/* Card 2: Latest Run Status */}
        <div className="bg-white border border-card-border rounded-2xl p-5 shadow-xs flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-mono uppercase text-text-tertiary tracking-wider">
                Latest Test Run
              </span>
              <Layers className="w-4 h-4 text-clay" />
            </div>
            <div className="flex items-center gap-2 mt-1 mb-2">
              {renderStatusBadge(latestRun?.status, latestRun?.stage)}
            </div>
            <p className="text-xs text-text-secondary">
              {latestRun
                ? `Run ID: ${latestRun.runId || latestRun.id} (${formatDuration(
                    latestRun.duration_seconds || latestRun.duration || (latestRun?.budget_usage?.elapsed_minutes ? latestRun.budget_usage.elapsed_minutes * 60 : undefined)
                  )})`
                : "No runs executed for this project yet."}
            </p>
          </div>
          <div className="mt-4 pt-3 border-t border-card-border flex items-center justify-between">
            <button
              onClick={onGoToRuns}
              className="text-xs font-semibold text-clay hover:underline flex items-center gap-1 cursor-pointer"
            >
              <span>View All Runs</span>
              <ArrowRight className="w-3 h-3" />
            </button>
          </div>
        </div>

        {/* Card 3: Pass / Fail Counts */}
        <div className="bg-white border border-card-border rounded-2xl p-5 shadow-xs flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-mono uppercase text-text-tertiary tracking-wider">
                Pass / Defect Ratio
              </span>
              <Shield className="w-4 h-4 text-status-confirmed" />
            </div>
            <div className="flex items-baseline gap-3">
              <span className="text-2xl font-heading font-medium text-status-confirmed">
                {passedCount} Passed
              </span>
              {defectCount > 0 && (
                <span className="text-lg font-heading font-medium text-status-failed">
                  {defectCount} Defects
                </span>
              )}
            </div>
            <p className="text-xs text-text-secondary mt-1">
              From latest run ({totalTests} total test cases executed).
            </p>
          </div>
          <div className="mt-4 pt-3 border-t border-card-border flex items-center justify-between">
            {latestRun ? (
              <Link
                href={`/projects/${project.id}/runs/${latestRun.runId || latestRun.id}/report`}
                className="text-xs font-semibold text-clay hover:underline flex items-center gap-1"
              >
                <span>View Latest Report</span>
                <ArrowRight className="w-3 h-3" />
              </Link>
            ) : (
              <span className="text-xs text-text-tertiary">No data available</span>
            )}
          </div>
        </div>
      </div>

      {/* Project Configuration Summary Card */}
      <div className="bg-white border border-card-border rounded-2xl p-6 shadow-xs space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-heading text-lg font-normal text-text-primary">
            Project Configuration
          </h3>
          <Button
            variant="secondary"
            size="sm"
            onClick={onGoToSettings}
            className="gap-1.5"
          >
            <Settings className="w-3.5 h-3.5" />
            <span>Edit Settings</span>
          </Button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
          <div className="bg-cloud/50 border border-card-border rounded-xl p-4 space-y-2">
            <span className="text-[11px] font-mono uppercase text-text-tertiary">
              Target Test URL
            </span>
            <div className="flex items-center gap-2 text-text-primary font-mono break-all font-medium">
              <Globe className="w-4 h-4 text-clay shrink-0" />
              <a
                href={targetUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="hover:underline flex items-center gap-1 text-clay"
              >
                <span>{targetUrl}</span>
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          </div>

          <div className="bg-cloud/50 border border-card-border rounded-xl p-4 space-y-2">
            <span className="text-[11px] font-mono uppercase text-text-tertiary">
              GitHub Repository & PAT
            </span>
            <div className="flex items-center gap-2 text-text-primary font-mono break-all">
              <GitBranch className="w-4 h-4 text-clay shrink-0" />
              {project.githubUrl ? (
                <div className="flex items-center gap-2">
                  <a
                    href={project.githubUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="hover:underline flex items-center gap-1 text-clay"
                  >
                    <span>{project.githubUrl.replace("https://github.com/", "")}</span>
                    <ExternalLink className="w-3 h-3" />
                  </a>
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-cloud border border-card-border text-text-secondary">
                    {project.patMasked ? "PAT Encrypted" : "Public"}
                  </span>
                </div>
              ) : (
                <span className="text-text-tertiary italic">Not configured</span>
              )}
            </div>
          </div>
        </div>

        {project.description && (
          <div className="pt-2">
            <p className="text-xs text-text-secondary leading-relaxed">
              {project.description}
            </p>
          </div>
        )}
      </div>

      {/* Latest Run Highlights */}
      {latestRun && (
        <div className="bg-white border border-card-border rounded-2xl p-6 shadow-xs space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-heading text-lg font-normal text-text-primary">
                  Latest Run Overview
                </h3>
                <span className="font-mono text-xs font-semibold px-2 py-0.5 rounded bg-cloud border border-card-border text-text-primary">
                  {latestRun.runId || latestRun.id}
                </span>
              </div>
              <p className="text-xs text-text-secondary mt-0.5">
                Executed on{" "}
                {new Date(latestRun.created_at || Date.now()).toLocaleString()}
              </p>
            </div>

            <div className="flex items-center gap-2">
              <Link href={`/projects/${project.id}/runs/${latestRun.runId || latestRun.id}/execution`}>
                <Button variant="secondary" size="sm">
                  Cockpit
                </Button>
              </Link>
              <Link href={`/projects/${project.id}/runs/${latestRun.runId || latestRun.id}/report`}>
                <Button variant="primary" size="sm" className="gap-1">
                  <span>Full Report</span>
                  <ArrowRight className="w-3 h-3" />
                </Button>
              </Link>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
            <div className="bg-cloud/40 border border-card-border rounded-xl p-3">
              <span className="text-[10px] font-mono uppercase text-text-tertiary">
                Total Tests
              </span>
              <p className="text-lg font-heading font-medium text-text-primary mt-1">
                {totalTests}
              </p>
            </div>

            <div className="bg-status-confirmed-bg/40 border border-status-confirmed/30 rounded-xl p-3">
              <span className="text-[10px] font-mono uppercase text-status-confirmed">
                Passed
              </span>
              <p className="text-lg font-heading font-medium text-status-confirmed mt-1">
                {passedCount}
              </p>
            </div>

            <div className="bg-status-failed-bg/40 border border-status-failed/30 rounded-xl p-3">
              <span className="text-[10px] font-mono uppercase text-status-failed">
                Defects
              </span>
              <p className="text-lg font-heading font-medium text-status-failed mt-1">
                {defectCount}
              </p>
            </div>

            <div className="bg-cloud/40 border border-card-border rounded-xl p-3">
              <span className="text-[10px] font-mono uppercase text-text-tertiary">
                Duration
              </span>
              <p className="text-lg font-heading font-medium text-text-primary mt-1">
                {formatDuration(latestRun.duration_seconds || latestRun.duration)}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
