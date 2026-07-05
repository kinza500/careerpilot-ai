export function sourceLabel(source?: string) {
  if (!source) return "the source site";
  const names: Record<string, string> = {
    indeed: "Indeed", linkedin: "LinkedIn", google: "Google Jobs", bayt: "Bayt",
    glassdoor: "Glassdoor", zip_recruiter: "ZipRecruiter", jooble: "Jooble",
    google_jobs: "Google Jobs (via SerpApi)",
  };
  return names[source.toLowerCase()] || source;
}

export const EVENT_LABELS: Record<string, string> = {
  application_prepared: "Application prepared (Writer + Critic agents ran)",
  application_saved_for_later: "Saved for later",
  application_gmail_draft_created: "Drafted to Gmail",
  application_email_sent: "Application email sent (detected via Gmail)",
  application_reply_received: "Reply received (detected via Gmail)",
  interview_schedule_suggested: "Interview time detected in a reply",
  interview_scheduled_confirmed: "Interview added to Google Calendar",
  interview_schedule_dismissed: "Suggested interview time dismissed",
  followup_saved: "Follow-up saved for later",
  followup_gmail_draft_created: "Follow-up drafted to Gmail",
  followup_email_sent: "Follow-up email sent (detected via Gmail)",
  followup_auto_responded: "Reply detected in Gmail thread",
};

// Company research comes back as "- **Label:** text" lines from the LLM —
// split into plain bullet strings for rendering as a <ul>, bold markers kept
// intact so the caller can render them (see boldSegments below).
export function parseBullets(text?: string): string[] {
  if (!text) return [];
  return text
    .split("\n")
    .map((l) => l.trim().replace(/^[-*]\s*/, ""))
    .filter(Boolean);
}

// Splits "**bold**" markdown into alternating plain/bold segments for a
// lightweight render without pulling in a full markdown parser.
export function boldSegments(line: string): { text: string; bold: boolean }[] {
  return line.split(/\*\*(.+?)\*\*/g).map((text, i) => ({ text, bold: i % 2 === 1 })).filter((s) => s.text);
}

export function formatEventTime(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium", timeStyle: "short",
  });
}

export function scoreColor(s: number) {
  if (s >= 70) return "bg-teal-100 text-teal-800";
  if (s >= 45) return "bg-amber-100 text-amber-800";
  return "bg-slate-100 text-slate-600";
}

export function statusColor(status: string) {
  if (status === "approved") return "bg-teal-100 text-teal-800";
  if (status === "review") return "bg-amber-100 text-amber-800";
  return "bg-slate-100 text-slate-600";
}

// Strong/stable economies that commonly draw skilled-worker relocation —
// matched 1:1 against the backend's DestinationCountry validation and its
// per-country job-board coverage (app.agents.discovery_agent.COUNTRY_SITES).
export const DESTINATION_COUNTRIES = [
  "Pakistan", "United Arab Emirates", "Saudi Arabia", "Qatar", "Kuwait",
  "USA", "Canada", "UK", "Germany", "Australia", "Singapore", "Ireland",
  "Netherlands", "New Zealand",
];
