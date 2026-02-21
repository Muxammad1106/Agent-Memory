import { create } from "zustand";

export interface Project {
  id: string;
  name: string;
  path: string;
  analysis_status: string;
  last_analyzed: string | null;
  total_files: number;
  total_lines: number;
  architecture_type: string | null;
  languages: string[];
  frameworks: string[];
}

export interface ProjectDetails {
  project: Project & {
    pages_read: number;
    databases: string[];
    build_tools: string[];
  };
  component_statistics: Record<string, number>;
  mcp_analysis: {
    files_processed: number;
    functions_extracted: number;
    classes_extracted: number;
    dependencies_mapped: number;
    last_scan: string | null;
  };
  quality_metrics: Record<string, string>;
}

interface ProjectState {
  projects: Project[];
  currentProject: ProjectDetails | null;
  loading: boolean;
  error: string | null;
  searchQuery: string;
  setProjects: (projects: Project[]) => void;
  setCurrentProject: (project: ProjectDetails | null) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setSearchQuery: (query: string) => void;
  filteredProjects: () => Project[];
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  projects: [],
  currentProject: null,
  loading: false,
  error: null,
  searchQuery: "",
  setProjects: (projects) => set({ projects }),
  setCurrentProject: (project) => set({ currentProject: project }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
  setSearchQuery: (query) => set({ searchQuery: query }),
  filteredProjects: () => {
    const { projects, searchQuery } = get();
    if (!searchQuery) return projects;
    const q = searchQuery.toLowerCase();
    return projects.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        p.path.toLowerCase().includes(q) ||
        (p.languages || []).some((l) => l.toLowerCase().includes(q))
    );
  },
}));
