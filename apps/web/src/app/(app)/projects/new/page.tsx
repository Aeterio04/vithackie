"use client";

import React, { useState } from "react";
import { NewProjectForm } from "@/features/projects/components/NewProjectForm";
import { StartTestForm } from "@/features/runs/components/StartTestForm";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/shared/ui/Tabs";
import { FolderPlus, Play, Shield } from "lucide-react";

export default function NewProjectPage() {
  const [activeTab, setActiveTab] = useState<"project" | "run">("run");

  return (
    <div className="max-w-5xl mx-auto py-4 space-y-6">
      <div>
        <h1 className="font-heading text-3xl font-normal text-[#141413]">
          New Project & Test Run
        </h1>
        <p className="text-xs text-[#6B6A64] mt-1">
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
              <StartTestForm />
            </div>
            <div className="lg:col-span-4 bg-white border border-[#E3DACC] rounded-[16px] p-5 shadow-xs space-y-3">
              <div className="flex items-center gap-2 pb-2 border-b border-[#E3DACC]">
                <Shield className="w-4 h-4 text-[#D97757]" />
                <h3 className="font-heading text-sm font-medium text-[#141413]">
                  Immediate Test Mode
                </h3>
              </div>
              <p className="text-xs text-[#6B6A64]">
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
