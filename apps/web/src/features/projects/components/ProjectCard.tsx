"use client";

import React from "react";
import Link from "next/link";
import { ProjectItem } from "../api";
import { Globe, ArrowRight, Calendar, Play } from "lucide-react";
import { Button } from "@/shared/ui/Button";

interface ProjectCardProps {
  project: ProjectItem;
}

export function ProjectCard({ project }: ProjectCardProps) {
  const formattedDate = new Date(project.createdAt).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });

  return (
    <div className="bg-white border border-[#E3DACC] rounded-[16px] p-6 shadow-xs hover:border-[#D97757]/60 hover:shadow-md transition-all flex flex-col justify-between">
      <div>
        <div className="flex items-start justify-between gap-3 mb-3">
          <div>
            <h3 className="font-heading text-lg font-medium text-[#141413]">
              {project.name}
            </h3>
            <div className="flex items-center gap-1.5 text-xs text-[#8A887F] font-mono mt-0.5">
              <Globe className="w-3.5 h-3.5 text-[#6B6A64]" />
              <span className="truncate max-w-[240px]">{project.targetUrl}</span>
            </div>
          </div>
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-mono font-medium bg-[#FAF9F5] border border-[#E3DACC] text-[#6B6A64]">
            {project.defaultMode}
          </span>
        </div>

        {project.description && (
          <p className="text-xs text-[#6B6A64] line-clamp-2 mb-4">
            {project.description}
          </p>
        )}
      </div>

      <div className="pt-4 border-t border-[#E3DACC]/60 flex items-center justify-between mt-4">
        <div className="flex items-center gap-1 text-[11px] text-[#8A887F]">
          <Calendar className="w-3.5 h-3.5" />
          <span>{formattedDate}</span>
        </div>

        <div className="flex items-center gap-2">
          <Link href={`/projects/${project.id}`}>
            <Button variant="secondary" size="sm" className="gap-1.5">
              <span>View Runs</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Button>
          </Link>
        </div>
      </div>
    </div>
  );
}
