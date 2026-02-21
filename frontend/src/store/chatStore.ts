import { create } from "zustand";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: string;
  metadata?: Record<string, unknown>;
  status?: "sending" | "streaming" | "done" | "error";
}

export interface ChatSession {
  id: string;
  title: string;
  projectId: string;
  messages: ChatMessage[];
  createdAt: string;
}

export interface ModelSettings {
  model: string;
  temperature: number;
  maxTokens: number;
  useMemory: boolean;
  useProjectContext: boolean;
  useOrchestration: boolean;
  provider: "ollama" | "openai";
}

interface ChatState {
  sessions: ChatSession[];
  currentSessionId: string | null;
  modelSettings: ModelSettings;
  isStreaming: boolean;
  streamingStatus: string;
  availableModels: string[];

  getCurrentSession: () => ChatSession | null;
  addSession: (session: ChatSession) => void;
  setCurrentSession: (id: string) => void;
  addMessage: (sessionId: string, message: ChatMessage) => void;
  updateMessage: (sessionId: string, messageId: string, updates: Partial<ChatMessage>) => void;
  appendToMessage: (sessionId: string, messageId: string, content: string) => void;
  setModelSettings: (settings: Partial<ModelSettings>) => void;
  setIsStreaming: (streaming: boolean) => void;
  setStreamingStatus: (status: string) => void;
  setAvailableModels: (models: string[]) => void;
  loadSessionsFromStorage: (projectId: string) => void;
  saveSessionsToStorage: () => void;
  deleteSession: (id: string) => void;
}

const DEFAULT_SETTINGS: ModelSettings = {
  model: "llama3.2",
  temperature: 0.7,
  maxTokens: 4096,
  useMemory: true,
  useProjectContext: true,
  useOrchestration: false,
  provider: "ollama",
};

export const useChatStore = create<ChatState>((set, get) => ({
  sessions: [],
  currentSessionId: null,
  modelSettings: DEFAULT_SETTINGS,
  isStreaming: false,
  streamingStatus: "",
  availableModels: [],

  getCurrentSession: () => {
    const { sessions, currentSessionId } = get();
    return sessions.find((s) => s.id === currentSessionId) || null;
  },

  addSession: (session) => {
    set((state) => ({
      sessions: [session, ...state.sessions],
      currentSessionId: session.id,
    }));
    get().saveSessionsToStorage();
  },

  setCurrentSession: (id) => set({ currentSessionId: id }),

  addMessage: (sessionId, message) => {
    set((state) => ({
      sessions: state.sessions.map((s) =>
        s.id === sessionId ? { ...s, messages: [...s.messages, message] } : s
      ),
    }));
    get().saveSessionsToStorage();
  },

  updateMessage: (sessionId, messageId, updates) => {
    set((state) => ({
      sessions: state.sessions.map((s) =>
        s.id === sessionId
          ? {
              ...s,
              messages: s.messages.map((m) =>
                m.id === messageId ? { ...m, ...updates } : m
              ),
            }
          : s
      ),
    }));
  },

  appendToMessage: (sessionId, messageId, content) => {
    set((state) => ({
      sessions: state.sessions.map((s) =>
        s.id === sessionId
          ? {
              ...s,
              messages: s.messages.map((m) =>
                m.id === messageId ? { ...m, content: m.content + content } : m
              ),
            }
          : s
      ),
    }));
  },

  setModelSettings: (settings) =>
    set((state) => ({
      modelSettings: { ...state.modelSettings, ...settings },
    })),

  setIsStreaming: (streaming) => set({ isStreaming: streaming }),
  setStreamingStatus: (status) => set({ streamingStatus: status }),
  setAvailableModels: (models) => set({ availableModels: models }),

  loadSessionsFromStorage: (projectId) => {
    if (typeof window === "undefined") return;
    try {
      const stored = localStorage.getItem(`chat_sessions_${projectId}`);
      if (stored) {
        const sessions = JSON.parse(stored) as ChatSession[];
        set({ sessions, currentSessionId: sessions[0]?.id || null });
      } else {
        set({ sessions: [], currentSessionId: null });
      }
    } catch {
      set({ sessions: [], currentSessionId: null });
    }
  },

  saveSessionsToStorage: () => {
    if (typeof window === "undefined") return;
    const { sessions } = get();
    if (sessions.length > 0) {
      const projectId = sessions[0].projectId;
      localStorage.setItem(`chat_sessions_${projectId}`, JSON.stringify(sessions));
    }
  },

  deleteSession: (id) => {
    set((state) => {
      const filtered = state.sessions.filter((s) => s.id !== id);
      return {
        sessions: filtered,
        currentSessionId:
          state.currentSessionId === id ? filtered[0]?.id || null : state.currentSessionId,
      };
    });
    get().saveSessionsToStorage();
  },
}));
