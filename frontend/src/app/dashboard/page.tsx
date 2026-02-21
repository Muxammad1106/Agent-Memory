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
        <div className="sticky top-0 z-10 border-b border-border bg-background/80 backdrop-blur-sm">
          <div className="flex items-center justify-between px-8 py-4">
            <div>
              <h1 className="text-xl font-bold">Dashboard</h1>
              <p className="text-sm text-muted-foreground">
                {projects.length} projects indexed
              </p>
            </div>
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="flex items-center gap-2 rounded-xl bg-primary/10 px-4 py-2 text-sm font-medium text-primary transition-colors hover:bg-primary/20 disabled:opacity-50"
            >
              <RefreshCw
                className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`}
              />
              Refresh
            </button>
          </div>
        </div>

        <div className="p-8">
          {/* Stats */}
          <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              icon={<FolderOpen className="h-5 w-5 text-primary" />}
              label="Projects"
              value={projects.length.toString()}
            />
            <StatCard
              icon={<FileCode className="h-5 w-5 text-green-400" />}
              label="Total Files"
              value={totalFiles.toLocaleString()}
            />
            <StatCard
              icon={<Code2 className="h-5 w-5 text-yellow-400" />}
              label="Total Lines"
              value={totalLines.toLocaleString()}
            />
            <StatCard
              icon={<Activity className="h-5 w-5 text-purple-400" />}
              label="Services"
              value={Object.values(healthStatus).filter((s) => s === "healthy").length + "/" + Object.keys(healthStatus).length}
            />
          </div>

          {/* Service Health */}
          {Object.keys(healthStatus).length > 0 && (
            <div className="mb-8">
              <h2 className="mb-3 text-sm font-semibold text-muted-foreground">Service Health</h2>
              <div className="flex flex-wrap gap-2">
                {Object.entries(healthStatus).map(([name, status]) => (
                  <span
                    key={name}
                    className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
                      status === "healthy"
                        ? "bg-green-500/10 text-green-400"
                        : "bg-destructive/10 text-destructive"
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
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="skeleton h-56 rounded-2xl" />
              ))}
            </div>
          ) : displayed.length > 0 ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {displayed.map((project) => (
                <ProjectCard key={project.id} project={project} />
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <FolderOpen className="mb-4 h-12 w-12 text-muted-foreground/50" />
              <h3 className="text-lg font-medium">No projects found</h3>
              <p className="mt-1 text-sm text-muted-foreground">
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
    <div className="rounded-2xl border border-border bg-card/50 p-5">
      <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-muted">
        {icon}
      </div>
      <p className="text-2xl font-bold">{value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}
