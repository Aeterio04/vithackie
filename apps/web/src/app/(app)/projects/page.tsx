"use client";

import React from "react";
import { ProjectList } from "@/features/projects/components/ProjectList";

export default function ProjectsPage() {
  return (
    <div className="max-w-6xl mx-auto py-4 space-y-6">
      <ProjectList />
    </div>
  );
}
