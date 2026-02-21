"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import remarkGfm from "remark-gfm";
import { Copy, Check, User, Bot, Wand2 } from "lucide-react";
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
        "group flex gap-4 px-6 py-5 transition-colors",
        isUser ? "bg-transparent" : "bg-card/30"
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
          isUser ? "bg-primary/10" : "bg-green-500/10"
        )}
      >
        {isUser ? (
          <User className="h-4 w-4 text-primary" />
        ) : (
          <Bot className="h-4 w-4 text-green-400" />
        )}
      </div>

      {/* Content */}
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex items-center gap-2">
          <span className="text-xs font-semibold">
            {isUser ? "You" : "Agent Brain"}
          </span>
          <span className="text-[10px] text-muted-foreground">
            {new Date(message.timestamp).toLocaleTimeString()}
          </span>
          {isStreaming && (
            <span className="flex items-center gap-1 text-[10px] text-primary">
              <Wand2 className="h-3 w-3 animate-pulse" />
              Generating...
            </span>
          )}
        </div>

        {/* Markdown content */}
        <div className="prose prose-invert prose-sm max-w-none">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeHighlight]}
            components={{
              pre: ({ children, ...props }) => (
                <div className="group/code relative my-3">
                  <pre
                    className="overflow-x-auto rounded-xl border border-border bg-muted/50 p-4 text-xs"
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
                    className="absolute right-2 top-2 rounded-md bg-muted p-1.5 text-muted-foreground opacity-0 transition-opacity hover:text-foreground group-hover/code:opacity-100"
                  >
                    {copied === message.id + "-code" ? (
                      <Check className="h-3.5 w-3.5 text-green-400" />
                    ) : (
                      <Copy className="h-3.5 w-3.5" />
                    )}
                  </button>
                </div>
              ),
              code: ({ className, children, ...props }) => {
                const isInline = !className;
                if (isInline) {
                  return (
                    <code
                      className="rounded-md bg-muted px-1.5 py-0.5 text-xs text-primary"
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
              p: ({ children }) => <p className="mb-3 leading-relaxed">{children}</p>,
              ul: ({ children }) => <ul className="mb-3 ml-4 list-disc space-y-1">{children}</ul>,
              ol: ({ children }) => <ol className="mb-3 ml-4 list-decimal space-y-1">{children}</ol>,
              h1: ({ children }) => <h1 className="mb-3 mt-4 text-lg font-bold">{children}</h1>,
              h2: ({ children }) => <h2 className="mb-2 mt-3 text-base font-bold">{children}</h2>,
              h3: ({ children }) => <h3 className="mb-2 mt-3 text-sm font-bold">{children}</h3>,
              blockquote: ({ children }) => (
                <blockquote className="mb-3 border-l-2 border-primary pl-4 italic text-muted-foreground">
                  {children}
                </blockquote>
              ),
              a: ({ href, children }) => (
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary underline hover:text-primary/80"
                >
                  {children}
                </a>
              ),
            }}
          >
            {message.content}
          </ReactMarkdown>
          {isStreaming && !message.content && (
            <div className="flex gap-1">
              <span className="h-2 w-2 animate-pulse rounded-full bg-primary" />
              <span className="h-2 w-2 animate-pulse rounded-full bg-primary [animation-delay:0.2s]" />
              <span className="h-2 w-2 animate-pulse rounded-full bg-primary [animation-delay:0.4s]" />
            </div>
          )}
        </div>

        {/* Actions for assistant messages */}
        {!isUser && message.status === "done" && (
          <div className="mt-3 flex items-center gap-2 opacity-0 transition-opacity group-hover:opacity-100">
            <button
              onClick={() => copyToClipboard(message.content, message.id)}
              className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[10px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              {copied === message.id ? (
                <Check className="h-3 w-3 text-green-400" />
              ) : (
                <Copy className="h-3 w-3" />
              )}
              Copy
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
