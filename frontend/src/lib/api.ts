import axios from "axios";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 30000,
});

api.interceptors.request.use((config) => {
  const apiKey = typeof window !== "undefined" ? localStorage.getItem("api_key") : null;
  if (apiKey) {
    config.headers["X-API-Key"] = apiKey;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      if (typeof window !== "undefined") {
        localStorage.removeItem("auth_token");
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

// Health
export const checkHealth = () => api.get("/health");

// Projects
export const listProjects = (limit = 50, offset = 0) =>
  api.get(`/projects/?limit=${limit}&offset=${offset}`);

export const getProjectDetails = (projectId: string) =>
  api.get(`/projects/${projectId}/details`);

export const getProjectSummary = (projectId: string) =>
  api.get(`/projects/${projectId}/summary`);

export const getProjectComponents = (
  projectId: string,
  params?: { component_type?: string; language?: string; limit?: number; offset?: number }
) => api.get(`/projects/${projectId}/components`, { params });

export const getProjectAnalytics = (projectId: string) =>
  api.get(`/projects/${projectId}/analytics`);

export const getProjectHealth = (projectId: string) =>
  api.get(`/projects/${projectId}/health`);

export const analyzeProject = (data: {
  project_path: string;
  project_name?: string;
  force_reindex?: boolean;
}) => api.post("/projects/analyze", data);

export const analyzeDependencies = (data: {
  project_id: string;
  include_impact_analysis?: boolean;
  component_id?: string;
}) => api.post("/projects/dependencies/analyze", data);

export const deleteProject = (projectId: string) =>
  api.delete(`/projects/${projectId}`);

// Memory
export const searchMemory = (data: {
  query: string;
  agent_id?: string;
  memory_type?: string;
  top_k?: number;
  min_similarity?: number;
}) => api.post("/memory/search", data);

export const storeMemory = (data: {
  content: string;
  memory_type?: string;
  agent_id?: string;
  metadata?: Record<string, unknown>;
  importance?: number;
}) => api.post("/memory/store", data);

// Chat
export const chatSend = (data: {
  message: string;
  project_id?: string;
  session_id?: string;
  model?: string;
  temperature?: number;
  max_tokens?: number;
  use_memory?: boolean;
  use_project_context?: boolean;
  images?: string[];
}) => api.post("/chat/send", data);

export const listModels = () => api.get("/chat/models");

// Semantic search
export const searchCode = (data: {
  query: string;
  language?: string;
  context?: string;
  max_results?: number;
}) => api.post("/semantic/search/code", data);

// Orchestration
export const runOrchestration = (data: {
  input: string;
  workflow?: string;
  auto_route?: boolean;
}) => api.post("/orchestration/run", data);

export const listWorkflows = () => api.get("/orchestration/workflows/list");

// Enhanced
export const getGitStatus = (projectPath: string) =>
  api.get("/enhanced/git/status", { params: { project_path: projectPath } });

export const getCommitHistory = (projectPath: string, limit = 10) =>
  api.get("/enhanced/git/commits", { params: { project_path: projectPath, limit } });

// Streaming chat helper
export async function* streamChat(data: {
  message: string;
  project_id?: string;
  session_id?: string;
  model?: string;
  temperature?: number;
  max_tokens?: number;
  use_memory?: boolean;
  use_project_context?: boolean;
  images?: string[];
}): AsyncGenerator<{ type: string; content: string }> {
  const response = await fetch(`${API_URL}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    throw new Error(`Chat stream error: ${response.statusText}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        try {
          const parsed = JSON.parse(line.slice(6));
          yield parsed;
        } catch {
          // skip malformed
        }
      }
    }
  }
}
