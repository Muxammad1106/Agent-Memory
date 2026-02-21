"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import {
  ArrowLeft,
  MessageSquare,
  FileCode,
  Code2,
  GitBranch,
  Layers,
  RefreshCw,
  FolderTree,
  Cpu,
  Database,
} from "lucide-react";
import Sidebar from "@/components/Sidebar";
import { useProjectStore, type ProjectDetails } from "@/store/projectStore";
import { getProjectDetails, analyzeDependencies } from "@/lib/api";

export default function ProjectPage() {
  const router = useRouter();
  const params = useParams();
  const projectId = params.id as string;
  const { currentProject, setCurrentProject, setLoading, loading } = useProjectStore();
  const [dependencies, setDependencies] = useState<Record<string, any> | null>(null);
  const [activeTab, setActiveTab] = useState("overview");

  useEffect(() => {
    if (!localStorage.getItem("auth_token")) {
      router.push("/login");
      return;
    }
    fetchProject();
  }, [projectId]);

  const fetchProject = async () => {
    setLoading(true);
    try {
      const resp = await getProjectDetails(projectId);
      setCurrentProject(resp.data);
    } catch (err) {
      console.error("Failed to load project:", err);
    } finally {
      setLoading(false);
    }
  };

  const fetchDependencies = async () => {
    try {
      const resp = await analyzeDependencies({ project_id: projectId });
      setDependencies(resp.data);
    } catch (err) {
      console.error("Failed to analyze dependencies:", err);
    }
  };

  const project = currentProject?.project;
  const stats = currentProject?.component_statistics;
  const mcp = currentProject?.mcp_analysis;

  const tabs = [
    { id: "overview", label: "Overview", icon: Layers },
    { id: "structure", label: "Structure", icon: FolderTree },
    { id: "dependencies", label: "Dependencies", icon: GitBranch },
  ];

  return (
    <div className="flex h-screen">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 z-10 border-b border-border bg-background/80 backdrop-blur-sm">
          <div className="flex items-center justify-between px-8 py-4">
            <div className="flex items-center gap-4">
              <button
                onClick={() => router.push("/dashboard")}
                className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              >
                <ArrowLeft className="h-4 w-4" />
              </button>
              <div>
                <h1 className="text-xl font-bold">{project?.name || "Loading..."}</h1>
                <p className="text-xs text-muted-foreground">{project?.path}</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={fetchProject}
                className="flex items-center gap-2 rounded-xl bg-muted px-4 py-2 text-sm text-muted-foreground transition-colors hover:bg-muted/80 hover:text-foreground"
              >
                <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
                Rescan
              </button>
              <button
                onClick={() => router.push(`/project/${projectId}/chat`)}
                className="flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90"
              >
                <MessageSquare className="h-4 w-4" />
                Chat
              </button>
            </div>
          </div>

          {/* Tabs */}
          <div className="flex gap-1 px-8">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => {
                  setActiveTab(tab.id);
                  if (tab.id === "dependencies" && !dependencies) fetchDependencies();
                }}
                className={`flex items-center gap-2 border-b-2 px-4 py-3 text-sm transition-colors ${
                  activeTab === tab.id
                    ? "border-primary text-primary"
                    : "border-transparent text-muted-foreground hover:text-foreground"
                }`}
              >
                <tab.icon className="h-4 w-4" />
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        <div className="p-8">
          {loading && !project ? (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="skeleton h-32 rounded-2xl" />
              ))}
            </div>
          ) : (
            <>
              {activeTab === "overview" && project && (
                <div className="space-y-6">
                  {/* Stats Grid */}
                  <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                    <MetricCard
                      icon={<FileCode className="h-5 w-5 text-primary" />}
                      label="Files"
                      value={(project.total_files || 0).toString()}
                    />
                    <MetricCard
                      icon={<Code2 className="h-5 w-5 text-green-400" />}
                      label="Lines of Code"
                      value={(project.total_lines || 0).toLocaleString()}
                    />
                    <MetricCard
                      icon={<Cpu className="h-5 w-5 text-yellow-400" />}
                      label="Functions"
                      value={(mcp?.functions_extracted || 0).toString()}
                    />
                    <MetricCard
                      icon={<Database className="h-5 w-5 text-purple-400" />}
                      label="Dependencies"
                      value={(mcp?.dependencies_mapped || 0).toString()}
                    />
                  </div>

                  {/* Info Blocks */}
                  <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                    {/* Languages */}
                    <div className="rounded-2xl border border-border bg-card/50 p-6">
                      <h3 className="mb-4 text-sm font-semibold">Languages</h3>
                      <div className="flex flex-wrap gap-2">
                        {(project.languages || []).map((lang: string) => (
                          <span
                            key={lang}
                            className="rounded-lg bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary"
                          >
                            {lang}
                          </span>
                        ))}
                        {(!project.languages || project.languages.length === 0) && (
                          <span className="text-xs text-muted-foreground">No languages detected</span>
                        )}
                      </div>
                    </div>

                    {/* Frameworks */}
                    <div className="rounded-2xl border border-border bg-card/50 p-6">
                      <h3 className="mb-4 text-sm font-semibold">Frameworks</h3>
                      <div className="flex flex-wrap gap-2">
                        {(project.frameworks || []).map((fw: string) => (
                          <span
                            key={fw}
                            className="rounded-lg bg-green-500/10 px-3 py-1.5 text-xs font-medium text-green-400"
                          >
                            {fw}
                          </span>
                        ))}
                        {(!project.frameworks || project.frameworks.length === 0) && (
                          <span className="text-xs text-muted-foreground">No frameworks detected</span>
                        )}
                      </div>
                    </div>

                    {/* Architecture */}
                    <div className="rounded-2xl border border-border bg-card/50 p-6">
                      <h3 className="mb-4 text-sm font-semibold">Architecture</h3>
                      <p className="text-sm">
                        {project.architecture_type || "Not determined"}
                      </p>
                    </div>

                    {/* MCP Analysis */}
                    <div className="rounded-2xl border border-border bg-card/50 p-6">
                      <h3 className="mb-4 text-sm font-semibold">MCP Analysis</h3>
                      <div className="space-y-2 text-xs">
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Files Processed</span>
                          <span>{mcp?.files_processed || 0}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Functions Extracted</span>
                          <span>{mcp?.functions_extracted || 0}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Classes Extracted</span>
                          <span>{mcp?.classes_extracted || 0}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Last Scan</span>
                          <span>
                            {mcp?.last_scan
                              ? new Date(mcp.last_scan).toLocaleString()
                              : "Never"}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Component Statistics */}
                  {stats && Object.keys(stats).length > 0 && (
                    <div className="rounded-2xl border border-border bg-card/50 p-6">
                      <h3 className="mb-4 text-sm font-semibold">Component Statistics</h3>
                      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                        {Object.entries(stats).map(([type, count]) => (
                          <div
                            key={type}
                            className="rounded-xl bg-muted/50 p-4 text-center"
                          >
                            <p className="text-xl font-bold">{count}</p>
                            <p className="text-[10px] text-muted-foreground capitalize">
                              {type}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {activeTab === "structure" && (
                <div className="rounded-2xl border border-border bg-card/50 p-6">
                  <h3 className="mb-4 text-sm font-semibold">Project Structure</h3>
                  <p className="text-sm text-muted-foreground">
                    Use the Chat tab to explore project structure with AI assistance.
                  </p>
                  <button
                    onClick={() => router.push(`/project/${projectId}/chat`)}
                    className="mt-4 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground"
                  >
                    Open Chat
                  </button>
                </div>
              )}

              {activeTab === "dependencies" && (
                <div className="rounded-2xl border border-border bg-card/50 p-6">
                  <h3 className="mb-4 text-sm font-semibold">Dependencies Analysis</h3>
                  {dependencies ? (
                    <pre className="max-h-96 overflow-auto rounded-xl bg-muted/50 p-4 text-xs">
                      {JSON.stringify(dependencies, null, 2)}
                    </pre>
                  ) : (
                    <div className="flex flex-col items-center py-8">
                      <GitBranch className="mb-3 h-8 w-8 text-muted-foreground/50" />
                      <p className="text-sm text-muted-foreground">
                        Click to analyze dependencies
                      </p>
                      <button
                        onClick={fetchDependencies}
                        className="mt-3 rounded-xl bg-primary/10 px-4 py-2 text-sm text-primary"
                      >
                        Analyze
                      </button>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  );
}

function MetricCard({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-2xl border border-border bg-card/50 p-5">
      <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-muted">
        {icon}
      </div>
      <p className="text-2xl font-bold">{value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}
