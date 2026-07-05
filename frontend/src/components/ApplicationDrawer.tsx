"use client";
import { useDashboard } from "@/lib/dashboard-context";
import { type Application } from "@/lib/api";
import { EVENT_LABELS, boldSegments, formatEventTime, parseBullets, sourceLabel } from "@/lib/format";
import { Building2, CalendarCheck, CalendarPlus, Check, Clock, ExternalLink, Loader2, Mail, Search, X } from "lucide-react";

function InterviewScheduleBanner({ active }: { active: Application }) {
  const { gmail, scheduleBusy, onConfirmSchedule, onDismissSchedule } = useDashboard();
  if (active.calendar_event_id) {
    return (
      <div className="mb-4 flex items-center gap-2 rounded-lg bg-teal-50 p-3 text-sm text-teal-800">
        <CalendarCheck className="h-4 w-4 shrink-0" /> Added to your Google Calendar.
      </div>
    );
  }
  const sched = active.interview_schedule;
  if (!sched) return null;

  let when = `${sched.date} ${sched.time}`;
  try {
    when = new Date(`${sched.date}T${sched.time}:00`).toLocaleString(undefined, {
      dateStyle: "full", timeStyle: "short",
    });
  } catch { /* fall back to raw date/time strings above */ }

  return (
    <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3">
      <h3 className="mb-1 flex items-center gap-1.5 text-sm font-semibold text-amber-900">
        <CalendarPlus className="h-4 w-4" /> Interview time detected in a reply
      </h3>
      <p className="mb-2 text-sm text-amber-900">
        <strong>{when}</strong> ({sched.timezone}, ~{sched.duration_minutes} min)
        {sched.location_or_method ? ` — ${sched.location_or_method}` : ""}
      </p>
      <p className="mb-3 text-xs text-amber-700">
        Extracted from the company's reply — double-check it matches before adding it, nothing is added automatically.
      </p>
      <div className="flex flex-wrap gap-2">
        <button className="btn shrink-0" onClick={onConfirmSchedule} disabled={scheduleBusy || !gmail?.has_calendar_scope}>
          {scheduleBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CalendarPlus className="h-4 w-4" />}
          Add to calendar
        </button>
        <button className="btn-ghost shrink-0" onClick={onDismissSchedule} disabled={scheduleBusy}>
          Not an interview / ignore
        </button>
      </div>
      {!gmail?.has_calendar_scope && (
        <p className="mt-2 text-xs text-amber-700">
          Reconnect Gmail (top right) to grant calendar access before this can be added.
        </p>
      )}
    </div>
  );
}

