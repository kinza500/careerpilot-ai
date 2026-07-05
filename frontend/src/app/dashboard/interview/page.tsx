"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type InterviewSession } from "@/lib/api";
import { useDashboard } from "@/lib/dashboard-context";
import { formatEventTime } from "@/lib/format";
import { Award, Loader2, MessagesSquare } from "lucide-react";

export default function InterviewPrepPage() {
  const { applications } = useDashboard();
  const [sessions, setSessions] = useState<InterviewSession[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(true);

  useEffect(() => {
    api.interviewSessions()
      .then(setSessions)
      .catch(() => {})
      .finally(() => setLoadingHistory(false));
  }, []);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="flex items-center gap-2 text-lg font-bold text-slate-800">
          <MessagesSquare className="h-5 w-5 text-brand" /> Interview prep
        </h1>
      </div>

      <section>
        <div className="mb-3 flex items-center gap-2 border-b-2 border-brand/20 pb-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-brand/10 text-brand">
            <MessagesSquare className="h-4 w-4" />
          </span>
          <h2 className="text-base font-bold text-slate-800">Practice a new interview</h2>
        </div>
        <p className="mb-3 text-xs text-slate-400">
          Pick any application you've acted on — grounded in that job's real
          description, your tailored resume, and the company research already
          gathered for it.
        </p>

        {applications.length === 0 ? (
          <p className="card text-sm text-slate-500">
            No applications yet — prepare one from Discover &amp; Rank first, then come back here to practice for it.
          </p>
        ) : (
          <div className="space-y-2">
            {applications.map((a) => (
              <div key={a.id} className="card flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <div>
                  <h3 className="font-medium">{a.job.title}</h3>
                  <p className="text-sm text-slate-500">
                    {a.job.company} {a.job.location ? `· ${a.job.location}` : ""}
                  </p>
                </div>
                <Link href={`/dashboard/interview/${a.id}`} className="btn shrink-0">
                  <MessagesSquare className="h-4 w-4" /> Practice interview
                </Link>
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <div className="mb-3 flex items-center gap-2 border-b-2 border-amber-400/30 pb-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-amber-100 text-amber-700">
            <Award className="h-4 w-4" />
          </span>
          <h2 className="text-base font-bold text-slate-800">Your interview history</h2>
        </div>
        <p className="mb-3 text-xs text-slate-400">
          Every past session — the exact questions asked, your own answers,
          and the detailed feedback — stays here for you to revisit anytime.
        </p>

        {loadingHistory ? (
          <p className="card flex items-center gap-2 text-sm text-slate-500">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading history...
          </p>
        ) : sessions.length === 0 ? (
          <p className="card text-sm text-slate-500">No interview sessions yet.</p>
        ) : (
          <div className="space-y-2">
            {sessions.map((s) => {
              const app = applications.find((a) => a.id === s.application_id);
              return (
                <div key={s.id} className="card flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                  <div>
                    <h3 className="font-medium">{app ? `${app.job.title} at ${app.job.company || "—"}` : "Application"}</h3>
                    <p className="text-xs text-slate-400">
                      {formatEventTime(s.created_at)} ·{" "}
                      {s.status === "completed" && s.feedback
                        ? `Readiness ${s.feedback.readiness_score}/100`
                        : "In progress"}
                      {" · "}{s.transcript.filter((t) => t.role === "interviewer").length} question
                      {s.transcript.filter((t) => t.role === "interviewer").length === 1 ? "" : "s"}
                    </p>
                  </div>
                  <Link href={`/dashboard/interview/${s.application_id}?session=${s.id}`} className="btn-ghost shrink-0">
                    View full transcript &amp; feedback
                  </Link>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
