import React, { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import { toast } from "sonner";
import { ArrowRight, ShieldCheck, TerminalSquare, Check, Clock, Zap } from "lucide-react";

export default function Subscribe() {
  const [params] = useSearchParams();
  const [plan, setPlan] = useState(null);
  const [form, setForm] = useState({
    name: params.get("name") || "",
    mobile: params.get("mobile") || "",
    email: params.get("email") || "",
  });
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(null);

  useEffect(() => { api.get("/public/plan").then((r) => setPlan(r.data)); }, []);

  const subscribe = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const { data } = await api.post("/public/checkout", form);
      if (data.is_placeholder) {
        setSuccess({ message: "Subscription registered (demo mode).", sub: data.subscription_id, invite: null });
      } else if (window.Razorpay) {
        const options = {
          key: data.razorpay_key_id,
          subscription_id: data.subscription_id,
          name: "FnO Tattva",
          description: data.plan_name,
          prefill: { name: data.customer_name, email: data.customer_email, contact: data.customer_mobile },
          theme: { color: "#F58220" },
          handler: (rp) => setSuccess({
            message: "Payment initiated. You'll receive a Telegram invite link shortly on the email you signed up with.",
            sub: data.subscription_id,
            payment_id: rp?.razorpay_payment_id,
          }),
          modal: {
            ondismiss: () => setLoading(false),
          },
        };
        new window.Razorpay(options).open();
      } else {
        toast.error("Razorpay SDK not loaded. Refresh and try again.");
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to create subscription");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0A0A0A] flex items-center justify-center px-4 py-10">
      <div className="w-full max-w-md">
        {/* brand strip */}
        <div className="flex items-center gap-2 mb-6 justify-center">
          <TerminalSquare className="w-5 h-5 text-[#F58220]" strokeWidth={1.5} />
          <span className="font-chivo font-black text-lg tracking-tight">FnO TATTVA</span>
        </div>

        <div className="panel p-8">
          {/* Price header */}
          <div className="flex items-baseline justify-between border-b border-[#27272A] pb-5 mb-5">
            <div>
              <div className="kicker">Monthly Subscription</div>
              <div className="mt-1 font-chivo font-black text-4xl">
                ₹<span className="font-mono-plex tabular-nums">{plan ? plan.amount_inr : "—"}</span>
                <span className="text-sm font-mono-plex text-[#9CA3AF] ml-2">/mo</span>
              </div>
              <div className="kicker mt-1 text-[#F58220]">Auto-renews via UPI</div>
            </div>
            <div className="text-right">
              <div className="kicker">Delivery</div>
              <div className="text-sm font-mono-plex mt-1">07:00 IST</div>
              <div className="text-[10px] text-[#9CA3AF] font-mono-plex uppercase tracking-[0.2em] mt-1">Telegram</div>
            </div>
          </div>

          {success ? (
            <div className="text-center py-4" data-testid="subscribe-success">
              <div className="w-14 h-14 mx-auto rounded-full bg-[#00A25B]/10 border border-[#00A25B]/40 flex items-center justify-center mb-4">
                <ShieldCheck className="w-7 h-7 text-[#00A25B]" strokeWidth={1.8} />
              </div>
              <div className="font-chivo font-bold text-xl">You're in.</div>
              <div className="text-sm text-[#9CA3AF] mt-2 leading-relaxed">{success.message}</div>
              <div className="kicker mt-4">Ref · {success.sub}</div>
              {success.payment_id && <div className="kicker mt-1 text-[#F58220]">Payment · {success.payment_id}</div>}
              <button
                onClick={() => { setSuccess(null); setForm({ name: "", mobile: "", email: "" }); }}
                className="btn-ghost text-xs mt-6"
                data-testid="subscribe-another"
              >Subscribe another account</button>
            </div>
          ) : (
            <form onSubmit={subscribe} className="space-y-3" data-testid="subscribe-form">
              <div>
                <label className="kicker block mb-1.5">Full Name</label>
                <input data-testid="checkout-name" required value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="w-full bg-transparent border border-[#27272A] focus:border-[#F58220] outline-none px-3 py-2.5 text-sm rounded-sm"
                  placeholder="As on PAN"
                />
              </div>
              <div>
                <label className="kicker block mb-1.5">Mobile</label>
                <input data-testid="checkout-mobile" required value={form.mobile} pattern="[0-9]{10}"
                  onChange={(e) => setForm({ ...form, mobile: e.target.value })}
                  className="w-full bg-transparent border border-[#27272A] focus:border-[#F58220] outline-none px-3 py-2.5 text-sm rounded-sm font-mono-plex"
                  placeholder="10-digit mobile"
                />
              </div>
              <div>
                <label className="kicker block mb-1.5">Email</label>
                <input data-testid="checkout-email" type="email" required value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  className="w-full bg-transparent border border-[#27272A] focus:border-[#F58220] outline-none px-3 py-2.5 text-sm rounded-sm"
                  placeholder="you@domain.com"
                />
              </div>
              <button data-testid="checkout-submit" disabled={loading} type="submit" className="btn-primary w-full flex items-center gap-2 justify-center mt-4">
                {loading ? "Opening payment…" : "Pay & join channel"}
                <ArrowRight className="w-4 h-4" />
              </button>
              <p className="text-[11px] text-[#6B7280] mt-2 font-mono-plex leading-relaxed text-center">
                Auto-recurring via UPI AutoPay · Cancel anytime · 2-day grace on failed payment
              </p>
            </form>
          )}
        </div>

        {/* micro trust bar */}
        <div className="grid grid-cols-3 gap-2 mt-4">
          {[
            { icon: Clock, label: "Daily 07:00 IST" },
            { icon: Zap, label: "5-min actionable" },
            { icon: Check, label: "Cancel anytime" },
          ].map((f, i) => (
            <div key={i} className="panel px-3 py-2 flex items-center gap-2">
              <f.icon className="w-3.5 h-3.5 text-[#F58220]" strokeWidth={1.5} />
              <span className="text-[11px] text-[#9CA3AF]">{f.label}</span>
            </div>
          ))}
        </div>

        <div className="text-center mt-6 text-[10px] text-[#6B7280] font-mono-plex uppercase tracking-[0.2em]">
          Secured by Razorpay · Not investment advice
        </div>
      </div>
    </div>
  );
}
