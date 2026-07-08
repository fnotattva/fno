import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { toast } from "sonner";
import { ArrowRight, ShieldCheck, Zap, Clock, TerminalSquare, ChevronRight } from "lucide-react";

export default function Landing() {
  const [plan, setPlan] = useState(null);
  const [form, setForm] = useState({ name: "", mobile: "", email: "" });
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(null);

  useEffect(() => { api.get("/public/plan").then((r) => setPlan(r.data)); }, []);

  const subscribe = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const { data } = await api.post("/public/checkout", form);
      if (data.is_placeholder) {
        setSuccess({
          message: "Subscription registered in demo mode.",
          sub: data.subscription_id,
        });
        toast.info("Razorpay is in placeholder mode. In production, checkout modal opens here.");
      } else if (window.Razorpay) {
        const options = {
          key: data.razorpay_key_id,
          subscription_id: data.subscription_id,
          name: "FnO Tattva",
          description: data.plan_name,
          prefill: { name: data.customer_name, email: data.customer_email, contact: data.customer_mobile },
          theme: { color: "#F58220" },
          handler: () => setSuccess({ message: "Payment initiated. You'll receive a Telegram invite shortly.", sub: data.subscription_id }),
        };
        new window.Razorpay(options).open();
      } else {
        toast.error("Razorpay SDK not loaded");
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to create subscription");
    } finally {
      setLoading(false);
    }
  };

  const price = plan?.amount_inr;
  const planLoaded = plan != null;

  return (
    <div className="min-h-screen bg-[#0A0A0A] text-[#F3F4F6]">
      {/* Ticker */}
      <div className="border-b border-[#27272A] overflow-hidden py-2">
        <div className="ticker font-mono-plex text-[11px] uppercase tracking-[0.2em] text-[#9CA3AF]">
          {[..."NIFTY  BANKNIFTY  FINNIFTY  SENSEX  MIDCPNIFTY  NIFTYIT  NIFTYBANK  NIFTYFMCG  NIFTYAUTO".split("  ")].map((t, i) => (
            <span key={i}>◆ {t} · Morning Brief · 7:00 IST</span>
          ))}
          {[..."NIFTY  BANKNIFTY  FINNIFTY  SENSEX  MIDCPNIFTY".split("  ")].map((t, i) => (
            <span key={`b${i}`}>◆ {t} · Morning Brief · 7:00 IST</span>
          ))}
        </div>
      </div>

      {/* Nav */}
      <nav className="max-w-[1400px] mx-auto flex items-center justify-between px-8 py-5">
        <div className="flex items-center gap-2">
          <TerminalSquare className="w-5 h-5 text-[#F58220]" strokeWidth={1.5} />
          <span className="font-chivo font-black text-lg tracking-tight">FnO TATTVA</span>
        </div>
        <div className="flex items-center gap-4">
          <Link to="/admin/login" className="text-xs text-[#9CA3AF] hover:text-[#F58220]" data-testid="nav-admin-login">Admin login →</Link>
        </div>
      </nav>

      {/* Hero: asymmetric split */}
      <div className="max-w-[1400px] mx-auto grid grid-cols-1 lg:grid-cols-12 gap-8 px-8 py-10">
        {/* Left: pitch */}
        <div className="lg:col-span-7 relative overflow-hidden panel min-h-[560px]">
          <div className="absolute inset-0 chart-bg opacity-30" />
          <div className="absolute inset-0 bg-gradient-to-br from-black/80 via-black/70 to-black/95" />
          <div className="relative p-10 lg:p-14 h-full flex flex-col justify-between">
            <div>
              <div className="kicker text-[#F58220]">◆ Daily · 7:00 AM IST · Private Telegram</div>
              <h1 className="font-chivo font-black text-4xl lg:text-6xl mt-4 leading-[1.05] tracking-tight">
                Trade the open<br />
                <span className="text-[#F58220]">before it happens.</span>
              </h1>
              <p className="mt-6 text-[#9CA3AF] max-w-lg text-base lg:text-lg">
                A precision morning brief for Indian F&amp;O traders. Delivered to a private,
                paid Telegram channel — every trading day, before the bell.
              </p>
            </div>

            <div className="grid grid-cols-3 gap-4 mt-10 border-t border-[#27272A]/60 pt-6">
              {[
                { icon: Clock, k: "07:00 IST", v: "Delivery" },
                { icon: Zap, k: "5 min read", v: "Actionable" },
                { icon: ShieldCheck, k: "Auto-managed", v: "Access" },
              ].map((f, i) => (
                <div key={i}>
                  <f.icon className="w-4 h-4 text-[#F58220] mb-2" strokeWidth={1.5} />
                  <div className="font-mono-plex text-sm text-white">{f.k}</div>
                  <div className="kicker mt-0.5">{f.v}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right: subscribe card */}
        <div className="lg:col-span-5">
          <div className="panel p-8">
            <div className="flex items-baseline justify-between">
              <div>
                <div className="kicker">Monthly Plan</div>
                <div className="mt-1 font-chivo font-black text-4xl">
                  ₹<span className="font-mono-plex tabular-nums">{planLoaded ? price : "—"}</span>
                  <span className="text-sm font-mono-plex text-[#9CA3AF] ml-2">/mo</span>
                </div>
              </div>
              <div className="text-right">
                <div className="kicker">UPI · Cards</div>
                <div className="text-xs text-[#9CA3AF] mt-1 font-mono-plex">via Razorpay</div>
              </div>
            </div>

            <div className="border-t border-[#27272A] my-6" />

            {success ? (
              <div className="text-center py-6" data-testid="subscribe-success">
                <div className="w-12 h-12 mx-auto rounded-full bg-[#00A25B]/10 border border-[#00A25B]/40 flex items-center justify-center mb-3">
                  <ShieldCheck className="w-6 h-6 text-[#00A25B]" strokeWidth={1.8} />
                </div>
                <div className="font-chivo font-bold text-lg">{success.message}</div>
                <div className="kicker mt-2">Ref · {success.sub}</div>
              </div>
            ) : (
              <form onSubmit={subscribe} className="space-y-4" data-testid="subscribe-form">
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
                <button data-testid="checkout-submit" disabled={loading} type="submit" className="btn-primary w-full flex items-center gap-2 justify-center">
                  {loading ? "Preparing…" : "Subscribe & join channel"}
                  <ArrowRight className="w-4 h-4" />
                </button>
                <p className="text-[11px] text-[#6B7280] mt-2 font-mono-plex leading-relaxed">
                  Auto-recurring via UPI AutoPay. Cancel anytime. Access is revoked automatically after a 2-day grace period on failed payment.
                </p>
              </form>
            )}
          </div>

          {/* Included */}
          <div className="mt-6 panel p-6">
            <div className="kicker mb-3">Included</div>
            <ul className="space-y-2 text-sm">
              {[
                "Daily FnO Tattva Morning Brief (PDF)",
                "Pre-market view on Nifty & BankNifty",
                "OI shifts, key levels, put-call ratio",
                "Sector rotation & event calendar",
                "Private Telegram channel access",
              ].map((x, i) => (
                <li key={i} className="flex items-start gap-2">
                  <ChevronRight className="w-4 h-4 text-[#F58220] mt-0.5" strokeWidth={2} />
                  <span className="text-[#F3F4F6]">{x}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="border-t border-[#27272A] mt-10">
        <div className="max-w-[1400px] mx-auto px-8 py-6 flex flex-wrap items-center justify-between gap-3 text-xs text-[#6B7280]">
          <div>© 2026 FnO Tattva · A market brief service</div>
          <div className="font-mono-plex tracking-[0.2em] uppercase">not investment advice · educational only</div>
        </div>
      </footer>
    </div>
  );
}
