import React, { useEffect, useState } from "react";
import AdminLayout from "@/components/AdminLayout";
import api from "@/lib/api";
import { toast } from "sonner";
import { Bell, Send, ChevronRight } from "lucide-react";

export default function Notifications() {
  const [templates, setTemplates] = useState([]);
  const [subs, setSubs] = useState([]);
  const [selected, setSelected] = useState(null);
  const [subId, setSubId] = useState("");

  useEffect(() => {
    api.get("/notifications/templates").then((r) => setTemplates(r.data));
    api.get("/subscribers").then((r) => setSubs(r.data));
  }, []);

  const send = async () => {
    if (!selected || !subId) return toast.error("Pick template & subscriber");
    try {
      const { data } = await api.post("/notifications/send", { subscriber_id: subId, template_key: selected.key });
      if (data.ok) toast.success("Sent via Telegram DM");
      else toast.info("Rendered — subscriber has not DM'd the bot yet");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed");
    }
  };

  return (
    <AdminLayout title="Notification Templates" subtitle="Message center">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1">
          <div className="panel">
            <div className="p-4 border-b border-[#27272A]">
              <div className="kicker">Templates</div>
              <div className="font-chivo font-bold text-lg">Available</div>
            </div>
            <div className="divide-y divide-[#27272A]">
              {templates.map((t) => (
                <button key={t.key} data-testid={`tpl-${t.key}`} onClick={() => setSelected(t)}
                  className={`w-full text-left p-4 hover:bg-[#F58220]/[0.06] flex items-center gap-3 ${selected?.key === t.key ? "bg-[#F58220]/[0.08] border-l-2 border-[#F58220]" : "border-l-2 border-transparent"}`}>
                  <Bell className="w-4 h-4 text-[#F58220]" strokeWidth={1.5} />
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-sm">{t.title}</div>
                    <div className="text-[11px] text-[#6B7280] font-mono-plex uppercase tracking-[0.15em]">{t.key}</div>
                  </div>
                  <ChevronRight className="w-4 h-4 text-[#6B7280]" />
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="lg:col-span-2">
          <div className="panel p-6">
            {!selected ? (
              <div className="text-center text-[#6B7280] py-16">Select a template on the left to preview.</div>
            ) : (
              <>
                <div className="kicker">Preview · {selected.key}</div>
                <h2 className="font-chivo font-bold text-2xl mt-1">{selected.title}</h2>
                <div className="mt-4 border border-[#27272A] p-4 rounded-sm bg-[#0A0A0A]">
                  <div className="text-sm whitespace-pre-wrap" dangerouslySetInnerHTML={{ __html: selected.body }} />
                </div>

                <div className="mt-6 border-t border-[#27272A] pt-6">
                  <div className="kicker mb-2">Send test / manual</div>
                  <div className="flex gap-2">
                    <select data-testid="tpl-recipient" value={subId} onChange={(e) => setSubId(e.target.value)}
                      className="flex-1 bg-transparent border border-[#27272A] focus:border-[#F58220] outline-none px-3 py-2 text-sm rounded-sm">
                      <option value="">Choose subscriber…</option>
                      {subs.map((s) => (
                        <option key={s.id} value={s.id}>{s.name} · {s.email}</option>
                      ))}
                    </select>
                    <button data-testid="tpl-send" onClick={send} className="btn-primary flex items-center gap-2 text-sm">
                      <Send className="w-4 h-4" /> Send
                    </button>
                  </div>
                  <p className="text-[11px] text-[#6B7280] mt-3 font-mono-plex">
                    Note: Telegram DMs deliver only if the subscriber has previously started a chat with the bot.
                  </p>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </AdminLayout>
  );
}
