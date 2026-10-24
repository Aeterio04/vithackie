"use client";

import React, { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { NewProjectForm } from "@/features/projects/components/NewProjectForm";
import { StartTestForm } from "@/components/features/StartTestForm";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/shared/ui/Tabs";
import { FolderPlus, Play, Shield, Loader2 } from "lucide-react";

function NewProjectContent() {
  const searchParams = useSearchParams();
  const requestedTab = searchParams.get("tab") === "project" ? "project" : "run";
  const [activeTab, setActiveTab] = useState<"project" | "run">(requestedTab);

  useEffect(() => {
    const tab = searchParams.get("tab");
    if (tab === "project" || tab === "run") {
      setActiveTab(tab);
    }
  }, [searchParams]);

  return (
    <div className="max-w-5xl mx-auto py-4 space-y-6">
      <div>
        <h1 className="font-heading text-3xl font-normal text-text-primary">
          New Project & Test Run
        </h1>
        <p className="text-xs text-text-secondary mt-1">
          Create a persistent project configuration or launch an immediate autonomous QA test run.
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as "project" | "run")}>
        <TabsList className="mb-6">
          <TabsTrigger value="run" className="gap-2">
            <Play className="w-3.5 h-3.5" />
            <span>Launch Immediate Run</span>
          </TabsTrigger>
          <TabsTrigger value="project" className="gap-2">
            <FolderPlus className="w-3.5 h-3.5" />
            <span>Create Project Entity</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="run">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
            <div className="lg:col-span-8">
              <StartTestForm defaultProjectId={searchParams.get("projectId") || undefined} />
            </div>
            <div className="lg:col-span-4 bg-white border border-card-border rounded-2xl p-5 shadow-xs space-y-3">
              <div className="flex items-center gap-2 pb-2 border-b border-card-border">
                <Shield className="w-4 h-4 text-clay" />
                <h3 className="font-heading text-sm font-medium text-text-primary">
                  Immediate Test Mode
                </h3>
              </div>
              <p className="text-xs text-text-secondary leading-relaxed">
                Runs are automatically scoped to your active project and user session.
                Generated Playwright scripts and 3x replay proofs are content-addressed and saved under managed storage.
              </p>
            </div>
          </div>
        </TabsContent>

        <TabsContent value="project">
          <NewProjectForm />
        </TabsContent>
      </Tabs>
    </div>
  );
}

export default function NewProjectPage() {
  return (
    <Suspense
      fallback={
        <div className="py-20 flex flex-col items-center justify-center text-center">
          <Loader2 className="w-8 h-8 text-clay animate-spin mb-3" />
          <p className="text-xs text-text-secondary">Loading...</p>
        </div>
      }
    >
      <NewProjectContent />
    </Suspense>
  );
}
