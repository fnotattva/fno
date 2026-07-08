import React, { useEffect, useState } from "react";
import AdminLayout from "@/components/AdminLayout";
import api from "@/lib/api";
import { Users, AlertTriangle, TrendingUp, XCircle, CheckCircle2, Pause, Ban, RefreshCw } from "lucide-react";
import StatusPill from "@/components/StatusPill";
import { Link } from "react-router-dom";

const kpiDef = [
  { key: "ACTIVE", icon: CheckCircle2, label: "Active", color: "#00A25B" },
  { key: "GRACE", icon: AlertTriangle, label: "Grace", color: "#F58220" },
  { key: "EXPIRED", icon: XCircle, label: "Expired", color: "#E92C2C" },
  { key: "CANCELLED", icon: Pause, label: "Cancelled", color: "#9CA3AF" },
  { key: "REFUNDED", icon: RefreshCw, label: "Refunded", color: "#A855F7" },
  { key: "ADMIN_COMP", icon: Ban, label: "Comp", color: "#3B82F6" },
];

export default function Overview() {
  const [stats, setStats] = useState(null);
  const [recent, setRecent] = useState([]);
  const [health, setHealth] = useState(null);

  const load = async () => {
    const [s, r, h] = await Promise.all([
      api.get("/subscribers/stats"),
      api.get("/subscribers", { params: { q: "" } }),
      api.get("/"),
    ]);
    setStats(s.data);
    setRecent(r.data.slice(0, 8));
    setHealth(h.data);
  };
  useEffect(() => { load(); }, []);

  return (
    <AdminLayout title="Operations Overview" subtitle="Control Room · Live" actions={
      <button data-testid="overview-refresh" onClick={load} className="btn-ghost text-xs flex items-center gap-2">
        <RefreshCw className="w-3.5 h-3.5" /> Refresh
      </button>
    }>
      {/* Integration status banner */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-6" data-testid="integration-status">
        <div className="panel px-4 py-3 flex items-center gap-3">
          <div className={`w-2 h-2 rounded-full ${health?.razorpay_configured ? "bg-[#00A25B]" : "bg-[#F58220]"}`} />
          <div>
            <div className="kicker">Razorpay</div>
            <div className="text-sm font-mono-plex">{health?.razorpay_configured ? "Configured" : "Placeholder mode"}</div>
          </div>
        </div>
        <div className="panel px-4 py-3 flex items-center gap-3">
          <div className={`w-2 h-2 rounded-full ${health?.telegram_configured ? "bg-[#00A25B]" : "bg-[#F58220]"}`} />
          <div>
            <div className="kicker">Telegram Bot</div>
            <div className="text-sm font-mono-plex">{health?.telegram_configured ? "Configured" : "Placeholder mode"}</div>
          </div>
        </div>
        <div className="panel px-4 py-3 flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-[#3B82F6]" />
          <div>
            <div className="kicker">Delivery</div>
            <div className="text-sm font-mono-plex">Daily 07:00 IST</div>
          </div>
        </div>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-6" data-testid="kpi-row">
        {kpiDef.map((k) => (
          <div key={k.key} className="panel p-4">
            <div className="flex items-center justify-between">
              <div className="kicker">{k.label}</div>
              <k.icon className="w-4 h-4" style={{ color: k.color }} strokeWidth={1.5} />
            </div>
            <div className="font-mono-plex text-3xl font-semibold mt-2 tabular-nums" style={{ color: k.color }}>
              {stats?.by_status?.[k.key] ?? 0}
            </div>
          </div>
        ))}
      </div>

      {/* Big cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-8">
        <div className="panel p-6 md:col-span-2">
          <div className="kicker">Estimated MRR</div>
          <div className="font-chivo font-black text-5xl mt-2 tabular-nums">
            ₹<span className="font-mono-plex">{(stats?.mrr_estimate_inr ?? 0).toLocaleString("en-IN")}</span>
          </div>
          <div className="text-xs text-[#9CA3AF] mt-2">Sum of amounts across ACTIVE + GRACE subscribers.</div>
        </div>
        <div className="panel p-6">
          <div className="kicker">Failed Payments (24h)</div>
          <div className="font-chivo font-black text-5xl mt-2 tabular-nums text-[#E92C2C]">
            {stats?.failed_payments_today ?? 0}
          </div>
          <div className="text-xs text-[#9CA3AF] mt-2">Auto-moved to GRACE with 2-day window.</div>
        </div>
      </div>

      {/* Recent subscribers */}
      <div className="panel">
        <div className="flex items-center justify-between p-4 border-b border-[#27272A]">
          <div>
            <div className="kicker">Latest signups</div>
            <div className="font-chivo font-bold text-lg mt-0.5">Recent Subscribers</div>
          </div>
          <Link to="/admin/subscribers" data-testid="see-all-subscribers" className="text-xs text-[#F58220] hover:underline font-mono-plex uppercase tracking-[0.18em]">See all →</Link>
        </div>
        <div className="overflow-x-auto">
          <table className="dense w-full">
            <thead>
              <tr>
                <th>Name</th><th>Email</th><th>Mobile</th><th>Status</th><th>Amount</th><th>Joined</th>
              </tr>
            </thead>
            <tbody>
              {recent.length === 0 ? (
                <tr><td colSpan="6" className="text-center text-[#6B7280] py-8">No subscribers yet</td></tr>
              ) : recent.map((s) => (
                <tr key={s.id} data-testid={`recent-row-${s.id}`}>
                  <td>{s.name}</td>
                  <td className="mono">{s.email}</td>
                  <td className="mono">{s.mobile}</td>
                  <td><StatusPill status={s.subscription_status} /></td>
                  <td className="mono">₹{Number(s.amount || 0).toLocaleString("en-IN")}</td>
                  <td className="mono text-[#9CA3AF]">{s.created_at?.slice(0, 10)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </AdminLayout>
  );
}
