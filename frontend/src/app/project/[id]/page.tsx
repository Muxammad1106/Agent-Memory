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
        <div className="sticky top-0 z-10 border-b border-white/[0.04] bg-black/60 backdrop-blur-xl">
          <div className="flex items-center justify-between px-8 py-3">
            <div className="flex items-center gap-3">
              <button
                onClick={() => router.push("/dashboard")}
                className="rounded-md p-1.5 text-white/20 transition-all hover:bg-white/[0.06] hover:text-white/50"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
              </button>
              <div>
                <h1 className="text-[15px] font-semibold tracking-tight text-white/90">{project?.name || "Loading..."}</h1>
                <p className="text-[10px] text-white/20">{project?.path}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={fetchProject}
                className="flex items-center gap-1.5 rounded-lg border border-white/[0.06] bg-white/[0.03] px-3 py-1.5 text-[11px] text-white/40 transition-all hover:bg-white/[0.06] hover:text-white/60"
              >
                <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
                Rescan
              </button>
              <button
                onClick={() => router.push(`/project/${projectId}/chat`)}
                className="flex items-center gap-1.5 rounded-lg bg-white/90 px-3 py-1.5 text-[11px] font-semibold text-black transition-all hover:bg-white"
              >
                <MessageSquare className="h-3 w-3" />
                Chat
              </button>
            </div>
          </div>

          {/* Tabs */}
          <div className="flex gap-0.5 px-8">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => {
                  setActiveTab(tab.id);
                  if (tab.id === "dependencies" && !dependencies) fetchDependencies();
                }}
                className={`flex items-center gap-1.5 border-b-2 px-3 py-2.5 text-[11px] transition-all ${
                  activeTab === tab.id
                    ? "border-white/50 text-white/80"
                    : "border-transparent text-white/25 hover:text-white/50"
                }`}
              >
                <tab.icon className="h-3 w-3" />
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        <div className="p-8">
          {loading && !project ? (
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="skeleton h-28 rounded-xl" />
              ))}
            </div>
          ) : (
            <>
              {activeTab === "overview" && project && (
                <div className="space-y-5">
                  {/* Stats Grid */}
                  <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                    <MetricCard
                      icon={<FileCode className="h-4 w-4 text-white/40" />}
                      label="Files"
                      value={(project.total_files || 0).toString()}
                    />
                    <MetricCard
                      icon={<Code2 className="h-4 w-4 text-white/40" />}
                      label="Lines of Code"
                      value={(project.total_lines || 0).toLocaleString()}
                    />
                    <MetricCard
                      icon={<Cpu className="h-4 w-4 text-white/40" />}
                      label="Functions"
                      value={(mcp?.functions_extracted || 0).toString()}
                    />
                    <MetricCard
                      icon={<Database className="h-4 w-4 text-white/40" />}
                      label="Dependencies"
                      value={(mcp?.dependencies_mapped || 0).toString()}
                    />
                  </div>

                  {/* Info Blocks */}
                  <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                    {/* Languages */}
                    <div className="glass rounded-xl p-5">
                      <h3 className="mb-3 text-[11px] font-medium uppercase tracking-widest text-white/25">Languages</h3>
                      <div className="flex flex-wrap gap-1.5">
                        {(project.languages || []).map((lang: string) => (
                          <span key={lang} className="rounded-md bg-white/[0.06] px-2.5 py-1 text-[10px] font-medium text-white/50">{lang}</span>
                        ))}
                        {(!project.languages || project.languages.length === 0) && (
                          <span className="text-[10px] text-white/20">No languages detected</span>
                        )}
                      </div>
                    </div>

                    {/* Frameworks */}
                    <div className="glass rounded-xl p-5">
                      <h3 className="mb-3 text-[11px] font-medium uppercase tracking-widest text-white/25">Frameworks</h3>
                      <div className="flex flex-wrap gap-1.5">
                        {(project.frameworks || []).map((fw: string) => (
                          <span key={fw} className="rounded-md bg-white/[0.06] px-2.5 py-1 text-[10px] font-medium text-white/50">{fw}</span>
                        ))}
                        {(!project.frameworks || project.frameworks.length === 0) && (
                          <span className="text-[10px] text-white/20">No frameworks detected</span>
                        )}
                      </div>
                    </div>

                    {/* Architecture */}
                    <div className="glass rounded-xl p-5">
                      <h3 className="mb-3 text-[11px] font-medium uppercase tracking-widest text-white/25">Architecture</h3>
                      <p className="text-[12px] text-white/50">{project.architecture_type || "Not determined"}</p>
                    </div>

                    {/* MCP Analysis */}
                    <div className="glass rounded-xl p-5">
                      <h3 className="mb-3 text-[11px] font-medium uppercase tracking-widest text-white/25">MCP Analysis</h3>
                      <div className="space-y-1.5 text-[11px]">
                        <div className="flex justify-between"><span className="text-white/25">Files Processed</span><span className="text-white/60">{mcp?.files_processed || 0}</span></div>
                        <div className="flex justify-between"><span className="text-white/25">Functions</span><span className="text-white/60">{mcp?.functions_extracted || 0}</span></div>
                        <div className="flex justify-between"><span className="text-white/25">Classes</span><span className="text-white/60">{mcp?.classes_extracted || 0}</span></div>
                        <div className="flex justify-between"><span className="text-white/25">Last Scan</span><span className="text-white/60">{mcp?.last_scan ? new Date(mcp.last_scan).toLocaleString() : "Never"}</span></div>
                      </div>
                    </div>
                  </div>

                  {/* Component Statistics */}
                  {stats && Object.keys(stats).length > 0 && (
                    <div className="glass rounded-xl p-5">
                      <h3 className="mb-3 text-[11px] font-medium uppercase tracking-widest text-white/25">Component Statistics</h3>
                      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                        {Object.entries(stats).map(([type, count]) => (
                          <div key={type} className="rounded-lg bg-white/[0.03] p-3 text-center">
                            <p className="text-lg font-semibold text-white/80">{count}</p>
                            <p className="text-[9px] text-white/25 capitalize">{type}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {activeTab === "structure" && (
                <div className="glass rounded-xl p-6">
                  <h3 className="mb-3 text-[12px] font-medium text-white/60">Project Structure</h3>
                  <p className="text-[11px] text-white/25">Use the Chat tab to explore project structure with AI assistance.</p>
                  <button
                    onClick={() => router.push(`/project/${projectId}/chat`)}
                    className="mt-3 rounded-lg bg-white/90 px-3 py-1.5 text-[11px] font-semibold text-black"
                  >
                    Open Chat
                  </button>
                </div>
              )}

              {activeTab === "dependencies" && (
                <div className="glass rounded-xl p-6">
                  <h3 className="mb-3 text-[12px] font-medium text-white/60">Dependencies Analysis</h3>
                  {dependencies ? (
                    <pre className="max-h-96 overflow-auto rounded-lg bg-white/[0.02] p-3 text-[10px] text-white/50">
                      {JSON.stringify(dependencies, null, 2)}
                    </pre>
                  ) : (
                    <div className="flex flex-col items-center py-8">
                      <GitBranch className="mb-3 h-6 w-6 text-white/10" />
                      <p className="text-[11px] text-white/25">Click to analyze dependencies</p>
                      <button onClick={fetchDependencies} className="mt-3 rounded-lg bg-white/[0.06] px-3 py-1.5 text-[11px] text-white/50 hover:bg-white/[0.1]">
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
    <div className="glass rounded-xl p-4">
      <div className="mb-2 flex h-7 w-7 items-center justify-center rounded-md bg-white/[0.04]">
        {icon}
      </div>
      <p className="text-xl font-semibold tracking-tight text-white/85">{value}</p>
      <p className="text-[10px] text-white/25">{label}</p>
    </div>
  );
}
