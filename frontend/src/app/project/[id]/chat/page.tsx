"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import {
  ArrowLeft,
  Send,
  Plus,
  Trash2,
  ImageIcon,
  MessageSquare,
  Loader2,
} from "lucide-react";
import Sidebar from "@/components/Sidebar";
import ChatMessage from "@/components/ChatMessage";
import ModelSelector from "@/components/ModelSelector";
import { useChatStore, type ChatSession, type ChatMessage as ChatMsg } from "@/store/chatStore";
import { streamChat } from "@/lib/api";

export default function ChatPage() {
  const router = useRouter();
  const params = useParams();
  const projectId = params.id as string;

  const {
    sessions,
    currentSessionId,
    modelSettings,
    isStreaming,
    streamingStatus,
    getCurrentSession,
    addSession,
    setCurrentSession,
    addMessage,
    updateMessage,
    appendToMessage,
    setIsStreaming,
    setStreamingStatus,
    loadSessionsFromStorage,
    deleteSession,
  } = useChatStore();

  const [input, setInput] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [images, setImages] = useState<string[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!localStorage.getItem("auth_token")) {
      router.push("/login");
      return;
    }
    loadSessionsFromStorage(projectId);
  }, [projectId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [getCurrentSession()?.messages]);

  const createNewSession = useCallback(() => {
    const session: ChatSession = {
      id: crypto.randomUUID(),
      title: `Chat ${sessions.length + 1}`,
      projectId,
      messages: [],
      createdAt: new Date().toISOString(),
    };
    addSession(session);
  }, [sessions.length, projectId, addSession]);

  const handleSend = async () => {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;

    let sessionId = currentSessionId;
    if (!sessionId) {
      const session: ChatSession = {
        id: crypto.randomUUID(),
        title: trimmed.slice(0, 40),
        projectId,
        messages: [],
        createdAt: new Date().toISOString(),
      };
      addSession(session);
      sessionId = session.id;
    }

    // Add user message
    const userMsg: ChatMsg = {
      id: crypto.randomUUID(),
      role: "user",
      content: trimmed,
      timestamp: new Date().toISOString(),
      status: "done",
    };
    addMessage(sessionId, userMsg);
    setInput("");
    setImages([]);

    // Auto-resize textarea
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }

    // Add assistant placeholder
    const assistantMsgId = crypto.randomUUID();
    const assistantMsg: ChatMsg = {
      id: assistantMsgId,
      role: "assistant",
      content: "",
      timestamp: new Date().toISOString(),
      status: "streaming",
    };
    addMessage(sessionId, assistantMsg);
    setIsStreaming(true);

    try {
      for await (const chunk of streamChat({
        message: trimmed,
        project_id: projectId,
        session_id: sessionId,
        model: modelSettings.model,
        temperature: modelSettings.temperature,
        max_tokens: modelSettings.maxTokens,
        use_memory: modelSettings.useMemory,
        use_project_context: modelSettings.useProjectContext,
        images: images.length > 0 ? images : undefined,
      })) {
        if (chunk.type === "status") {
          setStreamingStatus(chunk.content);
        } else if (chunk.type === "token") {
          appendToMessage(sessionId!, assistantMsgId, chunk.content);
        } else if (chunk.type === "error") {
          updateMessage(sessionId!, assistantMsgId, {
            content: `Error: ${chunk.content}`,
            status: "error",
          });
          break;
        } else if (chunk.type === "done") {
          updateMessage(sessionId!, assistantMsgId, { status: "done" });
        }
      }
    } catch (err: any) {
      updateMessage(sessionId!, assistantMsgId, {
        content: `Connection error: ${err.message}`,
        status: "error",
      });
    } finally {
      setIsStreaming(false);
      setStreamingStatus("");
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      handleSend();
    }
  };

  const handleImageUpload = (files: FileList | null) => {
    if (!files) return;
    Array.from(files).forEach((file) => {
      if (file.type.startsWith("image/")) {
        const reader = new FileReader();
        reader.onload = () => {
          const base64 = (reader.result as string).split(",")[1];
          setImages((prev) => [...prev, base64]);
        };
        reader.readAsDataURL(file);
      }
    });
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    handleImageUpload(e.dataTransfer.files);
  };

  const currentSession = getCurrentSession();
  const messages = currentSession?.messages || [];

  return (
    <div className="flex h-screen">
      <Sidebar />

      {/* Chat sidebar */}
      <div className="flex w-60 flex-col border-r border-border bg-card/30">
        <div className="flex items-center justify-between border-b border-border p-3">
          <h2 className="text-xs font-semibold">Chats</h2>
          <button
            onClick={createNewSession}
            className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <Plus className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {sessions.map((s) => (
            <div
              key={s.id}
              className={`group mb-1 flex cursor-pointer items-center justify-between rounded-lg px-3 py-2 text-xs transition-colors ${
                s.id === currentSessionId
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              }`}
              onClick={() => setCurrentSession(s.id)}
            >
              <div className="flex items-center gap-2 truncate">
                <MessageSquare className="h-3.5 w-3.5 shrink-0" />
                <span className="truncate">{s.title}</span>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  deleteSession(s.id);
                }}
                className="shrink-0 rounded p-1 opacity-0 transition-opacity hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))}
          {sessions.length === 0 && (
            <p className="px-3 py-4 text-center text-[10px] text-muted-foreground">
              No chats yet. Click + to start.
            </p>
          )}
        </div>
      </div>

      {/* Main chat area */}
      <div className="flex flex-1 flex-col">
        {/* Top bar */}
        <div className="flex items-center justify-between border-b border-border px-4 py-2">
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.push(`/project/${projectId}`)}
              className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
            <span className="text-sm font-medium">
              {currentSession?.title || "New Chat"}
            </span>
            {streamingStatus && (
              <span className="flex items-center gap-1.5 text-xs text-primary">
                <Loader2 className="h-3 w-3 animate-spin" />
                {streamingStatus}
              </span>
            )}
          </div>
          <ModelSelector />
        </div>

        {/* Messages */}
        <div
          className="flex-1 overflow-y-auto"
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
        >
          {dragOver && (
            <div className="absolute inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
              <div className="flex flex-col items-center gap-2 rounded-2xl border-2 border-dashed border-primary p-8">
                <ImageIcon className="h-8 w-8 text-primary" />
                <p className="text-sm text-primary">Drop image here</p>
              </div>
            </div>
          )}

          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-4 px-8 text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10">
                <MessageSquare className="h-8 w-8 text-primary" />
              </div>
              <h2 className="text-lg font-semibold">Start a conversation</h2>
              <p className="max-w-md text-sm text-muted-foreground">
                Ask questions about your project, search code, get recommendations,
                or discuss architecture decisions.
              </p>
              <div className="flex flex-wrap justify-center gap-2">
                {[
                  "Explain the project structure",
                  "Find security issues",
                  "Suggest refactoring",
                  "Analyze dependencies",
                ].map((q) => (
                  <button
                    key={q}
                    onClick={() => {
                      setInput(q);
                      textareaRef.current?.focus();
                    }}
                    className="rounded-xl border border-border bg-card/50 px-4 py-2 text-xs text-muted-foreground transition-colors hover:border-primary/30 hover:text-foreground"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="divide-y divide-border/50">
              {messages.map((msg) => (
                <ChatMessage key={msg.id} message={msg} />
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Image previews */}
        {images.length > 0 && (
          <div className="flex gap-2 border-t border-border px-4 py-2">
            {images.map((img, i) => (
              <div key={i} className="relative">
                <img
                  src={`data:image/png;base64,${img}`}
                  alt="upload"
                  className="h-16 w-16 rounded-lg object-cover"
                />
                <button
                  onClick={() => setImages((prev) => prev.filter((_, idx) => idx !== i))}
                  className="absolute -right-1 -top-1 rounded-full bg-destructive p-0.5 text-destructive-foreground"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Input */}
        <div className="border-t border-border p-4">
          <div className="flex items-end gap-3">
            <label className="cursor-pointer rounded-lg p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground">
              <ImageIcon className="h-5 w-5" />
              <input
                type="file"
                accept="image/*"
                multiple
                className="hidden"
                onChange={(e) => handleImageUpload(e.target.files)}
              />
            </label>
            <div className="relative flex-1">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => {
                  setInput(e.target.value);
                  e.target.style.height = "auto";
                  e.target.style.height = Math.min(e.target.scrollHeight, 200) + "px";
                }}
                onKeyDown={handleKeyDown}
                placeholder="Ask about your project... (Cmd+Enter to send)"
                rows={1}
                className="w-full resize-none rounded-xl border border-border bg-muted/50 px-4 py-3 pr-12 text-sm outline-none transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
              />
            </div>
            <button
              onClick={handleSend}
              disabled={!input.trim() || isStreaming}
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
            >
              {isStreaming ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
