import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import api from "@/lib/api";
import { toast } from "sonner";
import { TerminalSquare, Lock } from "lucide-react";

export default function Login() {
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const { data } = await api.post("/auth/login", { email, password });
      localStorage.setItem("fnot_token", data.token);
      localStorage.setItem("fnot_email", data.email);
      toast.success("Signed in");
      nav("/admin");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0A0A0A] px-4">
      <div className="w-full max-w-md">
        <div className="flex items-center gap-2 mb-8">
          <TerminalSquare className="w-6 h-6 text-[#F58220]" strokeWidth={1.5} />
          <span className="font-chivo font-black text-xl tracking-tight">FnO TATTVA</span>
          <span className="kicker ml-2">access console</span>
        </div>
        <div className="panel p-8">
          <div className="kicker mb-1">Restricted</div>
          <h1 className="font-chivo font-black text-3xl tracking-tight mb-1">Admin sign-in</h1>
          <p className="text-sm text-[#9CA3AF] mb-6">Only authorised operators may proceed.</p>

          <form onSubmit={submit} className="space-y-4" data-testid="login-form">
            <div>
              <label className="kicker block mb-1.5">Email</label>
              <input
                data-testid="login-email"
                type="email" required autoFocus
                value={email} onChange={(e) => setEmail(e.target.value)}
                className="w-full bg-transparent border border-[#27272A] focus:border-[#F58220] outline-none px-3 py-2.5 text-sm rounded-sm"
                placeholder="admin@fnotattva.com"
              />
            </div>
            <div>
              <label className="kicker block mb-1.5">Password</label>
              <input
                data-testid="login-password"
                type="password" required
                value={password} onChange={(e) => setPassword(e.target.value)}
                className="w-full bg-transparent border border-[#27272A] focus:border-[#F58220] outline-none px-3 py-2.5 text-sm rounded-sm"
                placeholder="••••••••"
              />
            </div>
            <button
              data-testid="login-submit"
              type="submit" disabled={loading}
              className="btn-primary w-full flex items-center gap-2 justify-center mt-2"
            >
              <Lock className="w-4 h-4" strokeWidth={2} />
              {loading ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </div>

        <div className="mt-6 flex justify-between text-xs text-[#6B7280]">
          <Link to="/" className="hover:text-[#F58220]" data-testid="back-to-landing">← Back to home</Link>
          <span className="font-mono-plex">v1.0 · IST</span>
        </div>
      </div>
    </div>
  );
}
