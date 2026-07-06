"use client";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  api, isAuthed,
  type Application, type ApplicationEvent, type Followup, type Profile,
} from "@/lib/api";

type GmailStatus = { connected: boolean; email?: string; has_readonly_scope?: boolean | null; has_calendar_scope?: boolean | null };

type DashboardState = {
  profile: Profile | null;
  setProfile: (p: Profile | null) => void;
  uploading: boolean;
  setUploading: (b: boolean) => void;

  applications: Application[];
  refreshApplications: () => void;

  followups: Followup[];
  refreshFollowups: () => void;
  followupBusy: string | null;
  onFollowupSave: (f: Followup) => Promise<void>;
  onFollowupDraftGmail: (f: Followup) => Promise<void>;

  gmail: GmailStatus | null;
  onConnectGmail: () => Promise<void>;

  active: Application | null;
  setActive: (a: Application | null) => void;
  history: ApplicationEvent[];
  drafting: boolean;
  onKeepAsDraft: () => Promise<void>;
  onApprove: () => Promise<void>;
  scheduleBusy: boolean;
  onConfirmSchedule: () => Promise<void>;
  onDismissSchedule: () => Promise<void>;

  // Jobs whose application was just saved/drafted — the Discover page uses
  // this to drop them from its local "Ranked matches" list without a refetch.
  approvedJobIds: string[];

  msg: string;
  setMsg: (s: string) => void;
  msgUrl: string | null;
};

const DashboardContext = createContext<DashboardState | null>(null);

export function useDashboard(): DashboardState {
  const ctx = useContext(DashboardContext);
  if (!ctx) throw new Error("useDashboard must be used within DashboardProvider");
  return ctx;
}

export function DashboardProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const pathname = usePathname();

  const [profile, setProfile] = useState<Profile | null>(null);
  const [uploading, setUploading] = useState(false);
  const [applications, setApplications] = useState<Application[]>([]);
  const [followups, setFollowups] = useState<Followup[]>([]);
  const [followupBusy, setFollowupBusy] = useState<string | null>(null);
  const [active, setActive] = useState<Application | null>(null);
  const [history, setHistory] = useState<ApplicationEvent[]>([]);
  const [msg, setMsg] = useState("");
  const [msgUrl, setMsgUrl] = useState<string | null>(null);
  const [gmail, setGmail] = useState<GmailStatus | null>(null);
  const [drafting, setDrafting] = useState(false);
  const [approvedJobIds, setApprovedJobIds] = useState<string[]>([]);
  const [scheduleBusy, setScheduleBusy] = useState(false);

  useEffect(() => {
    if (!msg) return;
    // Link messages (e.g. "Open in Gmail") get longer to notice and click,
    // but must still clear eventually — otherwise they stick on every page
    // indefinitely, same bug as the plain-text messages had before.
    const t = setTimeout(() => setMsg(""), msgUrl ? 30000 : 5000);
    return () => clearTimeout(t);
  }, [msg, msgUrl]);

  // A status message belongs to the page it was created on (e.g. "Draft
  // created" on Applications, or a follow-up draft on Follow-ups) — it
  // shouldn't follow the user to unrelated pages like Interview Prep.
  useEffect(() => {
    setMsg("");
    setMsgUrl(null);
  }, [pathname]);

  function refreshApplications() {
    api.applications().then(setApplications).catch(() => {});
  }

  function refreshFollowups() {
    api.followupsDue().then(setFollowups).catch(() => {});
  }

  useEffect(() => {
    if (!isAuthed()) { router.push("/"); return; }
    api.profile().then(setProfile).catch(() => {});
    api.googleStatus().then(setGmail).catch(() => {});
    refreshApplications();
    refreshFollowups();
    if (searchParams.get("gmail_connected")) {
      setMsg("Gmail connected. Cover letters can now be saved as Gmail drafts.");
    }
  }, [router, searchParams]);

  useEffect(() => {
    if (!active) { setHistory([]); return; }
    api.applicationHistory(active.id).then(setHistory).catch(() => setHistory([]));
  }, [active?.id]);

  async function onFollowupSave(f: Followup) {
    setFollowupBusy(f.application_id); setMsg(""); setMsgUrl(null);
    try {
      await api.followupSave(f.application_id);
      setMsg("Follow-up saved for later.");
      setFollowups((prev) => prev.filter((x) => x.application_id !== f.application_id));
      refreshApplications();
    } catch (e: any) { setMsg(e.message); }
    finally { setFollowupBusy(null); }
  }

  async function onFollowupDraftGmail(f: Followup) {
    setFollowupBusy(f.application_id); setMsg(""); setMsgUrl(null);
    try {
      const res = await api.followupDraftGmail(f.application_id);
      setMsg(res.threaded
        ? "Follow-up drafted in Gmail, in the same thread as your original application."
        : "Follow-up drafted in Gmail as a new email (the original wasn't sent via a Gmail draft, so it couldn't be threaded).");
      setMsgUrl(res.url ?? null);
      setFollowups((prev) => prev.filter((x) => x.application_id !== f.application_id));
      refreshApplications();
    } catch (e: any) { setMsg(e.message); }
    finally { setFollowupBusy(null); }
  }

  async function onConnectGmail() {
    try {
      const { url } = await api.googleAuthorize();
      window.location.href = url;
    } catch (e: any) { setMsg(e.message); }
  }

  async function onKeepAsDraft() {
    if (!active) return;
    if (!gmail?.connected) {
      setActive(null);
      setMsg("Saved locally. Connect Gmail to also save drafts straight to your inbox.");
      setMsgUrl(null);
      return;
    }
    setDrafting(true); setMsg(""); setMsgUrl(null);
    try {
      const res = await api.draftGmail(active.id);
      setMsg("Draft created in your Gmail account — review and send it from there whenever you're ready.");
      setMsgUrl(res.url ?? null);
    } catch (e: any) {
      setMsg(`Saved locally, but couldn't create the Gmail draft: ${e.message}`);
    } finally {
      setDrafting(false);
      setActive(null);
    }
  }

  async function onApprove() {
    if (!active) return;
    const app = await api.approve(active.id);
    setActive(app);
    refreshApplications();
    setApprovedJobIds((prev) => [...prev, app.job_id]);
  }

  async function onConfirmSchedule() {
    if (!active) return;
    setScheduleBusy(true); setMsg("");
    try {
      const app = await api.confirmInterviewSchedule(active.id);
      setActive(app);
      setMsg("Added to your Google Calendar.");
      refreshApplications();
    } catch (e: any) { setMsg(e.message); }
    finally { setScheduleBusy(false); }
  }

  async function onDismissSchedule() {
    if (!active) return;
    setScheduleBusy(true); setMsg("");
    try {
      const app = await api.dismissInterviewSchedule(active.id);
      setActive(app);
      refreshApplications();
    } catch (e: any) { setMsg(e.message); }
    finally { setScheduleBusy(false); }
  }

  return (
    <DashboardContext.Provider value={{
      profile, setProfile, uploading, setUploading,
      applications, refreshApplications,
      followups, refreshFollowups, followupBusy, onFollowupSave, onFollowupDraftGmail,
      gmail, onConnectGmail,
      active, setActive, history, drafting, onKeepAsDraft, onApprove,
      scheduleBusy, onConfirmSchedule, onDismissSchedule,
      approvedJobIds,
      msg, setMsg, msgUrl,
    }}>
      {children}
    </DashboardContext.Provider>
  );
}
