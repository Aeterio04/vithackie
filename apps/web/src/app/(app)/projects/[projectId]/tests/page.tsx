"use client";

import { use } from "react";
import { SavedTestEmptyState } from "@/features/library/components/SavedTestEmptyState";

interface PageProps {
  params: Promise<{ projectId: string }>;
}

export default function ProjectTestsPage({ params }: PageProps) {
  const { projectId } = use(params);
  return (
    <div className="py-6">
      <SavedTestEmptyState projectId={projectId} />
    </div>
  );
}
