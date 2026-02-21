"use client";

import { useRouter } from "next/navigation";
import { FolderOpen, FileCode, Clock, Code2, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Project } from "@/store/projectStore";

interface ProjectCardProps {
  project: Project;
}

export default function ProjectCard({ project }: ProjectCardProps) {
  const router = useRouter();

  const statusColor: Record<string, string> = {
    completed: "bg-emerald-500/10 text-emerald-400/70",
    analyzing: "bg-amber-500/10 text-amber-400/70",
    pending: "bg-white/[0.04] text-white/30",
    error: "bg-red-500/10 text-red-400/70",
  };

  return (
    <div
      onClick={() => router.push(`/project/${project.id}`)}
      className="glass glass-hover group cursor-pointer rounded-xl p-4 transition-all duration-200"
    >
      <div className="mb-3 flex items-start justify-between">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/[0.04]">
          <FolderOpen className="h-4 w-4 text-white/40" />
        </div>
        <span
          className={cn(
            "rounded-md px-2 py-0.5 text-[9px] font-medium",
            statusColor[project.analysis_status] || statusColor.pending
          )}
        >
          {project.analysis_status}
        </span>
      </div>

      <h3 className="mb-0.5 text-[13px] font-medium tracking-tight text-white/85 truncate">{project.name}</h3>
      <p className="mb-3 text-[10px] text-white/20 truncate">{project.path}</p>

      <div className="grid grid-cols-2 gap-2 mb-3">
        <div className="flex items-center gap-1.5 text-[10px] text-white/30">
          <FileCode className="h-3 w-3" />
          <span>{project.total_files || 0} files</span>
        </div>
        <div className="flex items-center gap-1.5 text-[10px] text-white/30">
          <Code2 className="h-3 w-3" />
          <span>{(project.total_lines || 0).toLocaleString()} lines</span>
        </div>
      </div>

      {/* Languages */}
      {project.languages && project.languages.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1">
          {project.languages.slice(0, 4).map((lang) => (
            <span
              key={lang}
              className="rounded-md bg-white/[0.04] px-1.5 py-0.5 text-[9px] font-medium text-white/30"
            >
              {lang}
            </span>
          ))}
          {project.languages.length > 4 && (
            <span className="rounded-md bg-white/[0.04] px-1.5 py-0.5 text-[9px] text-white/20">
              +{project.languages.length - 4}
            </span>
          )}
        </div>
      )}

      {/* Last analyzed */}
      <div className="flex items-center justify-between border-t border-white/[0.04] pt-2.5">
        <div className="flex items-center gap-1.5 text-[9px] text-white/20">
          <Clock className="h-2.5 w-2.5" />
          {project.last_analyzed
            ? new Date(project.last_analyzed).toLocaleDateString()
            : "Not analyzed"}
        </div>
        <ArrowRight className="h-3 w-3 text-white/10 transition-all group-hover:translate-x-0.5 group-hover:text-white/40" />
      </div>
    </div>
  );
}
