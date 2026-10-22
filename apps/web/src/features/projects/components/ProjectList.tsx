"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { projectsApi, ProjectItem } from "../api";
import { ProjectCard } from "./ProjectCard";
import { Button } from "@/shared/ui/Button";
import { Plus, FolderPlus, Loader2 } from "lucide-react";

export function ProjectList() {
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    projectsApi
      .list()
      .then((data) => {
        setProjects(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message || "Failed to load projects");
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="py-20 flex flex-col items-center justify-center text-center">
        <Loader2 className="w-8 h-8 text-[#D97757] animate-spin mb-3" />
        <p className="text-xs text-[#6B6A64]">Loading projects...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="py-12 text-center bg-white border border-[#E3DACC] rounded-[16px] p-8">
        <p className="text-sm text-[#C4473A] mb-3">{error}</p>
        <Button variant="secondary" onClick={() => window.location.reload()}>
          Retry
        </Button>
      </div>
    );
  }

  if (projects.length === 0) {
    return (
      <div className="py-16 text-center bg-white border border-[#E3DACC] rounded-[16px] p-8 max-w-md mx-auto">
        <div className="w-12 h-12 rounded-2xl bg-[#FAF9F5] border border-[#E3DACC] flex items-center justify-center mx-auto mb-4 text-[#D97757]">
          <FolderPlus className="w-6 h-6" />
        </div>
        <h3 className="font-heading text-lg font-medium text-[#141413] mb-1">
          No projects found
        </h3>
        <p className="text-xs text-[#6B6A64] mb-6">
          Create your first QA project to configure a target web app and execute autonomous test runs.
        </p>
        <Link href="/projects/new">
          <Button variant="primary" className="gap-2">
            <Plus className="w-4 h-4" />
            <span>Create First Project</span>
          </Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-heading text-2xl font-normal text-[#141413]">
            Projects ({projects.length})
          </h2>
          <p className="text-xs text-[#6B6A64] mt-0.5">
            Select a project to inspect runs, view verified defects, or launch regressions.
          </p>
        </div>
        <Link href="/projects/new">
          <Button variant="primary" className="gap-2">
            <Plus className="w-4 h-4" />
            <span>New Project</span>
          </Button>
        </Link>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {projects.map((project) => (
          <ProjectCard key={project.id} project={project} />
        ))}
      </div>
    </div>
  );
}
