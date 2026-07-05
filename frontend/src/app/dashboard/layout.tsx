"use client";
import { type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clearToken } from "@/lib/api";
import { DashboardProvider, useDashboard } from "@/lib/dashboard-context";
import ApplicationDrawer from "@/components/ApplicationDrawer";
import { Clock, Compass, LayoutList, LogOut, Mail, MessagesSquare, Search, TriangleAlert } from "lucide-react";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Discover & Rank", icon: Search },
  { href: "/dashboard/followups", label: "Follow-ups Due", icon: Clock },
  { href: "/dashboard/applications", label: "Applications", icon: LayoutList },
  { href: "/dashboard/interview", label: "Interview Prep", icon: MessagesSquare },
];

function DashboardShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { gmail, onConnectGmail, followups, msg, msgUrl } = useDashboard();

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2 text-brand">
            <Compass /> <span className="font-bold">CareerPilot AI</span>
          </div>
          <div className="flex items-center gap-2">
            {gmail?.connected && (gmail.has_readonly_scope === false || gmail.has_calendar_scope === false) ? (
              <>
                <span
                  className="badge bg-amber-100 text-amber-800"
                  title={
                    gmail.has_readonly_scope === false
                      ? "This connection can create drafts but can't check Gmail for replies or confirm sends — reconnect to grant the missing permission."
                      : "This connection can't add interview times to your calendar yet — reconnect to grant calendar access."
                  }
                >
                  <TriangleAlert className="h-3.5 w-3.5" /> Gmail: limited permissions
                </span>
                <button className="btn-ghost" onClick={onConnectGmail}>
                  <Mail className="h-4 w-4" /> Reconnect Gmail
                </button>
              </>
            ) : gmail?.connected ? (
              <span className="badge bg-teal-100 text-teal-800">
                <Mail className="h-3.5 w-3.5" /> Gmail: {gmail.email || "connected"}
              </span>
            ) : (
              <button className="btn-ghost" onClick={onConnectGmail}>
                <Mail className="h-4 w-4" /> Connect Gmail
              </button>
            )}
            <button className="btn-ghost" onClick={() => { clearToken(); router.push("/"); }}>
              <LogOut className="h-4 w-4" /> Log out
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto flex max-w-7xl gap-6 px-4 py-6">
        <aside className="w-56 shrink-0">
          <nav className="card space-y-1 p-2">
            {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
              const activeItem = pathname === href;
              return (
                <Link
                  key={href}
                  href={href}
                  className={`flex items-center justify-between rounded-lg px-3 py-2 text-sm ${
                    activeItem ? "bg-brand text-white" : "text-slate-700 hover:bg-slate-100"
                  }`}
                >
                  <span className="flex items-center gap-2">
                    <Icon className="h-4 w-4" /> {label}
                  </span>
                  {href === "/dashboard/followups" && followups.length > 0 && (
                    <span className={`rounded-full px-1.5 text-xs ${
                      activeItem ? "bg-white/20" : "bg-amber-100 text-amber-800"
                    }`}>
                      {followups.length}
                    </span>
                  )}
                </Link>
              );
            })}
          </nav>
        </aside>

        <main className="min-w-0 flex-1 space-y-6">
          {msg && (
            <div className="flex flex-wrap items-center gap-2 rounded-lg bg-slate-100 px-4 py-2 text-sm text-slate-700">
              <span>{msg}</span>
              {msgUrl && (
                <a href={msgUrl} target="_blank" rel="noopener noreferrer"
                   className="font-medium text-indigo-600 underline hover:text-indigo-800">
                  Open in Gmail
                </a>
              )}
            </div>
          )}
          {children}
        </main>
      </div>

      <ApplicationDrawer />
    </div>
  );
}

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <DashboardProvider>
      <DashboardShell>{children}</DashboardShell>
    </DashboardProvider>
  );
}
