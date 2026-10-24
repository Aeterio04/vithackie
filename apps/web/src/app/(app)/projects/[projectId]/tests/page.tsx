"use client";

import { use, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

interface PageProps {
  params: Promise<{ projectId: string }>;
}

export default function ProjectTestsPage({ params }: PageProps) {
  const { projectId } = use(params);
  const router = useRouter();

  useEffect(() => {
    router.replace(`/projects/${projectId}?tab=saved-tests`);
  }, [projectId, router]);

  return (
    <div className="py-20 flex flex-col items-center justify-center text-center">
      <Loader2 className="w-8 h-8 text-clay animate-spin mb-3" />
      <p className="text-xs text-text-secondary">Loading saved tests...</p>
    </div>
  );
}
