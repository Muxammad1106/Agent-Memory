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
      <div className="glass-subtle flex w-52 flex-col">
        <div className="flex items-center justify-between border-b border-white/[0.04] p-3">
          <h2 className="text-[11px] font-medium text-white/40">Chats</h2>
          <button
            onClick={createNewSession}
            className="rounded-md p-1 text-white/20 transition-all hover:bg-white/[0.06] hover:text-white/50"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-1.5">
          {sessions.map((s) => (
            <div
              key={s.id}
              className={`group mb-0.5 flex cursor-pointer items-center justify-between rounded-md px-2.5 py-1.5 text-[11px] transition-all ${
                s.id === currentSessionId
                  ? "bg-white/[0.06] text-white/70"
                  : "text-white/25 hover:bg-white/[0.03] hover:text-white/50"
              }`}
              onClick={() => setCurrentSession(s.id)}
            >
              <div className="flex items-center gap-2 truncate">
                <MessageSquare className="h-3 w-3 shrink-0" />
                <span className="truncate">{s.title}</span>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  deleteSession(s.id);
                }}
                className="shrink-0 rounded p-0.5 opacity-0 transition-all hover:bg-red-500/10 hover:text-red-400/70 group-hover:opacity-100"
              >
                <Trash2 className="h-2.5 w-2.5" />
              </button>
            </div>
          ))}
          {sessions.length === 0 && (
            <p className="px-2 py-6 text-center text-[9px] text-white/15">
              No chats yet. Click + to start.
            </p>
          )}
        </div>
      </div>

      {/* Main chat area */}
      <div className="flex flex-1 flex-col">
        {/* Top bar */}
        <div className="flex items-center justify-between border-b border-white/[0.04] bg-black/40 px-4 py-2 backdrop-blur-xl">
          <div className="flex items-center gap-2.5">
            <button
              onClick={() => router.push(`/project/${projectId}`)}
              className="rounded-md p-1 text-white/20 transition-all hover:bg-white/[0.06] hover:text-white/50"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
            </button>
            <span className="text-[12px] font-medium text-white/60">
              {currentSession?.title || "New Chat"}
            </span>
            {streamingStatus && (
              <span className="flex items-center gap-1 text-[9px] text-white/30">
                <Loader2 className="h-2.5 w-2.5 animate-spin" />
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
            <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm">
              <div className="glass flex flex-col items-center gap-2 rounded-xl p-6">
                <ImageIcon className="h-6 w-6 text-white/40" />
                <p className="text-[11px] text-white/40">Drop image here</p>
              </div>
            </div>
          )}

          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-4 px-8 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-white/[0.04]">
                <MessageSquare className="h-6 w-6 text-white/20" />
              </div>
              <h2 className="text-sm font-medium text-white/60">Start a conversation</h2>
              <p className="max-w-sm text-[11px] text-white/20">
                Ask about your project, search code, or discuss architecture.
              </p>
              <div className="flex flex-wrap justify-center gap-1.5">
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
                    className="glass glass-hover rounded-lg px-3 py-1.5 text-[10px] text-white/25 transition-all hover:text-white/50"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="divide-y divide-white/[0.02]">
              {messages.map((msg) => (
                <ChatMessage key={msg.id} message={msg} />
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Image previews */}
        {images.length > 0 && (
          <div className="flex gap-2 border-t border-white/[0.04] px-4 py-2">
            {images.map((img, i) => (
              <div key={i} className="relative">
                <img
                  src={`data:image/png;base64,${img}`}
                  alt="upload"
                  className="h-12 w-12 rounded-md object-cover opacity-80"
                />
                <button
                  onClick={() => setImages((prev) => prev.filter((_, idx) => idx !== i))}
                  className="absolute -right-1 -top-1 rounded-full bg-red-500/80 p-0.5"
                >
                  <Trash2 className="h-2.5 w-2.5 text-white" />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Input */}
        <div className="border-t border-white/[0.04] p-3">
          <div className="flex items-end gap-2">
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
                className="w-full resize-none rounded-lg border border-white/[0.06] bg-white/[0.03] px-3 py-2.5 text-[13px] text-white/70 outline-none transition-all placeholder:text-white/15 focus:border-white/[0.12] focus:bg-white/[0.05]"
              />
            </div>
            <button
              onClick={handleSend}
              disabled={!input.trim() || isStreaming}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white/90 text-black transition-all hover:bg-white disabled:opacity-30"
            >
              {isStreaming ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Send className="h-3.5 w-3.5" />
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
