"use client";

import { useEffect } from "react";
import { Settings, Brain, Thermometer, Hash, Zap } from "lucide-react";
import { useChatStore } from "@/store/chatStore";
import { listModels } from "@/lib/api";

export default function ModelSelector() {
  const { modelSettings, setModelSettings, availableModels, setAvailableModels } =
    useChatStore();

  useEffect(() => {
    fetchModels();
  }, []);

  const fetchModels = async () => {
    try {
      const resp = await listModels();
      const names = (resp.data.models || []).map((m: any) => m.name);
      setAvailableModels(names);
      if (names.length > 0 && !names.includes(modelSettings.model)) {
        setModelSettings({ model: names[0] });
      }
    } catch {
      setAvailableModels(["llama3.2", "llama3.1", "codellama", "mistral"]);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-card/50 px-4 py-2.5">
      {/* Model select */}
      <div className="flex items-center gap-2">
        <Brain className="h-3.5 w-3.5 text-muted-foreground" />
        <select
          value={modelSettings.model}
          onChange={(e) => setModelSettings({ model: e.target.value })}
          className="rounded-lg border border-border bg-muted/50 px-2 py-1 text-xs outline-none focus:border-primary"
        >
          {availableModels.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </div>

      {/* Temperature */}
      <div className="flex items-center gap-2">
        <Thermometer className="h-3.5 w-3.5 text-muted-foreground" />
        <input
          type="range"
          min="0"
          max="1"
          step="0.1"
          value={modelSettings.temperature}
          onChange={(e) => setModelSettings({ temperature: parseFloat(e.target.value) })}
          className="h-1 w-16 cursor-pointer accent-primary"
        />
        <span className="text-[10px] text-muted-foreground">
          {modelSettings.temperature}
        </span>
      </div>

      {/* Max tokens */}
      <div className="flex items-center gap-2">
        <Hash className="h-3.5 w-3.5 text-muted-foreground" />
        <select
          value={modelSettings.maxTokens}
          onChange={(e) => setModelSettings({ maxTokens: parseInt(e.target.value) })}
          className="rounded-lg border border-border bg-muted/50 px-2 py-1 text-xs outline-none focus:border-primary"
        >
          <option value={1024}>1K</option>
          <option value={2048}>2K</option>
          <option value={4096}>4K</option>
          <option value={8192}>8K</option>
          <option value={16384}>16K</option>
        </select>
      </div>

      {/* Toggles */}
      <div className="flex items-center gap-3 border-l border-border pl-3">
        <Toggle
          label="Memory"
          active={modelSettings.useMemory}
          onChange={(v) => setModelSettings({ useMemory: v })}
        />
        <Toggle
          label="Context"
          active={modelSettings.useProjectContext}
          onChange={(v) => setModelSettings({ useProjectContext: v })}
        />
        <Toggle
          label="Orchestration"
          active={modelSettings.useOrchestration}
          onChange={(v) => setModelSettings({ useOrchestration: v })}
        />
      </div>
    </div>
  );
}

function Toggle({
  label,
  active,
  onChange,
}: {
  label: string;
  active: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <button
      onClick={() => onChange(!active)}
      className={`rounded-md px-2 py-1 text-[10px] font-medium transition-colors ${
        active
          ? "bg-primary/10 text-primary"
          : "bg-muted text-muted-foreground hover:text-foreground"
      }`}
    >
      {label}
    </button>
  );
}
