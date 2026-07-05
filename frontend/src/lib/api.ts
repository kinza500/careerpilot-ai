// Typed client for the CareerPilot backend. The JWT is stored client-side and
// sent as a bearer token. All CV/profile data is fetched per-request and never
// cached to disk.
const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function token(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("cp_token");
}

export function setToken(t: string) {
  localStorage.setItem("cp_token", t);
}
export function clearToken() {
  localStorage.removeItem("cp_token");
}
export function isAuthed(): boolean {
  return !!token();
}

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers as any) };
  const t = token();
  if (t) headers["Authorization"] = `Bearer ${t}`;
  const res = await fetch(`${API}${path}`, { ...opts, headers });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail || `Request failed (${res.status})`);
  }
  return res.json();
}

export type Profile = { id: string; resume_id: string | null; profile: any };
export type Job = { id: string; title: string; company?: string; location?: string; remote?: boolean; salary?: string; url?: string; source?: string; company_url?: string; contact_email?: string };
export type Match = {
  id: string;
  job: Job;
  score: number;
  reasoning?: string;
  factors?: Record<string, number>;
};
export type Application = {
  id: string; job_id: string; job: Job; status: string;
  resume_filename?: string; resume_uploaded_at?: string;
  tailored_resume?: string; cover_letter?: string; outreach_email?: string;
  critic_notes?: any;
  company_research?: string;
  company_research_grounded?: boolean;
  company_research_sources?: { title: string; url: string }[];
  followup_status?: string;
  has_gmail_draft?: boolean;
  email_sent?: boolean;
  reply_received?: boolean;
  interview_schedule?: InterviewScheduleSuggestion | null;
  calendar_event_id?: string | null;
};
export type InterviewScheduleSuggestion = {
  date: string; time: string; timezone: string; duration_minutes: number;
  location_or_method?: string; summary?: string;
};
export type ApplicationEvent = { kind: string; created_at: string };
export type Followup = {
  application_id: string;
  job: Job;
  days_since_applied: number;
  followup_email: string;
  can_thread: boolean;
  reply_checked: boolean;
};
export type FollowupDraft = {
  application_id: string;
  followup_status: string;
  draft_id?: string;
  url?: string;
  threaded: boolean;
};
export type InterviewTurn = { role: "interviewer" | "candidate"; content: string };
export type InterviewFeedback = {
  readiness_score: number;
  strengths: string[];
  areas_to_improve: string[];
  weakest_answer: string;
  suggested_better_answer: string;
};
export type InterviewSession = {
  id: string;
  application_id: string;
  status: "in_progress" | "completed";
  transcript: InterviewTurn[];
  feedback?: InterviewFeedback;
  created_at: string;
};

export const api = {
  register: (email: string, password: string, full_name: string) =>
    req<{ access_token: string }>("/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, full_name }),
    }),
  login: (email: string, password: string) =>
    req<{ access_token: string }>("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }),
  me: () => req<{ id: string; email: string; full_name?: string }>("/auth/me"),
  uploadResume: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return req<Profile>("/resumes/upload", { method: "POST", body: fd });
  },
  profile: () => req<Profile>("/resumes/profile"),
  discover: (query: string, location: string, work_type: string, limit = 20) =>
    req<Match[]>("/jobs/discover", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, location, work_type, limit }),
    }),
  matches: () => req<Match[]>("/jobs/matches"),
  prepare: (job_id: string) =>
    req<Application>("/applications/prepare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id }),
    }),
  approve: (application_id: string) =>
    req<Application>("/applications/approve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ application_id, confirm: true }),
    }),
  applications: () => req<Application[]>("/applications"),
  googleStatus: () => req<{ connected: boolean; email?: string; has_readonly_scope?: boolean | null; has_calendar_scope?: boolean | null }>("/auth/google/status"),
  googleAuthorize: () => req<{ url: string }>("/auth/google/authorize"),
  draftGmail: (application_id: string) =>
    req<{ draft_id: string; url?: string }>(`/applications/${application_id}/draft-gmail`, {
      method: "POST",
    }),
  followupsDue: () => req<Followup[]>("/applications/followups-due"),
  followupSave: (application_id: string) =>
    req<FollowupDraft>(`/applications/${application_id}/followup/save`, { method: "POST" }),
  followupDraftGmail: (application_id: string) =>
    req<FollowupDraft>(`/applications/${application_id}/followup/draft-gmail`, { method: "POST" }),
  applicationHistory: (application_id: string) =>
    req<ApplicationEvent[]>(`/applications/${application_id}/history`),
  confirmInterviewSchedule: (application_id: string) =>
    req<Application>(`/applications/${application_id}/schedule-interview/confirm`, { method: "POST" }),
  dismissInterviewSchedule: (application_id: string) =>
    req<Application>(`/applications/${application_id}/schedule-interview/dismiss`, { method: "POST" }),
  interviewStart: (application_id: string) =>
    req<InterviewSession>("/interview/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ application_id }),
    }),
  interviewRespond: (session_id: string, answer: string) =>
    req<InterviewSession>(`/interview/${session_id}/respond`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answer }),
    }),
  interviewEnd: (session_id: string) =>
    req<InterviewSession>(`/interview/${session_id}/end`, { method: "POST" }),
  interviewSessions: (application_id?: string) =>
    req<InterviewSession[]>(`/interview/sessions${application_id ? `?application_id=${application_id}` : ""}`),
  interviewSession: (session_id: string) =>
    req<InterviewSession>(`/interview/${session_id}`),
};
