"use client";

import { use } from "react";
import { CommitEmptyState } from "@/features/commits/components/CommitEmptyState";

interface PageProps {
  params: Promise<{ projectId: string }>;
}

export default function ProjectCommitsPage({ params }: PageProps) {
  const { projectId } = use(params);
  return (
    <div className="py-6">
      <CommitEmptyState projectId={projectId} />
    </div>
  );
}
