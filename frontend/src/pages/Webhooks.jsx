import React, { useEffect, useState } from "react";
import AdminLayout from "@/components/AdminLayout";
import api from "@/lib/api";
import { RefreshCw, ShieldCheck, ShieldAlert, ChevronRight, X } from "lucide-react";

export default function Webhooks() {
  const [logs, setLogs] = useState([]);
  const [detail, setDetail] = useState(null);

  const load = async () => {
    const { data } = await api.get("/webhook-logs", { params: { limit: 200 } });
    setLogs(data);
  };
  useEffect(() => { load(); }, []);

  return (
    <AdminLayout title="Webhook Logs" subtitle="Razorpay events" actions={
      <button onClick={load} data-testid="webhooks-refresh" className="btn-ghost text-xs flex items-center gap-2">
        <RefreshCw className="w-3.5 h-3.5" /> Refresh
      </button>
    }>
      <div className="panel">
        <table className="dense w-full">
          <thead>
            <tr><th>Time</th><th>Event</th><th>Signature</th><th>Processed</th><th>Error</th><th></th></tr>
          </thead>
          <tbody>
            {logs.length === 0 ? (
              <tr><td colSpan="6" className="text-center text-[#6B7280] py-10">No webhook events captured yet.</td></tr>
            ) : logs.map((l) => (
              <tr key={l.id} data-testid={`wh-${l.id}`}>
                <td className="mono text-[#9CA3AF]">{l.created_at?.slice(0, 19).replace("T", " ")}</td>
                <td className="mono">{l.event}</td>
                <td>
                  {l.signature_valid ? (
                    <span className="inline-flex items-center gap-1 text-[#00A25B] text-xs font-mono-plex"><ShieldCheck className="w-3.5 h-3.5" /> valid</span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-[#E92C2C] text-xs font-mono-plex"><ShieldAlert className="w-3.5 h-3.5" /> invalid</span>
                  )}
                </td>
                <td className="mono">{l.processed ? "yes" : "no"}</td>
                <td className="text-xs text-[#E92C2C] truncate max-w-xs">{l.error || "—"}</td>
                <td><button data-testid={`wh-view-${l.id}`} onClick={() => setDetail(l)} className="text-[#F58220] text-xs flex items-center gap-1">Payload <ChevronRight className="w-3.5 h-3.5" /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {detail && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4" onClick={() => setDetail(null)}>
          <div className="panel w-full max-w-2xl p-6" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <div>
                <div className="kicker">Event</div>
                <div className="font-chivo font-bold text-lg">{detail.event}</div>
              </div>
              <button onClick={() => setDetail(null)}><X className="w-4 h-4 text-[#9CA3AF]" /></button>
            </div>
            <pre className="font-mono-plex text-[11px] bg-[#0A0A0A] border border-[#27272A] p-4 rounded-sm max-h-[60vh] overflow-auto">{JSON.stringify(detail.payload, null, 2)}</pre>
          </div>
        </div>
      )}
    </AdminLayout>
  );
}
