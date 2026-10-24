"use client";

import React, { useEffect, useState, use, Suspense } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import {
  projectsApi,
  ProjectItem,
  ProjectOverviewTab,
  SavedTestsTab,
  TestRunsTab,
  CommitsTab,
  ProjectSettings,
} from "@/features/projects";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/shared/ui/Tabs";
import { Button } from "@/shared/ui/Button";
import {
  Globe,
  Play,
  Bookmark,
  Layers,
  GitCommit,
  Settings,
  ArrowLeft,
  Loader2,
  ExternalLink,
  Shield,
  LayoutDashboard,
} from "lucide-react";

interface ProjectPageProps {
  params: Promise<{ projectId: string }>;
}

function ProjectPageContent({ projectId }: { projectId: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialTab = searchParams.get("tab") || "overview";

  const [activeTab, setActiveTab] = useState(initialTab);
  const [project, setProject] = useState<ProjectItem | null>(null);
  const [runs, setRuns] = useState<any[]>([]);
  const [savedTestCount, setSavedTestCount] = useState<number>(0);
  const [loading, setLoading] = useState(true);

  // Sync tab with URL query parameter if it changes
  useEffect(() => {
    const tabFromUrl = searchParams.get("tab");
    if (tabFromUrl && tabFromUrl !== activeTab) {
      setActiveTab(tabFromUrl);
    }
  }, [searchParams, activeTab]);

  const handleTabChange = (newTab: string) => {
    setActiveTab(newTab);
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", newTab);
    router.replace(`/projects/${projectId}?${params.toString()}`);
  };

  useEffect(() => {
    async function loadData() {
      try {
        const [projectData, runsData, testsData] = await Promise.all([
          projectsApi.get(projectId),
          projectsApi.getProjectRuns(projectId).catch(() => []),
          projectsApi.getSavedTests(projectId).catch(() => []),
        ]);

        setProject(projectData);
        setRuns(runsData || []);
        setSavedTestCount(testsData?.length ?? projectData.savedTestCount ?? 0);
      } catch (err) {
        // Fallback demo object if project not found
        setProject({
          id: projectId,
          name: `Project ${projectId.slice(0, 8)}`,
          slug: `project-${projectId.slice(0, 8)}`,
          targetUrl: "http://localhost:4000",
          defaultMode: "manual",
          createdAt: new Date().toISOString(),
        });
      } finally {
        setLoading(false);
      }
    }

    loadData();
  }, [projectId]);

  if (loading) {
    return (
      <div className="py-24 flex flex-col items-center justify-center text-center">
        <Loader2 className="w-8 h-8 text-clay animate-spin mb-3" />
        <p className="text-xs text-text-secondary">Loading project dashboard...</p>
      </div>
    );
  }

  const latestRun = runs.length > 0 ? runs[0] : null;
  const targetUrl = project?.testUrl || project?.targetUrl || "http://localhost:4000";

  return (
    <div className="max-w-6xl mx-auto py-4 space-y-6">
      {/* Back button & Breadcrumb */}
      <div className="flex items-center gap-2 text-xs text-text-secondary">
        <Link
          href="/projects"
          className="flex items-center gap-1 hover:text-text-primary transition-colors cursor-pointer"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Projects</span>
        </Link>
        <span>/</span>
        <span className="text-text-primary font-medium">{project?.name}</span>
      </div>

      {/* Project Banner Header */}
      <div className="bg-white border border-card-border rounded-2xl p-6 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2 mb-1.5">
            <h1 className="font-heading text-2xl font-normal text-text-primary">
              {project?.name}
            </h1>
            <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-cloud border border-card-border text-text-secondary uppercase">
              {project?.defaultMode || "manual"}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-text-secondary font-mono">
            <div className="flex items-center gap-1.5">
              <Globe className="w-3.5 h-3.5 text-clay shrink-0" />
              <a
                href={targetUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="hover:underline text-text-primary flex items-center gap-1"
              >
                <span>{targetUrl}</span>
                <ExternalLink className="w-3 h-3 text-text-tertiary" />
              </a>
            </div>

            {project?.githubUrl && (
              <div className="flex items-center gap-1 text-text-tertiary">
                <span>GitHub:</span>
                <a
                  href={project.githubUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:underline text-clay flex items-center gap-1"
                >
                  <span>{project.githubUrl.replace("https://github.com/", "")}</span>
                </a>
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <Link href={`/projects/new?tab=run&projectId=${projectId}`}>
            <Button variant="primary" size="sm" className="gap-1.5">
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>New Run</span>
            </Button>
          </Link>
        </div>
      </div>

      {/* Unified Tab Navigation */}
      <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
        <TabsList className="w-full sm:w-auto grid grid-cols-5 sm:inline-flex bg-cloud p-1 rounded-xl mb-2">
          <TabsTrigger value="overview" className="gap-1.5">
            <LayoutDashboard className="w-3.5 h-3.5" />
            <span>Overview</span>
          </TabsTrigger>
          <TabsTrigger value="saved-tests" className="gap-1.5">
            <Bookmark className="w-3.5 h-3.5" />
            <span>Saved Tests</span>
          </TabsTrigger>
          <TabsTrigger value="runs" className="gap-1.5">
            <Layers className="w-3.5 h-3.5" />
            <span>Test Runs</span>
          </TabsTrigger>
          <TabsTrigger value="commits" className="gap-1.5">
            <GitCommit className="w-3.5 h-3.5" />
            <span>Commits</span>
          </TabsTrigger>
          <TabsTrigger value="settings" className="gap-1.5">
            <Settings className="w-3.5 h-3.5" />
            <span>Settings</span>
          </TabsTrigger>
        </TabsList>

        {/* Tab 1: Overview */}
        <TabsContent value="overview">
          {project && (
            <ProjectOverviewTab
              project={project}
              latestRun={latestRun}
              savedTestCount={savedTestCount}
              onGoToSavedTests={() => handleTabChange("saved-tests")}
              onGoToSettings={() => handleTabChange("settings")}
              onGoToRuns={() => handleTabChange("runs")}
            />
          )}
        </TabsContent>

        {/* Tab 2: Saved Tests */}
        <TabsContent value="saved-tests">
          <SavedTestsTab projectId={projectId} />
        </TabsContent>

        {/* Tab 3: Test Runs */}
        <TabsContent value="runs">
          <TestRunsTab projectId={projectId} />
        </TabsContent>

        {/* Tab 4: Commits */}
        <TabsContent value="commits">
          <CommitsTab
            projectId={projectId}
            onGoToSettings={() => handleTabChange("settings")}
          />
        </TabsContent>

        {/* Tab 5: Settings */}
        <TabsContent value="settings">
          <ProjectSettings projectId={projectId} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

export default function ProjectPage({ params }: ProjectPageProps) {
  const { projectId } = use(params);

  return (
    <Suspense
      fallback={
        <div className="py-24 flex flex-col items-center justify-center text-center">
          <Loader2 className="w-8 h-8 text-clay animate-spin mb-3" />
          <p className="text-xs text-text-secondary">Loading project dashboard...</p>
        </div>
      }
    >
      <ProjectPageContent projectId={projectId} />
    </Suspense>
  );
}
