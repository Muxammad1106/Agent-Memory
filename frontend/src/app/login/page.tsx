"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Brain, Eye, EyeOff, Lock, User } from "lucide-react";

const HARDCODED_CREDENTIALS = {
  username: "admin",
  password: "admin123",
};

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    await new Promise((r) => setTimeout(r, 800));

    if (
      username === HARDCODED_CREDENTIALS.username &&
      password === HARDCODED_CREDENTIALS.password
    ) {
      localStorage.setItem("auth_token", "local_session_" + Date.now());
      localStorage.setItem("user", username);
      router.push("/dashboard");
    } else {
      setError("Invalid credentials");
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-black p-4">
      {/* Background gradient */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -left-40 -top-40 h-80 w-80 rounded-full bg-white/[0.02] blur-[120px]" />
        <div className="absolute -bottom-40 -right-40 h-60 w-60 rounded-full bg-white/[0.015] blur-[100px]" />
      </div>

      <div className="glass relative w-full max-w-sm animate-fade-in rounded-2xl p-8">
        {/* Logo */}
        <div className="mb-8 flex flex-col items-center gap-3">
          <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-white/[0.06]">
            <Brain className="h-7 w-7 text-white/70" />
          </div>
          <h1 className="text-xl font-semibold tracking-tight text-white/90">Agent Brain</h1>
          <p className="text-[11px] text-white/25">AI IDE Control Panel</p>
        </div>

        <form onSubmit={handleLogin} className="space-y-4">
          {/* Username */}
          <div className="space-y-1.5">
            <label className="text-[11px] font-medium text-white/30">Username</label>
            <div className="relative">
              <User className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-white/20" />
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Enter username"
                className="w-full rounded-lg border border-white/[0.06] bg-white/[0.03] py-2.5 pl-9 pr-4 text-sm text-white/80 outline-none transition-all placeholder:text-white/15 focus:border-white/[0.15] focus:bg-white/[0.05]"
                required
              />
            </div>
          </div>

          {/* Password */}
          <div className="space-y-1.5">
            <label className="text-[11px] font-medium text-white/30">Password</label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-white/20" />
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter password"
                className="w-full rounded-lg border border-white/[0.06] bg-white/[0.03] py-2.5 pl-9 pr-10 text-sm text-white/80 outline-none transition-all placeholder:text-white/15 focus:border-white/[0.15] focus:bg-white/[0.05]"
                required
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-white/20 hover:text-white/50"
              >
                {showPassword ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
              </button>
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="rounded-lg bg-red-500/10 px-3 py-2 text-[11px] text-red-400/80">
              {error}
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-white/90 py-2.5 text-[12px] font-semibold text-black transition-all hover:bg-white disabled:opacity-40"
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-black border-t-transparent" />
                Signing in...
              </span>
            ) : (
              "Sign In"
            )}
          </button>
        </form>

        <p className="mt-5 text-center text-[10px] text-white/15">
          Default: admin / admin123
        </p>
      </div>
    </div>
  );
}
