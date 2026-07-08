import React from "react";

const map = {
  ACTIVE: "badge-active",
  GRACE: "badge-grace",
  EXPIRED: "badge-expired",
  CANCELLED: "badge-cancelled",
  REFUNDED: "badge-refunded",
  ADMIN_COMP: "badge-comp",
};

export default function StatusPill({ status }) {
  const cls = map[status] || "badge-cancelled";
  return (
    <span
      data-testid={`status-${status}`}
      className={`inline-flex items-center px-2 py-0.5 text-[10.5px] font-mono-plex tracking-[0.18em] uppercase rounded-sm ${cls}`}
    >
      {status || "—"}
    </span>
  );
}
