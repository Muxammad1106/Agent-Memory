"use client";

import { useRouter, usePathname } from "next/navigation";
import {
  Brain,
  LayoutDashboard,
  FolderOpen,
  MessageSquare,
  Settings,
  LogOut,
  Search,
  Activity,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useProjectStore, type Project } from "@/store/projectStore";

interface SidebarProps {
  collapsed?: boolean;
}

export default function Sidebar({ collapsed = false }: SidebarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { projects, searchQuery, setSearchQuery } = useProjectStore();

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
        "flex h-screen flex-col border-r border-border bg-card/50 transition-all duration-300",
        collapsed ? "w-16" : "w-64"
      )}
    >
      {/* Logo */}
      <div className="flex h-16 items-center gap-3 border-b border-border px-4">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary/10">
          <Brain className="h-5 w-5 text-primary" />
        </div>
        {!collapsed && (
          <div>
            <h1 className="text-sm font-bold">Agent Brain</h1>
            <p className="text-[10px] text-muted-foreground">AI Control Panel</p>
          </div>
        )}
      </div>

      {/* Search */}
      {!collapsed && (
        <div className="px-3 py-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search projects..."
              className="w-full rounded-lg border border-border bg-muted/50 py-2 pl-9 pr-3 text-xs outline-none transition-colors focus:border-primary"
            />
          </div>
        </div>
      )}

      {/* Nav */}
      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-2">
        {navItems.map((item) => {
          const isActive = pathname === item.href;
          return (
            <button
              key={item.href}
              onClick={() => router.push(item.href)}
              className={cn(
                "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors",
                isActive
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              <item.icon className="h-4 w-4 shrink-0" />
              {!collapsed && <span>{item.label}</span>}
            </button>
          );
        })}

        {/* Recent Projects */}
        {!collapsed && recentProjects.length > 0 && (
          <div className="mt-6">
            <p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Recent Projects
            </p>
            {recentProjects.map((project: Project) => {
              const isActive = pathname.includes(`/project/${project.id}`);
              return (
                <button
                  key={project.id}
                  onClick={() => router.push(`/project/${project.id}`)}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-xs transition-colors",
                    isActive
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground"
                  )}
                >
                  <FolderOpen className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">{project.name}</span>
                </button>
              );
            })}
          </div>
        )}
      </nav>

      {/* Bottom */}
      <div className="border-t border-border p-3">
        <button
          onClick={handleLogout}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
        >
          <LogOut className="h-4 w-4 shrink-0" />
          {!collapsed && <span>Logout</span>}
        </button>
      </div>
    </aside>
  );
}