function CompanyResearch({ text, grounded, sources }: { text?: string; grounded?: boolean; sources?: { title: string; url: string }[] }) {
  const bullets = parseBullets(text);
  if (bullets.length === 0) return null;
  return (
    <div className="mb-4">
      <h3 className="mb-1 flex items-center gap-1.5 text-sm font-semibold text-slate-700">
        <Search className="h-3.5 w-3.5" /> Company research
      </h3>
      <p className="mb-2 text-xs text-slate-400">
        {grounded
          ? "Based on a live web search, done automatically before writing your documents."
          : "Generated without a live web search (none configured or none found) — treat as a starting point, not a fact."}
        {" "}Used to help write the cover letter and outreach email below.
      </p>
      <ul className="list-disc space-y-1 rounded-lg bg-slate-50 p-3 pl-8 text-sm text-slate-700">
        {bullets.map((b, i) => (
          <li key={i}>
            {boldSegments(b).map((seg, j) => (seg.bold ? <strong key={j}>{seg.text}</strong> : <span key={j}>{seg.text}</span>))}
          </li>
        ))}
      </ul>
      {sources && sources.length > 0 && (
        <div className="mt-2 rounded-lg bg-slate-50 p-3">
          <p className="mb-1 text-xs font-medium text-slate-500">Sources</p>
          <ul className="space-y-1">
            {sources.map((s, i) => (
              <li key={i}>
                <a href={s.url} target="_blank" rel="noopener noreferrer"
                   className="flex items-start gap-1 text-xs text-brand hover:underline">
                  <ExternalLink className="mt-0.5 h-3 w-3 shrink-0" /> <span className="break-all">{s.title}</span>
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Section({ title, body }: { title: string; body?: string }) {
  if (!body) return null;
  return (
    <div className="mb-4">
      <h3 className="mb-1 text-sm font-semibold text-slate-700">{title}</h3>
      <pre className="whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-sm text-slate-700">{body}</pre>
    </div>
  );
}

export default function ApplicationDrawer() {
  const { active, setActive, history, gmail, drafting, onKeepAsDraft, onApprove } = useDashboard();
  if (!active) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={() => setActive(null)}>
      <div className="h-full w-full max-w-2xl overflow-y-auto bg-white p-6" onClick={(e) => e.stopPropagation()}>
        <div className="mb-1 flex items-center justify-between">
          <h2 className="text-lg font-semibold">{active.job.title}</h2>
          <button className="btn-ghost" onClick={() => setActive(null)}><X className="h-4 w-4" /></button>
        </div>
        <p className="mb-3 text-sm text-slate-500">
          {active.job.company} {active.job.location ? `· ${active.job.location}` : ""}
          {active.job.remote ? " · remote" : ""}
        </p>

        <div className="mb-3 flex flex-wrap gap-3 text-xs">
          {active.job.url && (
            <a href={active.job.url} target="_blank" rel="noopener noreferrer"
               className="flex items-center gap-1 text-brand hover:underline">
              <ExternalLink className="h-3 w-3" /> View on {sourceLabel(active.job.source)}
            </a>
          )}
          {active.job.company_url && (
            <a href={active.job.company_url} target="_blank" rel="noopener noreferrer"
               className="flex items-center gap-1 text-brand hover:underline">
              <Building2 className="h-3 w-3" /> Company website
            </a>
          )}
          {active.job.contact_email && (
            <span className="flex items-center gap-1 text-slate-500">
              <Mail className="h-3 w-3" /> {active.job.contact_email}
            </span>
          )}
        </div>

        {active.resume_filename && (
          <p className="mb-3 text-xs text-slate-500">Resume used: {active.resume_filename}</p>
        )}

        <div className="mb-3 flex flex-wrap items-center gap-2">
          <span className={`badge ${active.status === "approved" ? "bg-teal-100 text-teal-800" : "bg-amber-100 text-amber-800"}`}>
            {active.status === "approved" ? "saved" : active.status}
          </span>
          {active.critic_notes?.score != null && (
            <span className="badge bg-slate-100 text-slate-600">Critic score: {active.critic_notes.score}/100</span>
          )}
          {active.has_gmail_draft && (
            active.email_sent ? (
              <span className="badge bg-teal-100 text-teal-800"><Check className="h-3 w-3" /> sent (detected via Gmail)</span>
            ) : (
              <span className="badge bg-slate-100 text-slate-600"><Mail className="h-3 w-3" /> drafted to Gmail, not yet sent</span>
            )
          )}
          {active.followup_status && (
            <span className={`badge ${active.followup_status === "responded" || active.followup_status === "sent" ? "bg-teal-100 text-teal-800" : "bg-slate-100 text-slate-600"}`}>
              {active.followup_status === "responded" || active.followup_status === "sent" ? <Check className="h-3 w-3" /> : <Clock className="h-3 w-3" />}
              {active.followup_status === "responded" ? "got a reply"
                : active.followup_status === "sent" ? "follow-up sent"
                : `follow-up ${active.followup_status}`}
            </span>
          )}
        </div>

        <InterviewScheduleBanner active={active} />

        {active.critic_notes?.issues?.length > 0 && (
          <div className="mb-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
            <p className="font-medium">Critic notes</p>
            <ul className="list-disc pl-5">
              {active.critic_notes.issues.map((i: string, k: number) => <li key={k}>{i}</li>)}
            </ul>
          </div>
        )}

        <CompanyResearch text={active.company_research} grounded={active.company_research_grounded} sources={active.company_research_sources} />

        <Section title="Cover letter" body={active.cover_letter} />
        <Section title="Outreach email" body={active.outreach_email} />
        <Section title="Tailored resume" body={active.tailored_resume} />

        {history.length > 0 && (
          <div className="mb-4">
            <h3 className="mb-2 text-sm font-semibold text-slate-700">History</h3>
            <ul className="space-y-2 border-l-2 border-slate-200 pl-4">
              {history.map((e, i) => (
                <li key={i} className="text-sm">
                  <p className="text-slate-700">{EVENT_LABELS[e.kind] || e.kind}</p>
                  <p className="text-xs text-slate-400">{formatEventTime(e.created_at)}</p>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="sticky bottom-0 mt-6 flex gap-2 border-t border-slate-200 bg-white pt-4">
          <button className="btn-ghost flex-1 justify-center" onClick={onKeepAsDraft} disabled={drafting}>
            {drafting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            {gmail?.connected ? "Keep as draft (save to Gmail)" : "Keep as draft"}
          </button>
          <button
            className="btn flex-1 justify-center"
            onClick={onApprove}
            disabled={active.status === "approved" || active.has_gmail_draft || drafting}
            title={active.has_gmail_draft ? "Already kept as a Gmail draft — no need to also save for later." : undefined}
          >
            <Check className="h-4 w-4" />
            {active.status === "approved" ? "Saved" : active.has_gmail_draft ? "Drafted to Gmail" : "Save for later"}
          </button>
        </div>
        {!gmail?.connected && (
          <p className="mt-2 text-center text-xs text-slate-400">
            Connect Gmail (top right) to also save this as a real draft in your inbox.
          </p>
        )}
        <p className="mt-2 text-center text-xs text-slate-400">
          CareerPilot never sends anything on its own — this only saves the
          application so you can find and send it yourself whenever you're ready.
        </p>
      </div>
    </div>
  );
}
