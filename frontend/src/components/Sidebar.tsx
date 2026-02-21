"use client";

import { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import {
  Brain,
  LayoutDashboard,
  FolderOpen,
  LogOut,
  Search,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useProjectStore, type Project } from "@/store/projectStore";
import { listProjects } from "@/lib/api";

interface SidebarProps {
  collapsed?: boolean;
}

export default function Sidebar({ collapsed = false }: SidebarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { projects, setProjects, searchQuery, setSearchQuery } = useProjectStore();

  useEffect(() => {
    if (projects.length === 0) {
      listProjects().then((r) => setProjects(r.data)).catch(() => {});
    }
  }, []);

  const handleLogout = () => {
    localStorage.removeItem("auth_token");
    localStorage.removeItem("user");
    router.push("/login");
  };

  const navItems = [
    { icon: LayoutDashboard, label: "Dashboard", href: "/dashboard" },
  ];

  const recentProjects = projects.slice(0, 5);

  return (
    <aside
      className={cn(
        "glass-subtle flex h-screen flex-col transition-all duration-300",
        collapsed ? "w-16" : "w-60"
      )}
    >
      {/* Logo */}
      <div className="flex h-14 items-center gap-3 border-b border-white/[0.04] px-4">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/[0.06]">
          <Brain className="h-4 w-4 text-white/80" />
        </div>
        {!collapsed && (
          <div>
            <h1 className="text-xs font-semibold tracking-wide text-white/90">Agent Brain</h1>
            <p className="text-[9px] text-white/30">AI Control Panel</p>
          </div>
        )}
      </div>

      {/* Search */}
      {!collapsed && (
        <div className="px-3 py-3">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 h-3 w-3 -translate-y-1/2 text-white/20" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search..."
              className="w-full rounded-lg border border-white/[0.06] bg-white/[0.03] py-1.5 pl-8 pr-3 text-[11px] text-white/70 outline-none transition-colors placeholder:text-white/20 focus:border-white/[0.12] focus:bg-white/[0.05]"
            />
          </div>
        </div>
      )}

      {/* Nav */}
      <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 py-1">
        {navItems.map((item) => {
          const isActive = pathname === item.href;
          return (
            <button
              key={item.href}
              onClick={() => router.push(item.href)}
              className={cn(
                "flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[12px] transition-all",
                isActive
                  ? "bg-white/[0.08] text-white"
                  : "text-white/40 hover:bg-white/[0.04] hover:text-white/70"
              )}
            >
              <item.icon className="h-3.5 w-3.5 shrink-0" />
              {!collapsed && <span>{item.label}</span>}
            </button>
          );
        })}

        {/* Recent Projects */}
        {!collapsed && recentProjects.length > 0 && (
          <div className="mt-5">
            <p className="mb-1.5 px-3 text-[9px] font-medium uppercase tracking-widest text-white/20">
              Projects
            </p>
            {recentProjects.map((project: Project) => {
              const isActive = pathname.includes(`/project/${project.id}`);
              return (
                <button
                  key={project.id}
                  onClick={() => router.push(`/project/${project.id}`)}
                  className={cn(
                    "flex w-full items-center gap-2.5 rounded-lg px-3 py-1.5 text-[11px] transition-all",
                    isActive
                      ? "bg-white/[0.08] text-white"
                      : "text-white/35 hover:bg-white/[0.04] hover:text-white/60"
                  )}
                >
                  <FolderOpen className="h-3 w-3 shrink-0" />
                  <span className="truncate">{project.name}</span>
                </button>
              );
            })}
          </div>
        )}
      </nav>

      {/* Bottom */}
      <div className="border-t border-white/[0.04] p-2">
        <button
          onClick={handleLogout}
          className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[12px] text-white/30 transition-all hover:bg-white/[0.04] hover:text-white/60"
        >
          <LogOut className="h-3.5 w-3.5 shrink-0" />
          {!collapsed && <span>Logout</span>}
        </button>
      </div>
    </aside>
  );
}
