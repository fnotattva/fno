import React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { LayoutDashboard, Users, Receipt, FileText, Webhook, Bell, LogOut, TerminalSquare } from "lucide-react";

const links = [
  { to: "/admin", icon: LayoutDashboard, label: "Overview", testId: "nav-overview", end: true },
  { to: "/admin/subscribers", icon: Users, label: "Subscribers", testId: "nav-subscribers" },
  { to: "/admin/payments", icon: Receipt, label: "Payments", testId: "nav-payments" },
  { to: "/admin/reports", icon: FileText, label: "Reports", testId: "nav-reports" },
  { to: "/admin/webhooks", icon: Webhook, label: "Webhook Logs", testId: "nav-webhooks" },
  { to: "/admin/notifications", icon: Bell, label: "Notifications", testId: "nav-notifications" },
];

export default function Sidebar() {
  const nav = useNavigate();
  const email = localStorage.getItem("fnot_email") || "admin";

  const logout = () => {
    localStorage.removeItem("fnot_token");
    localStorage.removeItem("fnot_email");
    nav("/admin/login");
  };

  return (
    <aside className="w-[240px] shrink-0 border-r border-[#27272A] h-screen sticky top-0 bg-[#0A0A0A] flex flex-col" data-testid="admin-sidebar">
      <div className="px-5 py-6 border-b border-[#27272A]">
        <div className="flex items-center gap-2">
          <TerminalSquare className="w-5 h-5 text-[#F58220]" strokeWidth={1.5} />
          <span className="font-chivo font-black text-lg tracking-tight">FnO TATTVA</span>
        </div>
        <div className="kicker mt-1">Access Control</div>
      </div>
      <nav className="flex-1 py-3">
        {links.map((l) => (
          <NavLink
            key={l.to}
            to={l.to}
            end={l.end}
            data-testid={l.testId}
            className={({ isActive }) => `sidebar-link ${isActive ? "active" : ""}`}
          >
            <l.icon className="w-4 h-4" strokeWidth={1.5} />
            <span>{l.label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="border-t border-[#27272A] p-4">
        <div className="text-xs text-[#9CA3AF] mb-2 truncate" title={email}>{email}</div>
        <button data-testid="logout-btn" onClick={logout} className="btn-ghost text-xs w-full flex items-center gap-2 justify-center">
          <LogOut className="w-3.5 h-3.5" /> Sign out
        </button>
      </div>
    </aside>
  );
}
