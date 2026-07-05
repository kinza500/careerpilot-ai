"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, setToken } from "@/lib/api";
import { Compass, Loader2, ShieldCheck } from "lucide-react";

export default function Home() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    setLoading(true);
    try {
      const res =
        mode === "login"
          ? await api.login(email, password)
          : await api.register(email, password, name);
      setToken(res.access_token);
      router.push("/dashboard");
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-5xl items-center justify-center px-4">
      <div className="grid w-full gap-10 md:grid-cols-2">
        <div className="hidden flex-col justify-center md:flex">
          <div className="mb-3 flex items-center gap-2 text-brand">
            <Compass /> <span className="text-2xl font-bold">CareerPilot AI</span>
          </div>
          <p className="mb-6 text-lg text-slate-600">
            An autonomous multi-agent system that understands your resume, finds
            roles, explains the fit, and drafts tailored applications — with you
            approving every outbound action.
          </p>
          <div className="flex items-start gap-2 rounded-lg bg-teal-50 p-3 text-sm text-teal-800">
            <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0" />
            <span>
              Your CV is private. It is encrypted at rest, isolated per user by
              database row-level security, and processed only by a model that
              does not train on your data.
            </span>
          </div>
        </div>

        <div className="card">
          <div className="mb-4 flex gap-2">
            <button
              className={mode === "login" ? "btn" : "btn-ghost"}
              onClick={() => setMode("login")}
            >
              Log in
            </button>
            <button
              className={mode === "register" ? "btn" : "btn-ghost"}
              onClick={() => setMode("register")}
            >
              Sign up
            </button>
          </div>
          <form onSubmit={submit} className="space-y-3">
            {mode === "register" && (
              <input
                className="input"
                placeholder="Full name"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            )}
            <input
              className="input"
              type="email"
              placeholder="Email"
              value={email}
              required
              onChange={(e) => setEmail(e.target.value)}
            />
            <input
              className="input"
              type="password"
              placeholder="Password (min 8 chars)"
              value={password}
              required
              minLength={8}
              onChange={(e) => setPassword(e.target.value)}
            />
            {err && <p className="text-sm text-red-600">{err}</p>}
            <button className="btn w-full justify-center" disabled={loading}>
              {loading && <Loader2 className="h-4 w-4 animate-spin" />}
              {mode === "login" ? "Log in" : "Create account"}
            </button>
          </form>
        </div>
      </div>
    </main>
  );
}
