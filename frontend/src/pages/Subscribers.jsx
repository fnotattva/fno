import React, { useEffect, useState } from "react";
import AdminLayout from "@/components/AdminLayout";
import api from "@/lib/api";
import StatusPill from "@/components/StatusPill";
import { toast } from "sonner";
import { Plus, Search, Trash2, RotateCw, Gift, Ban, X } from "lucide-react";

const STATUSES = ["ALL", "ACTIVE", "GRACE", "EXPIRED", "CANCELLED", "REFUNDED", "ADMIN_COMP"];

export default function Subscribers() {
  const [list, setList] = useState([]);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("ALL");
  const [showAdd, setShowAdd] = useState(false);
  const [selected, setSelected] = useState(null);
  const [addForm, setAddForm] = useState({ name: "", email: "", mobile: "", amount: 999, notes: "" });

  const load = async () => {
    const { data } = await api.get("/subscribers", { params: { q, status } });
    setList(data);
  };
  useEffect(() => { load(); }, [q, status]);

  const add = async (e) => {
    e.preventDefault();
    try {
      await api.post("/subscribers", { ...addForm, subscription_status: "ADMIN_COMP" });
      toast.success("Subscriber added");
      setShowAdd(false);
      setAddForm({ name: "", email: "", mobile: "", amount: 999, notes: "" });
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to add");
    }
  };

  const removeFromChannel = async (id) => {
    if (!window.confirm("Remove this user from the Telegram channel?")) return;
    await api.post(`/subscribers/${id}/remove-from-channel`);
    toast.success("Removed (or ban queued)");
    load();
  };

  const reactivate = async (id) => {
    await api.post(`/subscribers/${id}/reactivate`, { reason: "Manual reactivation" });
    toast.success("Reactivated");
    load();
  };

  const grantComp = async (id) => {
    await api.post(`/subscribers/${id}/comp`, { reason: "Complimentary access" });
    toast.success("Complimentary access granted");
    load();
  };

  const del = async (id) => {
    if (!window.confirm("Delete subscriber permanently?")) return;
    await api.delete(`/subscribers/${id}`);
    toast.success("Deleted");
    load();
  };

  return (
    <AdminLayout title="Subscribers" subtitle="Database" actions={
      <button data-testid="add-subscriber-btn" onClick={() => setShowAdd(true)} className="btn-primary flex items-center gap-2 text-sm">
        <Plus className="w-4 h-4" /> Add Subscriber
      </button>
    }>
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 mb-4" data-testid="filters">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#6B7280]" />
          <input data-testid="search-input" value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Search by name, email, mobile…"
            className="w-full bg-transparent border border-[#27272A] focus:border-[#F58220] outline-none pl-10 pr-3 py-2.5 text-sm rounded-sm" />
        </div>
        <div className="flex items-center gap-1 flex-wrap">
          {STATUSES.map((s) => (
            <button key={s} data-testid={`filter-${s}`} onClick={() => setStatus(s)}
              className={`px-3 py-1.5 text-[11px] font-mono-plex uppercase tracking-[0.18em] rounded-sm border ${
                status === s ? "bg-[#F58220] text-black border-[#F58220]" : "border-[#27272A] text-[#9CA3AF] hover:border-[#F58220]"
              }`}>{s}</button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="panel">
        <div className="overflow-x-auto">
          <table className="dense w-full" data-testid="subscribers-table">
            <thead>
              <tr>
                <th>Name</th><th>Contact</th><th>Status</th><th>Plan / ₹</th>
                <th>Next Billing</th><th>Grace End</th><th>TG</th><th className="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {list.length === 0 ? (
                <tr><td colSpan="8" className="text-center text-[#6B7280] py-10">No subscribers match.</td></tr>
              ) : list.map((s) => (
                <tr key={s.id} data-testid={`row-${s.id}`}>
                  <td>
                    <div className="font-medium">{s.name}</div>
                    <div className="text-[11px] text-[#6B7280] font-mono-plex">{s.id.slice(0, 8)}…</div>
                  </td>
                  <td className="mono">
                    <div>{s.email}</div>
                    <div className="text-[#9CA3AF]">{s.mobile}</div>
                  </td>
                  <td><StatusPill status={s.subscription_status} /></td>
                  <td className="mono">₹{Number(s.amount || 0).toLocaleString("en-IN")}</td>
                  <td className="mono text-[#9CA3AF]">{s.next_billing_date?.slice(0, 10) || "—"}</td>
                  <td className="mono text-[#F58220]">{s.grace_period_end_date?.slice(0, 10) || "—"}</td>
                  <td className="mono">
                    {s.telegram_joined ? <span className="text-[#00A25B]">joined</span> : <span className="text-[#6B7280]">pending</span>}
                  </td>
                  <td>
                    <div className="flex items-center gap-1 justify-end">
                      <button data-testid={`view-${s.id}`} onClick={() => setSelected(s)} className="btn-ghost text-[11px] px-2 py-1">View</button>
                      <button data-testid={`react-${s.id}`} onClick={() => reactivate(s.id)} title="Reactivate" className="p-1.5 hover:text-[#00A25B]"><RotateCw className="w-3.5 h-3.5" /></button>
                      <button data-testid={`comp-${s.id}`} onClick={() => grantComp(s.id)} title="Grant comp" className="p-1.5 hover:text-[#3B82F6]"><Gift className="w-3.5 h-3.5" /></button>
                      <button data-testid={`remove-${s.id}`} onClick={() => removeFromChannel(s.id)} title="Remove from channel" className="p-1.5 hover:text-[#F58220]"><Ban className="w-3.5 h-3.5" /></button>
                      <button data-testid={`del-${s.id}`} onClick={() => del(s.id)} title="Delete" className="p-1.5 hover:text-[#E92C2C]"><Trash2 className="w-3.5 h-3.5" /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Add modal */}
      {showAdd && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4" data-testid="add-modal">
          <div className="panel w-full max-w-md p-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <div className="kicker">Manual</div>
                <div className="font-chivo font-bold text-xl">Add Subscriber</div>
              </div>
              <button onClick={() => setShowAdd(false)} className="text-[#9CA3AF] hover:text-white"><X className="w-4 h-4" /></button>
            </div>
            <form onSubmit={add} className="space-y-3">
              {[
                { k: "name", label: "Name", type: "text" },
                { k: "email", label: "Email", type: "email" },
                { k: "mobile", label: "Mobile", type: "text" },
                { k: "amount", label: "Amount (₹)", type: "number" },
              ].map((f) => (
                <div key={f.k}>
                  <label className="kicker block mb-1">{f.label}</label>
                  <input data-testid={`add-${f.k}`} required type={f.type} value={addForm[f.k]}
                    onChange={(e) => setAddForm({ ...addForm, [f.k]: f.type === "number" ? Number(e.target.value) : e.target.value })}
                    className="w-full bg-transparent border border-[#27272A] focus:border-[#F58220] outline-none px-3 py-2 text-sm rounded-sm" />
                </div>
              ))}
              <div>
                <label className="kicker block mb-1">Notes</label>
                <textarea data-testid="add-notes" value={addForm.notes} rows="2"
                  onChange={(e) => setAddForm({ ...addForm, notes: e.target.value })}
                  className="w-full bg-transparent border border-[#27272A] focus:border-[#F58220] outline-none px-3 py-2 text-sm rounded-sm" />
              </div>
              <button data-testid="add-submit" type="submit" className="btn-primary w-full mt-3">Add & generate invite</button>
            </form>
          </div>
        </div>
      )}

      {/* Detail drawer */}
      {selected && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4" data-testid="detail-modal" onClick={() => setSelected(null)}>
          <div className="panel w-full max-w-lg p-6" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between mb-4">
              <div>
                <div className="kicker">Subscriber</div>
                <div className="font-chivo font-bold text-xl">{selected.name}</div>
                <div className="text-xs text-[#9CA3AF] font-mono-plex">{selected.email} · {selected.mobile}</div>
              </div>
              <button onClick={() => setSelected(null)}><X className="w-4 h-4 text-[#9CA3AF]" /></button>
            </div>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <Field label="Status"><StatusPill status={selected.subscription_status} /></Field>
              <Field label="Plan">{selected.plan_name}</Field>
              <Field label="Amount" mono>₹{selected.amount}</Field>
              <Field label="Start" mono>{selected.start_date?.slice(0, 10) || "—"}</Field>
              <Field label="Next Billing" mono>{selected.next_billing_date?.slice(0, 10) || "—"}</Field>
              <Field label="Grace Ends" mono>{selected.grace_period_end_date?.slice(0, 10) || "—"}</Field>
              <Field label="Razorpay Sub" mono>{selected.razorpay_subscription_id || "—"}</Field>
              <Field label="Telegram User ID" mono>{selected.telegram_user_id || "—"}</Field>
              <Field label="Removed from channel">{selected.removed_from_channel ? "Yes" : "No"}</Field>
              <Field label="Last payment">{selected.last_payment_status || "—"}</Field>
            </div>
            {selected.telegram_invite_link && (
              <div className="mt-4 panel p-3 bg-[#0A0A0A]">
                <div className="kicker mb-1">Telegram Invite Link</div>
                <a href={selected.telegram_invite_link} target="_blank" rel="noreferrer" className="text-[#F58220] font-mono-plex text-xs break-all hover:underline">{selected.telegram_invite_link}</a>
              </div>
            )}
            {selected.notes && (
              <div className="mt-4 panel p-3 bg-[#0A0A0A]">
                <div className="kicker mb-1">Notes</div>
                <div className="text-xs whitespace-pre-wrap">{selected.notes}</div>
              </div>
            )}
          </div>
        </div>
      )}
    </AdminLayout>
  );
}

function Field({ label, children, mono }) {
  return (
    <div>
      <div className="kicker mb-1">{label}</div>
      <div className={mono ? "font-mono-plex text-sm" : "text-sm"}>{children}</div>
    </div>
  );
}
