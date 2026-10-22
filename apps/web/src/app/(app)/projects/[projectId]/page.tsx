"use client";

import React, { useEffect, useState, use } from "react";
import Link from "next/link";
import { projectsApi, ProjectItem } from "@/features/projects/api";
import { useRuns } from "@/shared/lib/api/hooks";
import { Button } from "@/shared/ui/Button";
import { Stepper } from "@/shared/ui/Stepper";
import {
  Globe,
  Play,
  Bookmark,
  GitCommit,
  Settings,
  ArrowRight,
  Shield,
  Loader2,
  Calendar,
} from "lucide-react";

interface ProjectOverviewPageProps {
  params: Promise<{ projectId: string }>;
}

export default function ProjectOverviewPage({ params }: ProjectOverviewPageProps) {
  const { projectId } = use(params);
  const [project, setProject] = useState<ProjectItem | null>(null);
  const [loadingProject, setLoadingProject] = useState(true);
  const { data: runs, isLoading: loadingRuns } = useRuns();

  useEffect(() => {
    projectsApi
      .get(projectId)
      .then((data) => {
        setProject(data);
        setLoadingProject(false);
      })
      .catch(() => {
        // Fallback for demo / legacy project id
        setProject({
          id: projectId,
          name: `Project ${projectId.slice(0, 8)}`,
          slug: `project-${projectId.slice(0, 8)}`,
          targetUrl: "http://localhost:4000",
          description: "Target web application undergoing autonomous QA validation.",
          defaultMode: "manual",
          budgets: {},
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        });
        setLoadingProject(false);
      });
  }, [projectId]);

  if (loadingProject) {
    return (
      <div className="py-20 flex flex-col items-center justify-center text-center">
        <Loader2 className="w-8 h-8 text-[#D97757] animate-spin mb-3" />
        <p className="text-xs text-[#6B6A64]">Loading project overview...</p>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto py-4 space-y-8">
      {/* Project Banner */}
      <div className="bg-white border border-[#E3DACC] rounded-[16px] p-6 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <h1 className="font-heading text-2xl font-normal text-[#141413]">
              {project?.name}
            </h1>
            <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-[#FAF9F5] border border-[#E3DACC] text-[#6B6A64]">
              {project?.defaultMode}
            </span>
          </div>
          <div className="flex items-center gap-2 text-xs text-[#6B6A64] font-mono">
            <Globe className="w-3.5 h-3.5" />
            <span>{project?.targetUrl}</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Link href={`/projects/${projectId}/tests`}>
            <Button variant="secondary" size="sm" className="gap-1.5">
              <Bookmark className="w-3.5 h-3.5" />
              <span>Saved Tests</span>
            </Button>
          </Link>
          <Link href={`/projects/${projectId}/commits`}>
            <Button variant="secondary" size="sm" className="gap-1.5">
              <GitCommit className="w-3.5 h-3.5" />
              <span>Commits</span>
            </Button>
          </Link>
          <Link href={`/projects/${projectId}/settings`}>
            <Button variant="secondary" size="sm" className="gap-1.5">
              <Settings className="w-3.5 h-3.5" />
              <span>Settings</span>
            </Button>
          </Link>
          <Link href="/projects/new">
            <Button variant="primary" size="sm" className="gap-1.5">
              <Play className="w-3.5 h-3.5" />
              <span>New Run</span>
            </Button>
          </Link>
        </div>
      </div>

      {/* Runs History */}
      <div className="space-y-4">
        <div>
          <h2 className="font-heading text-xl font-normal text-[#141413]">
            Test Runs
          </h2>
          <p className="text-xs text-[#6B6A64] mt-0.5">
            Historical autonomous runs, review gates, and 3x verified defects.
          </p>
        </div>

        {loadingRuns ? (
          <div className="py-12 text-center text-xs text-[#6B6A64]">
            Loading run history...
          </div>
        ) : !runs || runs.length === 0 ? (
          <div className="bg-white border border-[#E3DACC] rounded-[16px] p-8 text-center">
            <p className="text-xs text-[#6B6A64] mb-4">No test runs recorded yet.</p>
            <Link href="/projects/new">
              <Button variant="primary" size="sm">Launch First Run</Button>
            </Link>
          </div>
        ) : (
          <div className="space-y-3">
            {runs.map((r: any) => (
              <div
                key={r.runId}
                className="bg-white border border-[#E3DACC] rounded-xl p-4 shadow-xs hover:border-[#D97757]/60 transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-4"
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-medium text-[#141413]">
                      {r.runId}
                    </span>
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-[#FAF9F5] border border-[#E3DACC] text-[#6B6A64]">
                      {r.mode}
                    </span>
                    {r.golden && (
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-[#E8F3E8] text-[#5E8C61]">
                        Golden
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 text-[11px] text-[#8A887F]">
                    <span>Stage: {r.stage}</span>
                    <span>Tests: {r.counts?.tests || 0}</span>
                    <span>Confirmed Bugs: {r.counts?.confirmed || 0}</span>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <Link href={`/projects/${projectId}/runs/${r.runId}/execution`}>
                    <Button variant="secondary" size="sm">
                      Cockpit
                    </Button>
                  </Link>
                  <Link href={`/projects/${projectId}/runs/${r.runId}/results`}>
                    <Button variant="secondary" size="sm">
                      Results
                    </Button>
                  </Link>
                  <Link href={`/projects/${projectId}/runs/${r.runId}/report`}>
                    <Button variant="primary" size="sm" className="gap-1">
                      <span>Report</span>
                      <ArrowRight className="w-3 h-3" />
                    </Button>
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
