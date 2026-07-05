"use client";
import { useMemo, useState } from "react";
import { api, type Match } from "@/lib/api";
import { useDashboard } from "@/lib/dashboard-context";
import { DESTINATION_COUNTRIES, sourceLabel } from "@/lib/format";
import { Building2, ExternalLink, FileUp, Loader2, Mail, Search, ShieldCheck, Sparkles } from "lucide-react";

export default function DiscoverPage() {
  const {
    profile, setProfile, uploading, setUploading,
    setActive, refreshApplications, approvedJobIds, setMsg,
  } = useDashboard();

  const [query, setQuery] = useState("");
  const [location, setLocation] = useState("Pakistan");
  const [workType, setWorkType] = useState("remote");
  const [searching, setSearching] = useState(false);
  const [matches, setMatches] = useState<Match[]>([]);
  const [preparing, setPreparing] = useState<string | null>(null);

  const visibleMatches = useMemo(
    () => matches.filter((m) => !approvedJobIds.includes(m.job.id)),
    [matches, approvedJobIds]
  );

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    const previousProfile = profile;
    setUploading(true); setMsg(""); setProfile(null); setMatches([]);
    try {
      const p = await api.uploadResume(f);
      setProfile(p);
      setMsg("Resume parsed. Your structured profile is ready.");
    } catch (e: any) {
      setProfile(previousProfile);
      setMsg(e.message);
    } finally { setUploading(false); }
  }

  async function onSearch(e: React.FormEvent) {
    e.preventDefault();
    setSearching(true); setMsg("");
    try {
      const m = await api.discover(query, location, workType);
      setMatches(m);
      if (m.length === 0) setMsg("No jobs returned (job boards may be rate-limited in this environment).");
    } catch (e: any) { setMsg(e.message); }
    finally { setSearching(false); }
  }

  async function onPrepare(m: Match) {
    setPreparing(m.job.id); setMsg("");
    try {
      const app = await api.prepare(m.job.id);
      setActive(app);
      refreshApplications();
    } catch (e: any) { setMsg(e.message); }
    finally { setPreparing(null); }
  }

  const skills: string[] = profile?.profile?.skills || [];

  return (
    <div className="space-y-6">
      <div className="grid gap-6 md:grid-cols-3">
        {/* Profile / upload */}
        <section className="card md:col-span-1">
          <h2 className="mb-1 font-semibold">Your profile</h2>
          <p className="mb-3 flex items-center gap-1 text-xs text-slate-500">
            <ShieldCheck className="h-3.5 w-3.5" /> Encrypted &amp; private to you
          </p>
          {profile ? (
            <>
              <p className="text-sm font-medium">{profile.profile?.headline || profile.profile?.name}</p>
              <p className="mt-1 text-xs text-slate-500">{profile.profile?.summary}</p>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {skills.slice(0, 18).map((s) => (
                  <span key={s} className="badge bg-slate-100 text-slate-600">{s}</span>
                ))}
              </div>
            </>
          ) : (
            <p className="text-sm text-slate-500">
              {uploading ? "Processing your resume..." : "No resume yet. Upload one to begin."}
            </p>
          )}
          <label className="btn mt-4 w-full cursor-pointer justify-center">
            {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileUp className="h-4 w-4" />}
            {uploading ? "Uploading..." : profile ? "Replace resume" : "Upload resume"}
            <input type="file" accept=".pdf,.docx,.txt" className="hidden" onChange={onUpload} disabled={uploading} />
          </label>
          {uploading && (
            <p className="mt-2 text-xs text-slate-500">
              Parsing your resume and building your skill profile — this can take
              a minute (longer the first time, while models download). Please
              don&apos;t close this tab.
            </p>
          )}
        </section>

        {/* Search */}
        <section className="card md:col-span-2">
          <h2 className="mb-3 font-semibold">Discover &amp; rank roles</h2>
          <form onSubmit={onSearch} className="flex flex-wrap gap-2">
            <input className="input flex-1" placeholder="Role, e.g. backend engineer"
                   value={query} onChange={(e) => setQuery(e.target.value)} required />
            <select className="input w-48" value={location} onChange={(e) => setLocation(e.target.value)}>
              {DESTINATION_COUNTRIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
            <select className="input w-36" value={workType} onChange={(e) => setWorkType(e.target.value)}>
              <option value="remote">Remote</option>
              <option value="onsite">On-site</option>
              <option value="hybrid">Hybrid</option>
            </select>
            <button className="btn" disabled={searching || uploading || !profile}>
              {searching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              Search
            </button>
          </form>
          {!profile && !uploading && <p className="mt-2 text-xs text-amber-600">Upload a resume first to enable ranking.</p>}
          {uploading && <p className="mt-2 text-xs text-amber-600">Waiting for resume upload to finish...</p>}
          <p className="mt-2 text-xs text-slate-400">
            Agents run: Discovery → semantic Matching → explainable Ranking.
          </p>
        </section>
      </div>

      {/* Matches */}
      {visibleMatches.length > 0 && (
        <section className="space-y-3">
          <h2 className="font-semibold">Ranked matches</h2>
          {visibleMatches.map((m) => (
            <div key={m.id} className="card flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className={`badge ${m.score >= 70 ? "bg-teal-100 text-teal-800" : m.score >= 45 ? "bg-amber-100 text-amber-800" : "bg-slate-100 text-slate-600"}`}>
                    {Math.round(m.score)}% fit
                  </span>
                  <h3 className="font-medium">{m.job.title}</h3>
                </div>
                <p className="text-sm text-slate-500">
                  {m.job.company} · {m.job.location} {m.job.remote ? "· remote" : ""}
                </p>
                {m.job.contact_email ? (
                  <p className="mt-1 flex items-center gap-1 text-xs text-slate-500">
                    <Mail className="h-3 w-3" /> {m.job.contact_email}
                  </p>
                ) : (
                  <p className="mt-1 text-xs text-slate-400">No contact email listed on this posting.</p>
                )}
                <div className="mt-1 flex flex-wrap gap-3 text-xs">
                  {m.job.url && (
                    <a href={m.job.url} target="_blank" rel="noopener noreferrer"
                       className="flex items-center gap-1 text-brand hover:underline">
                      <ExternalLink className="h-3 w-3" /> View on {sourceLabel(m.job.source)}
                    </a>
                  )}
                  {m.job.company_url && (
                    <a href={m.job.company_url} target="_blank" rel="noopener noreferrer"
                       className="flex items-center gap-1 text-brand hover:underline">
                      <Building2 className="h-3 w-3" /> Company website
                    </a>
                  )}
                </div>
                {m.reasoning && <p className="mt-2 text-sm text-slate-700">{m.reasoning}</p>}
                {m.factors && (
                  <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-500">
                    {Object.entries(m.factors).map(([k, v]) => (
                      <span key={k} className="badge bg-slate-50">{k}: {Math.round((v as number) * 100)}%</span>
                    ))}
                  </div>
                )}
              </div>
              <button className="btn shrink-0" onClick={() => onPrepare(m)} disabled={preparing === m.job.id}>
                {preparing === m.job.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                Prepare application
              </button>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
