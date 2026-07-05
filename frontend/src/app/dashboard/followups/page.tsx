"use client";
import { useDashboard } from "@/lib/dashboard-context";
import { Clock, Loader2, Mail } from "lucide-react";

export default function FollowupsPage() {
  const { followups, followupBusy, gmail, onFollowupSave, onFollowupDraftGmail } = useDashboard();

  return (
    <div className="space-y-3">
      <h2 className="flex items-center gap-2 font-semibold">
        <Clock className="h-4 w-4" /> Follow-ups due
      </h2>
      <p className="text-xs text-slate-400">
        It&apos;s been 14+ days since these applications went out. Threads
        drafted via Gmail are checked for an actual reply first (any
        application that got one is left off this list entirely) —
        others fall back to this time-based nudge alone.
      </p>

      {followups.length === 0 && (
        <p className="card text-sm text-slate-500">Nothing due right now.</p>
      )}

      {followups.map((f) => (
        <div key={f.application_id} className="card space-y-2">
          <div className="flex items-center gap-2">
            <span className="badge bg-amber-100 text-amber-800">{f.days_since_applied} days ago</span>
            <h3 className="font-medium">{f.job.title}</h3>
            <span className="text-sm text-slate-500">· {f.job.company}</span>
          </div>
          {f.reply_checked ? (
            <p className="text-xs text-slate-400">Checked Gmail — no reply found in this thread.</p>
          ) : (
            <p className="text-xs text-slate-400">
              Couldn&apos;t verify against Gmail (no linked thread, or not connected) — time-based nudge only.
            </p>
          )}
          <pre className="whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-sm text-slate-700">
            {f.followup_email}
          </pre>
          <div className="flex flex-wrap gap-2">
            <button className="btn-ghost" onClick={() => onFollowupSave(f)} disabled={followupBusy === f.application_id}>
              {followupBusy === f.application_id ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Save for later
            </button>
            <button className="btn" onClick={() => onFollowupDraftGmail(f)}
                    disabled={followupBusy === f.application_id || !gmail?.connected}>
              {followupBusy === f.application_id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mail className="h-4 w-4" />}
              {f.can_thread ? "Send as Gmail draft (same thread)" : "Send as Gmail draft"}
            </button>
            {!gmail?.connected && (
              <span className="self-center text-xs text-slate-400">Connect Gmail (top right) to draft this.</span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
