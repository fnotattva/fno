import React, { useEffect, useState } from "react";
import AdminLayout from "@/components/AdminLayout";
import api from "@/lib/api";
import { RefreshCw } from "lucide-react";

const STATUS_CLR = {
  captured: "#00A25B",
  failed: "#E92C2C",
  refunded: "#A855F7",
  pending: "#F58220",
};

export default function Payments() {
  const [rows, setRows] = useState([]);
  const [filter, setFilter] = useState("");

  const load = async () => {
    const { data } = await api.get("/payments", { params: filter ? { status: filter } : {} });
    setRows(data);
  };
  useEffect(() => { load(); }, [filter]);

  const totals = rows.reduce(
    (acc, r) => {
      acc.count++;
      if (r.status === "captured") acc.captured += Number(r.amount || 0);
      if (r.status === "failed") acc.failed++;
      return acc;
    },
    { count: 0, captured: 0, failed: 0 }
  );

  return (
    <AdminLayout title="Payment History" subtitle="Ledger" actions={
      <button onClick={load} data-testid="payments-refresh" className="btn-ghost text-xs flex items-center gap-2">
        <RefreshCw className="w-3.5 h-3.5" /> Refresh
      </button>
    }>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-6">
        <KPI label="Records" value={totals.count} />
        <KPI label="Captured (INR)" value={`₹${totals.captured.toLocaleString("en-IN")}`} color="#00A25B" />
        <KPI label="Failed events" value={totals.failed} color="#E92C2C" />
      </div>

      <div className="flex items-center gap-2 mb-4">
        {["", "captured", "failed", "refunded", "pending"].map((s) => (
          <button key={s || "ALL"} data-testid={`pay-filter-${s || "ALL"}`} onClick={() => setFilter(s)}
            className={`px-3 py-1.5 text-[11px] font-mono-plex uppercase tracking-[0.18em] rounded-sm border ${
              filter === s ? "bg-[#F58220] text-black border-[#F58220]" : "border-[#27272A] text-[#9CA3AF] hover:border-[#F58220]"
            }`}>{s || "ALL"}</button>
        ))}
      </div>

      <div className="panel">
        <table className="dense w-full">
          <thead>
            <tr>
              <th>Time</th><th>Status</th><th>Amount</th><th>Method</th><th>Payment ID</th><th>Subscription</th><th>Desc</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr><td colSpan="7" className="text-center text-[#6B7280] py-10">No payment events yet. Webhook events land here.</td></tr>
            ) : rows.map((r) => (
              <tr key={r.id}>
                <td className="mono text-[#9CA3AF]">{r.created_at?.slice(0, 19).replace("T", " ")}</td>
                <td className="mono uppercase" style={{ color: STATUS_CLR[r.status] || "#9CA3AF" }}>{r.status}</td>
                <td className="mono">{r.amount != null ? `₹${Number(r.amount).toLocaleString("en-IN")}` : "—"}</td>
                <td className="mono">{r.method || "—"}</td>
                <td className="mono text-[#F58220]">{r.razorpay_payment_id || "—"}</td>
                <td className="mono text-[#9CA3AF]">{r.razorpay_subscription_id || "—"}</td>
                <td className="text-xs">{r.description || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </AdminLayout>
  );
}

function KPI({ label, value, color = "#F3F4F6" }) {
  return (
    <div className="panel p-4">
      <div className="kicker">{label}</div>
      <div className="font-mono-plex text-3xl mt-2 tabular-nums" style={{ color }}>{value}</div>
    </div>
  );
}
