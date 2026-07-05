"use client";
import { useMemo, useState } from "react";
import { type Application } from "@/lib/api";
import { useDashboard } from "@/lib/dashboard-context";
import { Check, Clock, Mail, Search, X } from "lucide-react";

// Single consolidated view of the application's own email lifecycle — mirrors
// the shape of the Follow-up filter below (a natural progression, most-
// advanced state wins when more than one is technically true at once).
const APPLICATION_STATUS_OPTIONS = [
  { value: "all", label: "Any status" },
  { value: "saved", label: "Saved for later" },
  { value: "drafted", label: "Drafted" },
  { value: "sent", label: "Sent" },
  { value: "responded", label: "Reply arrived" },
];

const FOLLOWUP_OPTIONS = [
  { value: "all", label: "Any follow-up state" },
  { value: "none", label: "Not started" },
  { value: "saved", label: "Follow-up noted (not sent anywhere)" },
  { value: "drafted", label: "Follow-up drafted in Gmail, not yet sent" },
  { value: "sent", label: "Follow-up sent (detected via Gmail)" },
  { value: "responded", label: "They replied" },
];

const FOLLOWUP_LABELS: Record<string, string> = {
  saved: "Follow-up noted", drafted: "Follow-up drafted", sent: "Follow-up sent", responded: "They replied",
};

// Detected live via gmail.readonly checks, never assumed — "responded" and
// "sent" outrank "drafted"/"saved" since they're strictly later stages of
// the same lifecycle, even if e.g. both status="approved" and email_sent
// happen to be true at once.
function applicationState(a: Application): "none" | "saved" | "drafted" | "sent" | "responded" {
  if (a.reply_received) return "responded";
  if (a.email_sent) return "sent";
  if (a.has_gmail_draft) return "drafted";
  if (a.status === "approved") return "saved";
  return "none";
}

const APPLICATION_STATE_LABELS: Record<string, string> = {
  saved: "Saved for later", drafted: "Drafted", sent: "Sent", responded: "Reply arrived",
};

export default function ApplicationsPage() {
  const { applications, setActive } = useDashboard();
  const [appStatusFilter, setAppStatusFilter] = useState("all");
  const [followupFilter, setFollowupFilter] = useState("all");
  const [q, setQ] = useState("");

  // Every active filter below must match (AND, not OR) — e.g. status=Saved
  // for later + follow-up=Not started shows only rows satisfying both at once.
  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return applications.filter((a) => {
      if (appStatusFilter !== "all" && applicationState(a) !== appStatusFilter) return false;
      if (followupFilter !== "all") {
        const fs = a.followup_status || "none";
        if (fs !== followupFilter) return false;
      }
      if (needle) {
        const hay = `${a.job.title} ${a.job.company || ""} ${a.job.location || ""}`.toLowerCase();
        if (!hay.includes(needle)) return false;
      }
      return true;
    });
  }, [applications, appStatusFilter, followupFilter, q]);

  const activeFilterCount =
    (appStatusFilter !== "all" ? 1 : 0) +
    (followupFilter !== "all" ? 1 : 0) +
    (q.trim() ? 1 : 0);

  function clearFilters() {
    setAppStatusFilter("all"); setFollowupFilter("all"); setQ("");
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">Applications</h2>
        <span className="text-xs text-slate-400">{filtered.length} of {applications.length}</span>
      </div>

      <div className="card space-y-3">
        <div className="flex items-center justify-between">
          <p className="text-xs font-medium text-slate-500">
            Filter by (all conditions must match at once):
          </p>
          {activeFilterCount > 0 && (
            <button className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700" onClick={clearFilters}>
              <X className="h-3 w-3" /> Clear {activeFilterCount} filter{activeFilterCount > 1 ? "s" : ""}
            </button>
          )}
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-[200px] flex-1">
            <label className="mb-1 block text-xs font-medium text-slate-500">Search title, company, location</label>
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input className="input w-full pl-8" placeholder="e.g. backend engineer, Acme Inc..."
                     value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">Application status</label>
            <select className="input w-52" value={appStatusFilter} onChange={(e) => setAppStatusFilter(e.target.value)}>
              {APPLICATION_STATUS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">Follow-up status</label>
            <select className="input w-56" value={followupFilter} onChange={(e) => setFollowupFilter(e.target.value)}>
              {FOLLOWUP_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
        </div>
      </div>

      {applications.length === 0 ? (
        <p className="card text-sm text-slate-500">No applications yet — prepare one from Discover &amp; Rank.</p>
      ) : filtered.length === 0 ? (
        <p className="card text-sm text-slate-500">No applications match these filters.</p>
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead className="border-b border-slate-200 text-xs uppercase text-slate-400">
                <tr>
                  <th className="px-4 py-3 font-medium">Role</th>
                  <th className="px-4 py-3 font-medium">Company</th>
                  <th className="px-4 py-3 font-medium">Location</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Follow-up</th>
                  <th className="px-4 py-3 font-medium">Resume</th>
                  <th className="px-4 py-3 font-medium"></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((a) => {
                  const state = applicationState(a);
                  return (
                    <tr key={a.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                      <td className="px-4 py-3 font-medium text-slate-800">{a.job.title}</td>
                      <td className="px-4 py-3 text-slate-600">{a.job.company || "—"}</td>
                      <td className="px-4 py-3 text-slate-600">
                        {a.job.location || "—"} {a.job.remote ? "(remote)" : ""}
                      </td>
                      <td className="px-4 py-3">
                        {state === "responded" || state === "sent" ? (
                          <span className="badge bg-teal-100 text-teal-800"><Check className="h-3 w-3" /> {APPLICATION_STATE_LABELS[state]}</span>
                        ) : state === "drafted" || state === "saved" ? (
                          <span className="badge bg-slate-100 text-slate-600"><Mail className="h-3 w-3" /> {APPLICATION_STATE_LABELS[state]}</span>
                        ) : (
                          <span className="text-xs text-slate-400">Not started</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        {a.followup_status === "responded" ? (
                          <span className="badge bg-teal-100 text-teal-800"><Mail className="h-3 w-3" /> {FOLLOWUP_LABELS.responded}</span>
                        ) : a.followup_status === "sent" ? (
                          <span className="badge bg-teal-100 text-teal-800"><Check className="h-3 w-3" /> {FOLLOWUP_LABELS.sent}</span>
                        ) : a.followup_status ? (
                          <span className="badge bg-slate-100 text-slate-600"><Clock className="h-3 w-3" /> {FOLLOWUP_LABELS[a.followup_status] || a.followup_status}</span>
                        ) : (
                          <span className="text-xs text-slate-400">Not started</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-500">{a.resume_filename || "—"}</td>
                      <td className="px-4 py-3 text-right">
                        <button className="btn-ghost" onClick={() => setActive(a)}>View</button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
