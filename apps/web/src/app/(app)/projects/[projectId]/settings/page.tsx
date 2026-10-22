"use client";

import { use } from "react";
import { ProjectSettings } from "@/features/projects/components/ProjectSettings";

interface PageProps {
  params: Promise<{ projectId: string }>;
}

export default function ProjectSettingsPage({ params }: PageProps) {
  const { projectId } = use(params);
  return (
    <div className="py-4">
      <ProjectSettings projectId={projectId} />
    </div>
  );
}
