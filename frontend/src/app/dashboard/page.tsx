"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { RefreshCw, FolderOpen, FileCode, Code2, Activity } from "lucide-react";
import Sidebar from "@/components/Sidebar";
import ProjectCard from "@/components/ProjectCard";
import { useProjectStore } from "@/store/projectStore";
import { listProjects, checkHealth } from "@/lib/api";

export default function DashboardPage() {
  const router = useRouter();
  const { projects, setProjects, loading, setLoading, setError, filteredProjects } =
    useProjectStore();
  const [healthStatus, setHealthStatus] = useState<Record<string, string>>({});
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("auth_token");
    if (!token) {
      router.push("/login");
      return;
    }
    fetchProjects();
    fetchHealth();
  }, []);

  const fetchProjects = async () => {
    setLoading(true);
    try {
      const resp = await listProjects();
      setProjects(resp.data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchHealth = async () => {
    try {
      const resp = await checkHealth();
      setHealthStatus(resp.data.services || {});
    } catch {
      // ignore
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await fetchProjects();
    await fetchHealth();
    setRefreshing(false);
  };

  const displayed = filteredProjects();
  const totalFiles = projects.reduce((sum, p) => sum + (p.total_files || 0), 0);
  const totalLines = projects.reduce((sum, p) => sum + (p.total_lines || 0), 0);

  return (
    <div className="flex h-screen">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 z-10 border-b border-white/[0.04] bg-black/60 backdrop-blur-xl">
          <div className="flex items-center justify-between px-8 py-4">
            <div>
              <h1 className="text-lg font-semibold tracking-tight text-white/90">Dashboard</h1>
              <p className="text-[11px] text-white/30">
                {projects.length} projects indexed
              </p>
            </div>
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="flex items-center gap-2 rounded-lg border border-white/[0.06] bg-white/[0.04] px-3 py-1.5 text-[11px] text-white/50 transition-all hover:bg-white/[0.08] hover:text-white/70 disabled:opacity-40"
            >
              <RefreshCw className={`h-3 w-3 ${refreshing ? "animate-spin" : ""}`} />
              Refresh
            </button>
          </div>
        </div>

        <div className="p-8">
          {/* Stats */}
          <div className="mb-8 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              icon={<FolderOpen className="h-4 w-4 text-white/50" />}
              label="Projects"
              value={projects.length.toString()}
            />
            <StatCard
              icon={<FileCode className="h-4 w-4 text-white/50" />}
              label="Total Files"
              value={totalFiles.toLocaleString()}
            />
            <StatCard
              icon={<Code2 className="h-4 w-4 text-white/50" />}
              label="Total Lines"
              value={totalLines.toLocaleString()}
            />
            <StatCard
              icon={<Activity className="h-4 w-4 text-white/50" />}
              label="Services"
              value={Object.values(healthStatus).filter((s) => s === "healthy").length + "/" + Object.keys(healthStatus).length}
            />
          </div>

          {/* Service Health */}
          {Object.keys(healthStatus).length > 0 && (
            <div className="mb-8">
              <h2 className="mb-3 text-[11px] font-medium uppercase tracking-widest text-white/20">Service Health</h2>
              <div className="flex flex-wrap gap-2">
                {Object.entries(healthStatus).map(([name, status]) => (
                  <span
                    key={name}
                    className={`rounded-md px-2.5 py-1 text-[10px] font-medium ${
                      status === "healthy"
                        ? "bg-emerald-500/10 text-emerald-400/80"
                        : "bg-red-500/10 text-red-400/80"
                    }`}
                  >
                    {name}: {typeof status === "string" ? status : "healthy"}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Projects Grid */}
          {loading ? (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="skeleton h-48 rounded-xl" />
              ))}
            </div>
          ) : displayed.length > 0 ? (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {displayed.map((project) => (
                <ProjectCard key={project.id} project={project} />
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <FolderOpen className="mb-4 h-10 w-10 text-white/10" />
              <h3 className="text-sm font-medium text-white/50">No projects found</h3>
              <p className="mt-1 text-[11px] text-white/25">
                Analyze a project through MCP to see it here
              </p>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

function StatCard({
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
      <div className="mb-2.5 flex h-8 w-8 items-center justify-center rounded-lg bg-white/[0.04]">
        {icon}
      </div>
      <p className="text-xl font-semibold tracking-tight text-white/90">{value}</p>
      <p className="text-[10px] text-white/30">{label}</p>
    </div>
  );
}
