"use client";

import { useEffect } from "react";
import { Brain, Thermometer, Hash } from "lucide-react";
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
      setAvailableModels(["qwen2.5:1.5b", "qwen2.5:7b"]);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2.5 rounded-lg border border-white/[0.04] bg-white/[0.02] px-3 py-1.5">
      {/* Model select */}
      <div className="flex items-center gap-1.5">
        <Brain className="h-3 w-3 text-white/20" />
        <select
          value={modelSettings.model}
          onChange={(e) => setModelSettings({ model: e.target.value })}
          className="rounded-md border border-white/[0.06] bg-white/[0.03] px-1.5 py-0.5 text-[10px] text-white/60 outline-none focus:border-white/[0.12]"
        >
          {availableModels.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </div>

      {/* Temperature */}
      <div className="flex items-center gap-1.5">
        <Thermometer className="h-3 w-3 text-white/20" />
        <input
          type="range"
          min="0"
          max="1"
          step="0.1"
          value={modelSettings.temperature}
          onChange={(e) => setModelSettings({ temperature: parseFloat(e.target.value) })}
          className="h-0.5 w-12 cursor-pointer accent-white/50"
        />
        <span className="text-[9px] text-white/25">{modelSettings.temperature}</span>
      </div>

      {/* Max tokens */}
      <div className="flex items-center gap-1.5">
        <Hash className="h-3 w-3 text-white/20" />
        <select
          value={modelSettings.maxTokens}
          onChange={(e) => setModelSettings({ maxTokens: parseInt(e.target.value) })}
          className="rounded-md border border-white/[0.06] bg-white/[0.03] px-1.5 py-0.5 text-[10px] text-white/60 outline-none focus:border-white/[0.12]"
        >
          <option value={1024}>1K</option>
          <option value={2048}>2K</option>
          <option value={4096}>4K</option>
          <option value={8192}>8K</option>
        </select>
      </div>

      {/* Toggles */}
      <div className="flex items-center gap-1.5 border-l border-white/[0.04] pl-2.5">
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
      className={`rounded-md px-1.5 py-0.5 text-[9px] font-medium transition-all ${
        active
          ? "bg-white/[0.08] text-white/60"
          : "bg-transparent text-white/20 hover:text-white/40"
      }`}
    >
      {label}
    </button>
  );
}
