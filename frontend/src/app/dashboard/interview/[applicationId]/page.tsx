"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { api, type InterviewSession } from "@/lib/api";
import { useDashboard } from "@/lib/dashboard-context";
import { Award, Bot, Loader2, MessagesSquare, Send, User } from "lucide-react";

const MAX_QUESTIONS = 5; // keep in sync with backend app/agents/interview_agent.py

// All MAX_QUESTIONS have been asked once the transcript ends on a candidate
// answer with no further interviewer question appended after it — mirrors
// the backend's own cap logic in routers/interview.py.
function allQuestionsAsked(session: InterviewSession): boolean {
  const asked = session.transcript.filter((t) => t.role === "interviewer").length;
  const last = session.transcript[session.transcript.length - 1];
  return asked >= MAX_QUESTIONS && last?.role === "candidate";
}

export default function InterviewSessionPage({ params }: { params: { applicationId: string } }) {
  const { applicationId } = params;
  const searchParams = useSearchParams();
  const requestedSessionId = searchParams.get("session");
  const { applications } = useDashboard();
  const application = applications.find((a) => a.id === applicationId);

  const [loading, setLoading] = useState(true);
  const [past, setPast] = useState<InterviewSession[]>([]);
  const [session, setSession] = useState<InterviewSession | null>(null);
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.interviewSessions(applicationId)
      .then((sessions) => {
        setPast(sessions);
        // A specific past session linked from Interview History takes
        // priority over auto-resuming whatever's in progress.
        const requested = requestedSessionId && sessions.find((s) => s.id === requestedSessionId);
        const active = sessions.find((s) => s.status === "in_progress");
        if (requested) setSession(requested);
        else if (active) setSession(active);
      })
      .catch((e) => setMsg(e.message))
      .finally(() => setLoading(false));
  }, [applicationId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session?.transcript.length]);

  async function startNew() {
    setBusy(true); setMsg("");
    try {
      const s = await api.interviewStart(applicationId);
      setSession(s);
    } catch (e: any) { setMsg(e.message); }
    finally { setBusy(false); }
  }

  async function send() {
    if (!session || !answer.trim()) return;
    setBusy(true); setMsg("");
    const text = answer;
    setAnswer("");
    try {
      const s = await api.interviewRespond(session.id, text);
      setSession(s);
    } catch (e: any) { setMsg(e.message); setAnswer(text); }
    finally { setBusy(false); }
  }

  async function endInterview() {
    if (!session) return;
    setBusy(true); setMsg("");
    try {
      const s = await api.interviewEnd(session.id);
      setSession(s);
      setPast((prev) => [s, ...prev.filter((p) => p.id !== s.id)]);
    } catch (e: any) { setMsg(e.message); }
    finally { setBusy(false); }
  }

  if (loading) {
    return <p className="card text-sm text-slate-500">Loading...</p>;
  }

  return (
    <div className="space-y-4">
      <div>
        <Link href="/dashboard/interview" className="text-xs text-brand hover:underline">&larr; Back to interview prep</Link>
        <h2 className="mt-1 flex items-center gap-2 font-semibold">
          <MessagesSquare className="h-4 w-4" />
          {application ? `${application.job.title} at ${application.job.company || "—"}` : "Mock interview"}
        </h2>
      </div>

      {msg && <div className="rounded-lg bg-slate-100 px-4 py-2 text-sm text-slate-700">{msg}</div>}

      {!session && (
        <div className="card space-y-3 text-sm text-slate-600">
          <p>
            Start a live mock interview for this role — {MAX_QUESTIONS} questions,
            adapted to what you actually answer as you go. There's no fixed
            question list; each follow-up reacts to your last response.
          </p>
          <button className="btn" onClick={startNew} disabled={busy}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <MessagesSquare className="h-4 w-4" />}
            Start interview
          </button>
        </div>
      )}

      {session && (
        <div className="card flex h-[60vh] flex-col p-0">
          {session.status === "in_progress" && (
            <div className="border-b border-slate-200 px-4 py-2 text-xs text-slate-400">
              Question {Math.min(session.transcript.filter((t) => t.role === "interviewer").length, MAX_QUESTIONS)} of {MAX_QUESTIONS}
            </div>
          )}
          <div className="flex-1 space-y-3 overflow-y-auto p-4">
            {session.transcript.map((t, i) => (
              <div key={i} className={`flex gap-2 ${t.role === "candidate" ? "flex-row-reverse" : ""}`}>
                <div className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${
                  t.role === "candidate" ? "bg-brand text-white" : "bg-slate-100 text-slate-600"
                }`}>
                  {t.role === "candidate" ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
                </div>
                <div className={`max-w-[75%] rounded-lg px-3 py-2 text-sm ${
                  t.role === "candidate" ? "bg-brand text-white" : "bg-slate-100 text-slate-700"
                }`}>
                  {t.content}
                </div>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>

          {session.status === "in_progress" && !allQuestionsAsked(session) && (
            <div className="border-t border-slate-200 p-3">
              <div className="flex items-end gap-2">
                <textarea
                  className="input flex-1 resize-none"
                  rows={2}
                  placeholder="Type your answer..."
                  value={answer}
                  onChange={(e) => setAnswer(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
                  disabled={busy}
                />
                <button className="btn shrink-0" onClick={send} disabled={busy || !answer.trim()}>
                  {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                </button>
              </div>
              <button
                className="mt-2 text-xs text-slate-400 hover:text-slate-600 hover:underline"
                onClick={endInterview}
                disabled={busy || session.transcript.length < 2}
              >
                End early &amp; get feedback now
              </button>
            </div>
          )}
          {session.status === "in_progress" && allQuestionsAsked(session) && (
            <div className="space-y-2 border-t border-slate-200 p-3 text-center">
              <p className="text-xs text-slate-500">
                That's all {MAX_QUESTIONS} questions — ready for your feedback?
              </p>
              <button className="btn" onClick={endInterview} disabled={busy}>
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Award className="h-4 w-4" />}
                End &amp; get feedback
              </button>
            </div>
          )}
          {session.status === "completed" && (
            <div className="border-t border-slate-200 p-3 text-center text-xs text-slate-400">
              This interview has ended — see your feedback below.
            </div>
          )}
        </div>
      )}

      {session?.status === "completed" && session.feedback && (
        <div className="card space-y-3">
          <h3 className="flex items-center gap-2 font-semibold">
            <Award className="h-4 w-4" /> Feedback
          </h3>
          <div className="flex items-center gap-2">
            <span className="badge bg-teal-100 text-teal-800">Readiness: {session.feedback.readiness_score}/100</span>
          </div>
          {session.feedback.strengths?.length > 0 && (
            <div>
              <p className="text-sm font-medium text-slate-700">Strengths</p>
              <ul className="list-disc pl-5 text-sm text-slate-600">
                {session.feedback.strengths.map((s, i) => <li key={i}>{s}</li>)}
              </ul>
            </div>
          )}
          {session.feedback.areas_to_improve?.length > 0 && (
            <div>
              <p className="text-sm font-medium text-slate-700">Areas to improve</p>
              <ul className="list-disc pl-5 text-sm text-slate-600">
                {session.feedback.areas_to_improve.map((s, i) => <li key={i}>{s}</li>)}
              </ul>
            </div>
          )}
          {session.feedback.weakest_answer && (
            <div>
              <p className="text-sm font-medium text-slate-700">Weakest moment</p>
              <p className="rounded-lg bg-slate-50 p-3 text-sm text-slate-600">{session.feedback.weakest_answer}</p>
            </div>
          )}
          {session.feedback.suggested_better_answer && (
            <div>
              <p className="text-sm font-medium text-slate-700">A stronger version</p>
              <p className="rounded-lg bg-slate-50 p-3 text-sm text-slate-600">{session.feedback.suggested_better_answer}</p>
            </div>
          )}
          <button className="btn" onClick={startNew} disabled={busy}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <MessagesSquare className="h-4 w-4" />}
            Practice again
          </button>
        </div>
      )}

      {past.length > 1 && (
        <div className="card">
          <p className="mb-2 text-xs font-medium text-slate-500">Past sessions for this application</p>
          <ul className="space-y-1 text-sm">
            {past.filter((p) => p.id !== session?.id).map((p) => (
              <li key={p.id}>
                <button className="text-brand hover:underline" onClick={() => setSession(p)}>
                  {p.status === "completed" && p.feedback
                    ? `Completed — readiness ${p.feedback.readiness_score}/100`
                    : "In progress"}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
