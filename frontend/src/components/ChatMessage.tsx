"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import remarkGfm from "remark-gfm";
import { Copy, Check, User, Bot, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChatMessage as ChatMessageType } from "@/store/chatStore";

interface ChatMessageProps {
  message: ChatMessageType;
}

export default function ChatMessage({ message }: ChatMessageProps) {
  const [copied, setCopied] = useState<string | null>(null);
  const isUser = message.role === "user";
  const isStreaming = message.status === "streaming";

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopied(id);
    setTimeout(() => setCopied(null), 2000);
  };

  return (
    <div
      className={cn(
        "group flex gap-3 px-5 py-4 transition-colors",
        isUser ? "bg-transparent" : "bg-white/[0.015]"
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          "flex h-7 w-7 shrink-0 items-center justify-center rounded-md",
          isUser ? "bg-white/[0.06]" : "bg-white/[0.04]"
        )}
      >
        {isUser ? (
          <User className="h-3.5 w-3.5 text-white/50" />
        ) : (
          <Bot className="h-3.5 w-3.5 text-white/40" />
        )}
      </div>

      {/* Content */}
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex items-center gap-2">
          <span className="text-[11px] font-medium text-white/60">
            {isUser ? "You" : "Agent Brain"}
          </span>
          <span className="text-[9px] text-white/15">
            {new Date(message.timestamp).toLocaleTimeString()}
          </span>
          {isStreaming && (
            <span className="flex items-center gap-1 text-[9px] text-white/30">
              <Loader2 className="h-2.5 w-2.5 animate-spin" />
              Generating...
            </span>
          )}
        </div>

        {/* Markdown content */}
        <div className="prose prose-invert prose-sm max-w-none text-[13px] text-white/75 leading-relaxed">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeHighlight]}
            components={{
              pre: ({ children, ...props }) => (
                <div className="group/code relative my-2.5">
                  <pre
                    className="overflow-x-auto rounded-lg border border-white/[0.04] bg-white/[0.02] p-3 text-[11px]"
                    {...props}
                  >
                    {children}
                  </pre>
                  <button
                    onClick={() => {
                      const codeEl = (props as any).node?.children?.[0];
                      const text =
                        typeof codeEl === "string"
                          ? codeEl
                          : (children as any)?.props?.children || "";
                      copyToClipboard(String(text), message.id + "-code");
                    }}
                    className="absolute right-1.5 top-1.5 rounded-md bg-white/[0.04] p-1 text-white/20 opacity-0 transition-all hover:bg-white/[0.08] hover:text-white/50 group-hover/code:opacity-100"
                  >
                    {copied === message.id + "-code" ? (
                      <Check className="h-3 w-3 text-emerald-400/70" />
                    ) : (
                      <Copy className="h-3 w-3" />
                    )}
                  </button>
                </div>
              ),
              code: ({ className, children, ...props }) => {
                const isInline = !className;
                if (isInline) {
                  return (
                    <code
                      className="rounded-md bg-white/[0.06] px-1.5 py-0.5 text-[11px] text-white/70"
                      {...props}
                    >
                      {children}
                    </code>
                  );
                }
                return (
                  <code className={className} {...props}>
                    {children}
                  </code>
                );
              },
              p: ({ children }) => <p className="mb-2.5 leading-relaxed">{children}</p>,
              ul: ({ children }) => <ul className="mb-2.5 ml-4 list-disc space-y-1">{children}</ul>,
              ol: ({ children }) => <ol className="mb-2.5 ml-4 list-decimal space-y-1">{children}</ol>,
              h1: ({ children }) => <h1 className="mb-2 mt-3 text-base font-semibold text-white/85">{children}</h1>,
              h2: ({ children }) => <h2 className="mb-2 mt-3 text-sm font-semibold text-white/85">{children}</h2>,
              h3: ({ children }) => <h3 className="mb-1.5 mt-2 text-[13px] font-semibold text-white/80">{children}</h3>,
              blockquote: ({ children }) => (
                <blockquote className="mb-2.5 border-l-2 border-white/10 pl-3 italic text-white/40">
                  {children}
                </blockquote>
              ),
              a: ({ href, children }) => (
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-white/70 underline decoration-white/20 hover:text-white/90"
                >
                  {children}
                </a>
              ),
            }}
          >
            {message.content}
          </ReactMarkdown>
          {isStreaming && !message.content && (
            <div className="flex gap-1 py-1">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white/20" />
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white/20 [animation-delay:0.2s]" />
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white/20 [animation-delay:0.4s]" />
            </div>
          )}
        </div>

        {/* Actions for assistant messages */}
        {!isUser && message.status === "done" && (
          <div className="mt-2 flex items-center gap-2 opacity-0 transition-opacity group-hover:opacity-100">
            <button
              onClick={() => copyToClipboard(message.content, message.id)}
              className="flex items-center gap-1 rounded-md px-2 py-1 text-[9px] text-white/20 transition-all hover:bg-white/[0.04] hover:text-white/50"
            >
              {copied === message.id ? (
                <Check className="h-2.5 w-2.5 text-emerald-400/70" />
              ) : (
                <Copy className="h-2.5 w-2.5" />
              )}
              Copy
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
