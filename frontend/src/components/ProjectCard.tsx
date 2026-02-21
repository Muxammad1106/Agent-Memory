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
    completed: "bg-green-500/10 text-green-400",
    analyzing: "bg-yellow-500/10 text-yellow-400",
    pending: "bg-muted text-muted-foreground",
    error: "bg-destructive/10 text-destructive",
  };

  return (
    <div
      onClick={() => router.push(`/project/${project.id}`)}
      className="group cursor-pointer rounded-2xl border border-border bg-card/50 p-5 transition-all duration-200 hover:border-primary/30 hover:bg-card hover:shadow-lg hover:shadow-primary/5"
    >
      <div className="mb-4 flex items-start justify-between">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
          <FolderOpen className="h-5 w-5 text-primary" />
        </div>
        <span
          className={cn(
            "rounded-full px-2.5 py-1 text-[10px] font-medium",
            statusColor[project.analysis_status] || statusColor.pending
          )}
        >
          {project.analysis_status}
        </span>
      </div>

      <h3 className="mb-1 text-sm font-semibold truncate">{project.name}</h3>
      <p className="mb-4 text-xs text-muted-foreground truncate">{project.path}</p>

      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <FileCode className="h-3.5 w-3.5" />
          <span>{project.total_files || 0} files</span>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Code2 className="h-3.5 w-3.5" />
          <span>{(project.total_lines || 0).toLocaleString()} lines</span>
        </div>
      </div>

      {/* Languages */}
      {project.languages && project.languages.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-1.5">
          {project.languages.slice(0, 4).map((lang) => (
            <span
              key={lang}
              className="rounded-md bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground"
            >
              {lang}
            </span>
          ))}
          {project.languages.length > 4 && (
            <span className="rounded-md bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">
              +{project.languages.length - 4}
            </span>
          )}
        </div>
      )}

      {/* Last analyzed */}
      <div className="flex items-center justify-between border-t border-border pt-3">
        <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
          <Clock className="h-3 w-3" />
          {project.last_analyzed
            ? new Date(project.last_analyzed).toLocaleDateString()
            : "Not analyzed"}
        </div>
        <ArrowRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-1 group-hover:text-primary" />
      </div>
    </div>
  );
}
