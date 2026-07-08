import React, { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import { toast } from "sonner";
import { ArrowRight, ShieldCheck, TerminalSquare, Check, Clock, Zap, Send, Loader2 } from "lucide-react";

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
  const [inviteState, setInviteState] = useState({ status: "idle", invite: null, msg: "" });

  useEffect(() => { api.get("/public/plan").then((r) => setPlan(r.data)); }, []);

  // Poll the backend after payment success until webhook lands (or 25 sec timeout)
  const pollForInvite = async (subscriptionId) => {
    setInviteState({ status: "polling", invite: null, msg: "Confirming payment with Razorpay…" });
    const maxTries = 25;
    for (let i = 0; i < maxTries; i++) {
      try {
        const { data } = await api.get(`/public/subscription-status/${subscriptionId}`);
        if (data.invite_link) {
          setInviteState({ status: "ready", invite: data.invite_link, msg: "" });
          return;
        }
      } catch (_) { /* keep polling */ }
      await new Promise((r) => setTimeout(r, 1200));
    }
    setInviteState({
      status: "delayed",
      invite: null,
      msg: "Payment confirmed. Your invite link is being generated — please wait a moment and refresh, or contact support if it doesn't appear in 1 minute.",
    });
  };

  const subscribe = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const { data } = await api.post("/public/checkout", form);
      if (data.is_placeholder) {
        setSuccess({ sub: data.subscription_id, payment_id: null });
        pollForInvite(data.subscription_id);
      } else if (window.Razorpay) {
        const options = {
          key: data.razorpay_key_id,
          subscription_id: data.subscription_id,
          name: "FnO Tattva",
          description: data.plan_name,
          prefill: { name: data.customer_name, email: data.customer_email, contact: data.customer_mobile },
          theme: { color: "#F58220" },
          handler: (rp) => {
            setSuccess({ sub: data.subscription_id, payment_id: rp?.razorpay_payment_id });
            pollForInvite(data.subscription_id);
          },
          modal: { ondismiss: () => setLoading(false) },
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
          <div className="border-b border-[#27272A] pb-5 mb-5">
            <div className="flex items-center gap-2 mb-2">
              <div className="kicker">Monthly Subscription</div>
              <span className="text-[10px] font-mono-plex tracking-[0.18em] uppercase px-2 py-0.5 bg-[#F58220] text-black rounded-sm font-bold">70% OFF · Launch</span>
            </div>
            <div className="flex items-baseline justify-between">
              <div className="flex items-baseline gap-3">
                <span className="font-chivo font-black text-4xl">
                  ₹<span className="font-mono-plex tabular-nums">{plan ? plan.amount_inr : "—"}</span>
                </span>
                <span className="text-lg font-mono-plex text-[#6B7280] line-through decoration-[#E92C2C] decoration-2 tabular-nums">₹499</span>
                <span className="text-sm font-mono-plex text-[#9CA3AF]">/mo</span>
              </div>
              <div className="text-right">
                <div className="kicker">Delivery</div>
                <div className="text-sm font-mono-plex mt-1">07:00 IST</div>
              </div>
            </div>
            <div className="mt-2 text-sm font-mono-plex text-[#00A25B]">
              Just <span className="font-bold text-white">₹5 / day</span> · less than a chai ☕
            </div>
            <div className="kicker mt-2 text-[#F58220]">Auto-renews via UPI · Cancel anytime</div>
          </div>

          {success ? (
            <div className="text-center py-4" data-testid="subscribe-success">
              {inviteState.status === "ready" ? (
                <>
                  <div className="w-14 h-14 mx-auto rounded-full bg-[#00A25B]/10 border border-[#00A25B]/40 flex items-center justify-center mb-4">
                    <ShieldCheck className="w-7 h-7 text-[#00A25B]" strokeWidth={1.8} />
                  </div>
                  <div className="font-chivo font-bold text-2xl">Payment successful.</div>
                  <div className="text-sm text-[#9CA3AF] mt-2 leading-relaxed">
                    Your subscription is <span className="text-[#00A25B] font-semibold">ACTIVE</span>. Tap the button below to join the private Telegram channel.
                  </div>
                  <a
                    href={inviteState.invite}
                    target="_blank"
                    rel="noopener noreferrer"
                    data-testid="telegram-join-btn"
                    className="btn-primary w-full mt-6 flex items-center gap-2 justify-center text-base py-3"
                  >
                    <Send className="w-5 h-5" strokeWidth={2} />
                    Join Telegram Channel
                  </a>
                  <p className="text-[11px] text-[#6B7280] mt-3 font-mono-plex leading-relaxed">
                    This link is <span className="text-[#F58220]">single-use</span> — join now on the device you'll use for Telegram.
                  </p>
                  <div className="mt-6 border-t border-[#27272A] pt-4 space-y-1">
                    <div className="kicker">Ref · <span className="text-[#F3F4F6]">{success.sub}</span></div>
                    {success.payment_id && <div className="kicker text-[#F58220]">Payment · {success.payment_id}</div>}
                  </div>
                </>
              ) : inviteState.status === "polling" ? (
                <>
                  <div className="w-14 h-14 mx-auto rounded-full bg-[#F58220]/10 border border-[#F58220]/40 flex items-center justify-center mb-4">
                    <Loader2 className="w-7 h-7 text-[#F58220] animate-spin" strokeWidth={1.8} />
                  </div>
                  <div className="font-chivo font-bold text-xl">Confirming your payment…</div>
                  <div className="text-sm text-[#9CA3AF] mt-2 leading-relaxed">
                    Verifying with Razorpay and generating your channel invite. This usually takes 3-5 seconds.
                  </div>
                  <div className="kicker mt-4">Ref · {success.sub}</div>
                </>
              ) : (
                <>
                  <div className="w-14 h-14 mx-auto rounded-full bg-[#F58220]/10 border border-[#F58220]/40 flex items-center justify-center mb-4">
                    <ShieldCheck className="w-7 h-7 text-[#F58220]" strokeWidth={1.8} />
                  </div>
                  <div className="font-chivo font-bold text-xl">Payment received.</div>
                  <div className="text-sm text-[#9CA3AF] mt-2 leading-relaxed">{inviteState.msg}</div>
                  <div className="kicker mt-4">Ref · {success.sub}</div>
                  <button
                    onClick={() => pollForInvite(success.sub)}
                    className="btn-ghost text-xs mt-4"
                    data-testid="retry-invite"
                  >Check again</button>
                </>
              )}
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

        <div className="text-center mt-6 space-y-1.5">
          <div className="text-[10px] text-[#6B7280] font-mono-plex uppercase tracking-[0.2em]">
            Secured by Razorpay · Not investment advice
          </div>
          <div className="text-[10px] text-[#6B7280] font-mono-plex uppercase tracking-[0.15em]">
            SEBI Reg. No. INH000016047 · BSE Enlistment No. 6149
          </div>
        </div>
      </div>
    </div>
  );
}
