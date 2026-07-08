import React from "react";
import Sidebar from "./Sidebar";

export default function AdminLayout({ children, title, subtitle, actions }) {
  return (
    <div className="min-h-screen flex bg-[#0A0A0A]" data-testid="admin-layout">
      <Sidebar />
      <main className="flex-1 min-w-0">
        <header className="border-b border-[#27272A] px-8 py-5 flex items-center justify-between bg-[#0A0A0A] sticky top-0 z-10">
          <div>
            <div className="kicker">{subtitle || "Control Room"}</div>
            <h1 className="font-chivo font-black text-2xl mt-1 tracking-tight" data-testid="page-title">{title}</h1>
          </div>
          <div className="flex items-center gap-3">{actions}</div>
        </header>
        <div className="p-8">{children}</div>
      </main>
    </div>
  );
}
