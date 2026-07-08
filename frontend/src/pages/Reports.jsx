import React, { useEffect, useState } from "react";
import AdminLayout from "@/components/AdminLayout";
import api from "@/lib/api";
import { toast } from "sonner";
import { Upload, Send, Trash2, FileText, CheckCircle2, XCircle, Clock } from "lucide-react";

export default function Reports() {
  const [reports, setReports] = useState([]);
  const [file, setFile] = useState(null);
  const [caption, setCaption] = useState("");
  const [uploading, setUploading] = useState(false);

  const load = async () => {
    const { data } = await api.get("/reports");
    setReports(data);
  };
  useEffect(() => { load(); }, []);

  const upload = async (e) => {
    e.preventDefault();
    if (!file) return toast.error("Choose a PDF first");
    const fd = new FormData();
    fd.append("file", file);
    fd.append("caption", caption);
    setUploading(true);
    try {
      await api.post("/reports/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Report uploaded");
      setFile(null); setCaption("");
      document.getElementById("report-file-input").value = "";
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const send = async (id) => {
    if (!window.confirm("Send this report to the Telegram channel now?")) return;
    const { data } = await api.post(`/reports/${id}/send`);
    if (data.ok) toast.success(data.mocked ? "Sent (mock mode)" : "Sent to channel");
    else toast.error("Send failed — check webhook logs");
    load();
  };

  const del = async (id) => {
    if (!window.confirm("Delete this report?")) return;
    await api.delete(`/reports/${id}`);
    toast.success("Deleted");
    load();
  };

  const statusIcon = (s) => {
    if (s === "SENT") return <CheckCircle2 className="w-4 h-4 text-[#00A25B]" />;
    if (s === "FAILED") return <XCircle className="w-4 h-4 text-[#E92C2C]" />;
    return <Clock className="w-4 h-4 text-[#F58220]" />;
  };

  return (
    <AdminLayout title="Daily Reports" subtitle="Publish to channel">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Upload */}
        <div className="lg:col-span-1">
          <div className="panel p-6 sticky top-24">
            <div className="kicker">Upload</div>
            <div className="font-chivo font-bold text-xl mb-4">New Morning Brief</div>
            <form onSubmit={upload} className="space-y-4">
              <label htmlFor="report-file-input" data-testid="file-drop"
                className="block border-2 border-dashed border-[#27272A] hover:border-[#F58220] transition rounded-sm p-6 text-center cursor-pointer">
                <Upload className="w-6 h-6 mx-auto text-[#F58220] mb-2" strokeWidth={1.5} />
                <div className="text-sm">{file ? file.name : "Click to select PDF"}</div>
                <div className="kicker mt-1">PDF only</div>
                <input id="report-file-input" data-testid="file-input" type="file" accept="application/pdf" className="hidden"
                  onChange={(e) => setFile(e.target.files?.[0] || null)} />
              </label>
              <div>
                <label className="kicker block mb-1.5">Caption (optional)</label>
                <textarea data-testid="caption-input" value={caption} onChange={(e) => setCaption(e.target.value)} rows="3"
                  placeholder="📈 FnO Tattva — 08 Jan 2026"
                  className="w-full bg-transparent border border-[#27272A] focus:border-[#F58220] outline-none px-3 py-2 text-sm rounded-sm" />
              </div>
              <button data-testid="upload-submit" type="submit" disabled={uploading} className="btn-primary w-full flex items-center gap-2 justify-center">
                <Upload className="w-4 h-4" /> {uploading ? "Uploading…" : "Upload Report"}
              </button>
              <p className="text-[11px] text-[#6B7280] font-mono-plex">
                Latest pending report auto-sends at 07:00 IST.
              </p>
            </form>
          </div>
        </div>

        {/* List */}
        <div className="lg:col-span-2">
          <div className="panel">
            <div className="p-4 border-b border-[#27272A]">
              <div className="kicker">History</div>
              <div className="font-chivo font-bold text-lg">Reports Library</div>
            </div>
            {reports.length === 0 ? (
              <div className="text-center text-[#6B7280] py-16">No reports yet — upload today&apos;s brief.</div>
            ) : (
              <div className="divide-y divide-[#27272A]">
                {reports.map((r) => (
                  <div key={r.id} data-testid={`report-${r.id}`} className="p-4 flex items-center gap-4 hover:bg-[#F58220]/[0.03]">
                    <div className="w-10 h-10 border border-[#27272A] flex items-center justify-center rounded-sm">
                      <FileText className="w-5 h-5 text-[#F58220]" strokeWidth={1.5} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-medium truncate">{r.filename}</div>
                      <div className="text-xs text-[#9CA3AF] font-mono-plex flex items-center gap-3">
                        <span>uploaded {r.uploaded_at?.slice(0, 16).replace("T", " ")}</span>
                        {r.sent_at && <span>· sent {r.sent_at.slice(0, 16).replace("T", " ")}</span>}
                      </div>
                      {r.caption && <div className="text-xs text-[#6B7280] mt-1 truncate">{r.caption}</div>}
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="flex items-center gap-1.5 text-xs font-mono-plex uppercase tracking-[0.15em]" style={{ color: r.delivery_status === "SENT" ? "#00A25B" : r.delivery_status === "FAILED" ? "#E92C2C" : "#F58220" }}>
                        {statusIcon(r.delivery_status)} {r.delivery_status}
                      </div>
                      <button data-testid={`send-${r.id}`} onClick={() => send(r.id)} className="btn-primary text-xs flex items-center gap-1.5 py-1.5 px-3">
                        <Send className="w-3.5 h-3.5" /> Send now
                      </button>
                      <button data-testid={`del-report-${r.id}`} onClick={() => del(r.id)} className="p-2 hover:text-[#E92C2C]"><Trash2 className="w-3.5 h-3.5" /></button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </AdminLayout>
  );
}
