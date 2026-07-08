import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { toast } from "sonner";
import { ArrowRight, ShieldCheck, Zap, Clock, TerminalSquare, ChevronRight, Send, Loader2 } from "lucide-react";

export default function Landing() {
  const [plan, setPlan] = useState(null);
  const [form, setForm] = useState({ name: "", mobile: "", email: "" });
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(null);
  const [inviteState, setInviteState] = useState({ status: "idle", invite: null, msg: "" });

  useEffect(() => { api.get("/public/plan").then((r) => setPlan(r.data)); }, []);

  const pollForInvite = async (subscriptionId) => {
    setInviteState({ status: "polling", invite: null, msg: "Confirming payment with Razorpay…" });
    for (let i = 0; i < 25; i++) {
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
      msg: "Payment confirmed. Your invite link is being generated — please wait a moment.",
    });
  };

  const subscribe = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const { data } = await api.post("/public/checkout", form);
      if (data.is_placeholder) {
        setSuccess({ sub: data.subscription_id });
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
                Your morning<br />
                <span className="text-[#F58220]">market edge.</span>
              </h1>
              <p className="mt-6 text-[#9CA3AF] max-w-lg text-base lg:text-lg">
                A daily market brief crafted by a <span className="text-white font-semibold">Chartered Accountant &amp; SEBI Registered Research Analyst</span>.
                Shown in a very simple format so anyone — from a first-time investor to a seasoned F&amp;O trader — can act on it before the bell.
              </p>
              <div className="mt-4 inline-flex items-center gap-2 px-3 py-1.5 border border-[#27272A] rounded-sm bg-black/40">
                <ShieldCheck className="w-3.5 h-3.5 text-[#00A25B]" strokeWidth={1.8} />
                <span className="kicker text-[#F3F4F6]">Authored by a Chartered Accountant · SEBI Registered RA · Algo Trader</span>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-4 mt-10 border-t border-[#27272A]/60 pt-6">
              {[
                { icon: Clock, k: "07:00 IST", v: "Delivery" },
                { icon: Zap, k: "Simple Format", v: "Actionable" },
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
                <div className="flex items-center gap-2">
                  <div className="kicker">Monthly Plan</div>
                  <span className="text-[10px] font-mono-plex tracking-[0.18em] uppercase px-2 py-0.5 bg-[#F58220] text-black rounded-sm font-bold">70% OFF · Launch</span>
                </div>
                <div className="mt-2 flex items-baseline gap-3">
                  <span className="font-chivo font-black text-4xl">
                    ₹<span className="font-mono-plex tabular-nums">{planLoaded ? price : "—"}</span>
                  </span>
                  <span className="text-lg font-mono-plex text-[#6B7280] line-through decoration-[#E92C2C] decoration-2 tabular-nums">₹499</span>
                  <span className="text-sm font-mono-plex text-[#9CA3AF]">/mo</span>
                </div>
                <div className="mt-1.5 text-sm font-mono-plex text-[#00A25B]">
                  Just <span className="font-bold text-white">₹5 / day</span> · less than a chai ☕
                </div>
              </div>
              <div className="text-right">
                <div className="kicker">UPI · Cards</div>
                <div className="text-xs text-[#9CA3AF] mt-1 font-mono-plex">via Razorpay</div>
              </div>
            </div>

            <div className="border-t border-[#27272A] my-6" />

            {success ? (
              <div className="text-center py-4" data-testid="subscribe-success">
                {inviteState.status === "ready" ? (
                  <>
                    <div className="w-14 h-14 mx-auto rounded-full bg-[#00A25B]/10 border border-[#00A25B]/40 flex items-center justify-center mb-4">
                      <ShieldCheck className="w-7 h-7 text-[#00A25B]" strokeWidth={1.8} />
                    </div>
                    <div className="font-chivo font-bold text-2xl">Payment successful.</div>
                    <div className="text-sm text-[#9CA3AF] mt-2 leading-relaxed">
                      You're <span className="text-[#00A25B] font-semibold">ACTIVE</span>. Tap below to join the private Telegram channel.
                    </div>
                    <a href={inviteState.invite} target="_blank" rel="noopener noreferrer"
                      data-testid="telegram-join-btn"
                      className="btn-primary w-full mt-6 flex items-center gap-2 justify-center text-base py-3">
                      <Send className="w-5 h-5" strokeWidth={2} />
                      Join Telegram Channel
                    </a>
                    <p className="text-[11px] text-[#6B7280] mt-3 font-mono-plex leading-relaxed">
                      Single-use link · join now on the device you'll use for Telegram.
                    </p>
                    <div className="kicker mt-6">Ref · {success.sub}</div>
                  </>
                ) : inviteState.status === "polling" ? (
                  <>
                    <div className="w-14 h-14 mx-auto rounded-full bg-[#F58220]/10 border border-[#F58220]/40 flex items-center justify-center mb-4">
                      <Loader2 className="w-7 h-7 text-[#F58220] animate-spin" strokeWidth={1.8} />
                    </div>
                    <div className="font-chivo font-bold text-xl">Confirming payment…</div>
                    <div className="text-sm text-[#9CA3AF] mt-2">Generating your channel invite. Usually takes 3-5 sec.</div>
                    <div className="kicker mt-4">Ref · {success.sub}</div>
                  </>
                ) : (
                  <>
                    <div className="w-14 h-14 mx-auto rounded-full bg-[#F58220]/10 border border-[#F58220]/40 flex items-center justify-center mb-4">
                      <ShieldCheck className="w-7 h-7 text-[#F58220]" strokeWidth={1.8} />
                    </div>
                    <div className="font-chivo font-bold text-xl">Payment received.</div>
                    <div className="text-sm text-[#9CA3AF] mt-2">{inviteState.msg}</div>
                    <div className="kicker mt-4">Ref · {success.sub}</div>
                    <button onClick={() => pollForInvite(success.sub)} className="btn-ghost text-xs mt-4">Check again</button>
                  </>
                )}
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
            <div className="kicker mb-3">What you get every morning</div>
            <ul className="space-y-2 text-sm">
              {[
                "Daily FnO Tattva Morning Brief (PDF)",
                "Pre-market view on Nifty & BankNifty",
                "Institutional activity (FII / DII flows)",
                "OI shifts, key levels & put-call ratio",
                "Breakout stocks to watch",
                "IPO watch",
                "Upcoming events calendar",
                "Sector rotation insights",
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
        <div className="max-w-[1400px] mx-auto px-8 py-6 space-y-3 text-xs text-[#6B7280]">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>© 2026 FnO Tattva · A market brief service</div>
            <div className="font-mono-plex tracking-[0.2em] uppercase">not investment advice · educational only</div>
          </div>
          <div className="border-t border-[#27272A] pt-3 flex flex-wrap gap-x-6 gap-y-1 font-mono-plex text-[10.5px] uppercase tracking-[0.15em]">
            <span>SEBI Registration No. <span className="text-[#F3F4F6]">INH000016047</span></span>
            <span>BSE Enlistment No. <span className="text-[#F3F4F6]">6149</span></span>
          </div>
          <p className="text-[11px] leading-relaxed text-[#6B7280] max-w-4xl">
            Disclaimer: Investment in securities market are subject to market risks. Read all the related documents carefully
            before investing. Registration granted by SEBI, enlistment as an IA / RA, and certification from NISM in no way
            guarantee performance of the intermediary or provide any assurance of returns to investors.
          </p>
        </div>
      </footer>
    </div>
  );
}
