"use client";

import React from "react";
import Link from "next/link";
import { ProjectItem } from "../api";
import { Globe, ArrowRight, Bookmark, GitBranch } from "lucide-react";
import { Button } from "@/shared/ui/Button";

interface ProjectCardProps {
  project: ProjectItem;
}

export function ProjectCard({ project }: ProjectCardProps) {
  const formattedDate = project.createdAt
    ? new Date(project.createdAt).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    : "Recently created";

  const testUrl = project.testUrl || project.targetUrl;
  const lastRunStatus = project.lastRunStatus;
  const savedTestCount = project.savedTestCount ?? 0;

  let statusBadgeClass = "bg-cloud text-text-tertiary border-card-border";
  let statusDotClass = "bg-text-tertiary";

  if (lastRunStatus === "completed" || lastRunStatus === "done" || lastRunStatus === "passed") {
    statusBadgeClass = "bg-status-confirmed-bg text-status-confirmed border-status-confirmed/30";
    statusDotClass = "bg-status-confirmed";
  } else if (lastRunStatus === "failed" || lastRunStatus === "cancelled") {
    statusBadgeClass = "bg-status-failed-bg text-status-failed border-status-failed/30";
    statusDotClass = "bg-status-failed";
  } else if (lastRunStatus) {
    statusBadgeClass = "bg-clay-subtle text-clay border-clay/30";
    statusDotClass = "bg-clay";
  }

  return (
    <div className="bg-white border border-card-border rounded-2xl p-6 shadow-xs hover:border-clay/60 hover:shadow-md transition-all flex flex-col justify-between group">
      <div>
        <div className="flex items-start justify-between gap-3 mb-2">
          <Link href={`/projects/${project.id}`} className="min-w-0 flex-1">
            <h3 className="font-heading text-lg font-medium text-text-primary group-hover:text-clay transition-colors truncate">
              {project.name}
            </h3>
          </Link>
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-mono font-medium bg-cloud border border-card-border text-text-secondary shrink-0 uppercase">
            {project.defaultMode}
          </span>
        </div>

        <div className="flex items-center gap-1.5 text-xs text-text-tertiary font-mono mb-3">
          <Globe className="w-3.5 h-3.5 text-text-secondary shrink-0" />
          <span className="truncate">{testUrl}</span>
        </div>

        {project.description && (
          <p className="text-xs text-text-secondary line-clamp-2 mb-4">
            {project.description}
          </p>
        )}

        <div className="flex flex-wrap items-center gap-2 mt-4 pt-3 border-t border-card-border/50 text-xs">
          {/* Last Run Status */}
          <div
            className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[11px] font-medium border ${statusBadgeClass}`}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${statusDotClass}`} />
            <span className="capitalize">{lastRunStatus || "No runs yet"}</span>
          </div>

          {/* Saved Test Count */}
          <div className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[11px] font-medium bg-cloud border border-card-border text-text-secondary">
            <Bookmark className="w-3 h-3 text-clay" />
            <span>{savedTestCount} saved {savedTestCount === 1 ? "test" : "tests"}</span>
          </div>

          {/* GitHub badge if connected */}
          {project.githubUrl && (
            <div className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-mono bg-cloud border border-card-border text-text-secondary">
              <GitBranch className="w-3 h-3 text-text-tertiary" />
              <span className="truncate max-w-[130px]">
                {project.githubUrl.replace(/^https?:\/\/github\.com\//, "")}
              </span>
            </div>
          )}
        </div>
      </div>

      <div className="pt-4 border-t border-card-border/60 flex items-center justify-between mt-5">
        <span className="text-[11px] text-text-tertiary">{formattedDate}</span>

        <Link href={`/projects/${project.id}`}>
          <Button variant="secondary" size="sm" className="gap-1.5 group-hover:bg-cloud">
            <span>Overview</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Button>
        </Link>
      </div>
    </div>
  );
}
