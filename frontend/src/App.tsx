import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import {
  ChevronsLeft,
  ChevronsRight,
  ClipboardCheck,
  CornerDownLeft,
  FlaskConical,
  Inbox,
  Keyboard,
  LayoutDashboard,
  Mic,
  Moon,
  Search,
  Settings as SettingsIcon,
  Sun,
  WifiOff,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api } from "./lib/api";
import { cn } from "./lib/cn";
import { useI18n, I18nProvider, type Locale } from './lib/i18n';
import { EASE, pageVariants } from "./lib/motion";
import { usePoll } from "./lib/usePoll";
import { useIncidentAlerts } from "./lib/alerts";
import { AlertToasts } from "./components/AlertToasts";
import { CommandCenter } from "./pages/CommandCenter";
import { JourneyPage } from "./pages/Journey";
import { Evaluation } from "./pages/Evaluation";
import { IncidentInvestigation } from "./pages/IncidentInvestigation";
import { Reports } from "./pages/Reports";
import { Review } from "./pages/Review";
import { Settings } from "./pages/Settings";
import { LimitationsPage } from "./pages/Limitations";

function useTheme() {
  const [dark, setDark] = useState(() => {
    try { return localStorage.getItem("aa.theme") !== "light"; } catch { return true; }
  });
  useEffect(() => {
    document.documentElement.classList.toggle("light", !dark);
    const meta = document.getElementById("meta-theme-color");
    if (meta) meta.setAttribute("content", dark ? "#07080b" : "#f8f9fb");
    try { localStorage.setItem("aa.theme", dark ? "dark" : "light"); } catch { /* noop */ }
  }, [dark]);
  return { dark, toggle: () => setDark((v) => !v) };
}

const SHORTCUTS: { keys: string; desc: string }[] = [
  { keys: "Ctrl K", desc: "Open command palette" },
  { keys: "?", desc: "Show keyboard shortcuts" },
  { keys: "↑ / ↓", desc: "Navigate command palette results" },
  { keys: "Enter", desc: "Select result" },
  { keys: "Esc", desc: "Close modal / palette" },
];

function ShortcutsModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[3000] flex items-center justify-center bg-black/60 px-4 backdrop-blur-sm"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          onMouseDown={onClose}
        >
          <motion.div
            role="dialog" aria-label="Keyboard shortcuts"
            className="glass w-full max-w-sm overflow-hidden rounded-2xl shadow-glow"
            initial={{ opacity: 0, y: -12, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }}
            transition={{ duration: 0.2 }}
            onMouseDown={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-white/5 px-5 py-4">
              <div className="flex items-center gap-2">
                <Keyboard className="h-4 w-4 text-accent-glow" />
                <span className="text-sm font-semibold text-ink">Keyboard Shortcuts</span>
              </div>
              <button onClick={onClose} className="rounded p-1 text-ink-3 hover:text-ink" aria-label="Close">
                <X className="h-4 w-4" />
              </button>
            </div>
            <ul className="divide-y divide-white/5 px-5 py-2">
              {SHORTCUTS.map((s) => (
                <li key={s.keys} className="flex items-center justify-between py-2.5">
                  <span className="text-sm text-ink-2">{s.desc}</span>
                  <kbd className="rounded border border-white/10 bg-white/5 px-2 py-0.5 font-mono text-xs text-ink-3">{s.keys}</kbd>
                </li>
              ))}
            </ul>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

const NAV = [
  { to: "/", label: "New call", hint: "Drop a voice note and watch it unfold", icon: Mic, end: true, group: "main" },
  { to: "/live", label: "Live situation", hint: "Globe, alerts and what needs attention", icon: LayoutDashboard, group: "main" },
  { to: "/review", label: "To review", hint: "Check, correct and merge", icon: ClipboardCheck, group: "main" },
  { to: "/reports", label: "All reports", hint: "Every report, with search", icon: Inbox, group: "more" },
  { to: "/incidents", label: "Incident details", hint: "Everything about one incident", icon: Search, group: "more" },
  { to: "/evaluation", label: "Accuracy", hint: "How well the system performs", icon: FlaskConical, group: "more" },
  { to: "/settings", label: "Settings", hint: "Thresholds and providers", icon: SettingsIcon, group: "more" },
];

function useOnline() {
  const [online, setOnline] = useState(typeof navigator === "undefined" ? true : navigator.onLine);
  useEffect(() => {
    const up = () => setOnline(true);
    const down = () => setOnline(false);
    window.addEventListener("online", up);
    window.addEventListener("offline", down);
    return () => {
      window.removeEventListener("online", up);
      window.removeEventListener("offline", down);
    };
  }, []);
  return online;
}

function ConnectionPill({ collapsed }: { collapsed: boolean }) {
  const health = usePoll(api.health, 10000);
  const online = useOnline();
  const stt = health.data?.providers.speech_to_text;
  const apiDown = !!health.error;
  const tone = apiDown ? "bad" : !online ? "offline" : "good";
  const text = apiDown
    ? "Backend unreachable"
    : !online
      ? "Offline mode · local data"
      : `STT ${stt?.mode === "real" ? "Gnani Prisma" : stt?.mode === "mock" ? "mock" : (stt?.mode ?? "…")}`;
  return (
    <div
      className="flex items-center gap-2 rounded-xl border border-white/5 bg-white/[0.03] px-3 py-2 text-xs text-ink-2"
      title="Backend health, network state and active speech-to-text provider"
    >
      <span className="relative flex h-2.5 w-2.5 shrink-0">
        {tone === "good" && <span className="absolute inline-flex h-full w-full animate-pulse-ring rounded-full bg-status-good" />}
        <span
          className={cn(
            "relative inline-flex h-2.5 w-2.5 rounded-full",
            tone === "good" && "bg-status-good",
            tone === "offline" && "bg-status-warning",
            tone === "bad" && "bg-status-critical",
          )}
        />
      </span>
      {!collapsed && <span className="truncate">{text}</span>}
      {!collapsed && tone === "offline" && <WifiOff className="ml-auto h-3.5 w-3.5 text-status-warning" aria-hidden />}
    </div>
  );
}

function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [idx, setIdx] = useState(0);
  const results = useMemo(() => {
    const t = q.trim().toLowerCase();
    const pages = NAV.filter((n) => !t || `${n.label} ${n.hint}`.toLowerCase().includes(t)).map((n) => ({
      key: n.to,
      title: n.label,
      sub: n.hint,
      icon: n.icon,
      go: n.to,
    }));
    const m = t.match(/^(inc|rep)[-\s]?(\w+)$/i);
    if (m) {
      const id = t.toUpperCase().replace(/\s/g, "-");
      pages.unshift(
        m[1].toLowerCase() === "inc"
          ? { key: id, title: `Open incident ${id}`, sub: "Jump straight to investigation", icon: Search, go: `/incidents/${id}` }
          : { key: id, title: `Find report ${id}`, sub: "Search incoming reports", icon: Inbox, go: `/reports?q=${id}` },
      );
    }
    return pages;
  }, [q]);

  useEffect(() => {
    if (open) {
      setQ("");
      setIdx(0);
    }
  }, [open]);
  useEffect(() => setIdx(0), [q]);

  const choose = (i: number) => {
    const r = results[i];
    if (!r) return;
    nav(r.go);
    onClose();
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[3000] flex items-start justify-center bg-black/60 px-4 pt-[14vh] backdrop-blur-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onMouseDown={onClose}
        >
          <motion.div
            role="dialog"
            aria-label="Command palette"
            className="glass w-full max-w-xl overflow-hidden rounded-2xl shadow-glow"
            initial={{ opacity: 0, y: -12, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }}
            transition={{ duration: 0.2, ease: EASE }}
            onMouseDown={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3 border-b border-white/5 px-4">
              <Search className="h-4 w-4 text-ink-3" aria-hidden />
              <input
                autoFocus
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "ArrowDown") {
                    e.preventDefault();
                    setIdx((i) => Math.min(i + 1, results.length - 1));
                  } else if (e.key === "ArrowUp") {
                    e.preventDefault();
                    setIdx((i) => Math.max(i - 1, 0));
                  } else if (e.key === "Enter") choose(idx);
                  else if (e.key === "Escape") onClose();
                }}
                placeholder="Go to a page, or type an incident id (INC-001)…"
                className="h-14 w-full bg-transparent text-sm text-ink placeholder:text-ink-3 focus:outline-none"
              />
              <kbd className="rounded border border-white/10 px-1.5 py-0.5 font-mono text-2xs text-ink-3">esc</kbd>
            </div>
            <ul className="max-h-80 overflow-y-auto p-2">
              {results.length === 0 && <li className="px-3 py-6 text-center text-sm text-ink-3">Nothing matches “{q}”.</li>}
              {results.map((r, i) => (
                <li key={r.key}>
                  <button
                    onMouseEnter={() => setIdx(i)}
                    onClick={() => choose(i)}
                    className={cn("flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left", i === idx ? "bg-white/[0.07]" : "")}
                  >
                    <span className="grid h-8 w-8 place-items-center rounded-lg bg-white/5 text-accent-glow">
                      <r.icon className="h-4 w-4" aria-hidden />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm text-ink">{r.title}</span>
                      <span className="block truncate text-xs text-ink-3">{r.sub}</span>
                    </span>
                    {i === idx && <CornerDownLeft className="h-3.5 w-3.5 text-ink-3" aria-hidden />}
                  </button>
                </li>
              ))}
            </ul>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function LangToggle({ collapsed }: { collapsed: boolean }) {
  const { locale, setLocale } = useI18n();
  const langs: { code: Locale; label: string }[] = [
    { code: "en", label: "EN" },
    { code: "hi", label: "हिं" },
    { code: "mr", label: "मर" },
  ];
  if (collapsed) return null;
  return (
    <div className="flex gap-1 rounded-xl border border-white/5 bg-white/[0.03] p-1" role="group" aria-label="Interface language">
      {langs.map(({ code, label: lbl }) => (
        <button
          key={code}
          onClick={() => setLocale(code)}
          className={cn(
            "flex-1 rounded-lg py-1 text-xs font-medium transition-colors",
            locale === code
              ? "bg-accent/20 text-accent-glow"
              : "text-ink-3 hover:text-ink",
          )}
          aria-pressed={locale === code}
        >
          {lbl}
        </button>
      ))}
    </div>
  );
}

function Sidebar({ collapsed, setCollapsed, openPalette, openShortcuts, dark, toggleTheme }: { collapsed: boolean; setCollapsed: (v: boolean) => void; openPalette: () => void; openShortcuts: () => void; dark: boolean; toggleTheme: () => void }) {
  const stats = usePoll(api.stats, 5000);
  const badges: Record<string, number> = {
    "/review": (stats.data?.incidents_needing_review ?? 0) + (stats.data?.possible_duplicates_pending ?? 0),
  };
  return (
    <motion.aside
      animate={{ width: collapsed ? 76 : 264 }}
      transition={{ duration: 0.3, ease: EASE }}
      className="sticky top-0 z-[1000] hidden h-screen shrink-0 flex-col border-r border-white/5 bg-bg/60 px-3 py-4 backdrop-blur-xl md:flex"
    >
      <div className="flex items-center gap-3 px-2 pb-5">
        <div className="relative grid h-10 w-10 shrink-0 place-items-center rounded-full border border-white/10 bg-[#0e1014] shadow-[0_0_0_1px_rgba(255,255,255,0.06)]">
          <Mic className="h-[18px] w-[18px] text-[#ff6b4a]" aria-hidden />
          <span className="absolute inset-0 animate-pulse-ring rounded-full border border-[#ff6b4a]/30" />
        </div>
        {!collapsed && (
          <div className="min-w-0">
            <div className="text-sm font-semibold leading-tight tracking-tight text-white">Aapda Awaaz</div>
            <div className="truncate text-2xs text-ink-3" lang="hi">आपदा आवाज़ · Disaster Voice</div>
          </div>
        )}
      </div>

      <button
        onClick={openPalette}
        className="mb-4 flex h-10 items-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-3 text-sm text-ink-3 transition-colors hover:bg-white/[0.07] hover:text-ink"
        aria-label="Open command palette"
      >
        <Search className="h-4 w-4 shrink-0" aria-hidden />
        {!collapsed && (
          <>
            <span className="flex-1 text-left">Jump to…</span>
            <kbd className="rounded border border-white/10 px-1.5 py-0.5 font-mono text-2xs">Ctrl K</kbd>
          </>
        )}
      </button>

      <nav className="flex flex-1 flex-col gap-1" aria-label="Main">
        <LayoutGroup id="nav">
          {NAV.filter((n) => n.group === "main").map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} title={collapsed ? n.label : undefined} className="relative block rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-accent/50">
              {({ isActive }) => (
                <div className={cn("relative flex h-11 items-center gap-3 rounded-xl px-3 text-sm transition-colors", isActive ? "text-ink" : "text-ink-3 hover:bg-white/[0.04] hover:text-ink")}>
                  {isActive && (
                    <motion.span
                      layoutId="nav-active"
                      className="absolute inset-0 rounded-xl border border-white/10 bg-gradient-to-r from-accent/20 to-white/[0.03]"
                      transition={{ type: "spring", stiffness: 380, damping: 32 }}
                    />
                  )}
                  {isActive && <motion.span layoutId="nav-bar" className="absolute -left-3 h-6 w-1 rounded-r-full bg-accent shadow-[0_0_12px_2px_rgba(77,157,255,0.8)]" />}
                  <n.icon className={cn("relative h-[18px] w-[18px] shrink-0", isActive && "text-accent-glow")} aria-hidden />
                  {!collapsed && <span className="relative truncate">{n.label}</span>}
                  {!!badges[n.to] && (
                    <span className={cn("relative ml-auto rounded-full bg-status-critical px-1.5 py-0.5 font-mono text-2xs font-semibold leading-none text-white", collapsed && "absolute right-1 top-1 ml-0")}>
                      {badges[n.to]}
                    </span>
                  )}
                </div>
              )}
            </NavLink>
          ))}
          {!collapsed && <div className="mb-1 mt-5 px-3 text-2xs font-medium uppercase tracking-[0.16em] text-ink-3/70">More</div>}
          {collapsed && <div className="my-3 h-px bg-white/5" />}
          {NAV.filter((n) => n.group === "more").map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} title={collapsed ? n.label : undefined} className="relative block rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-accent/50">
              {({ isActive }) => (
                <div className={cn("relative flex h-11 items-center gap-3 rounded-xl px-3 text-sm transition-colors", isActive ? "text-ink" : "text-ink-3 hover:bg-white/[0.04] hover:text-ink")}>
                  {isActive && (
                    <motion.span
                      layoutId="nav-active"
                      className="absolute inset-0 rounded-xl border border-white/10 bg-gradient-to-r from-accent/20 to-white/[0.03]"
                      transition={{ type: "spring", stiffness: 380, damping: 32 }}
                    />
                  )}
                  {isActive && <motion.span layoutId="nav-bar" className="absolute -left-3 h-6 w-1 rounded-r-full bg-accent shadow-[0_0_12px_2px_rgba(77,157,255,0.8)]" />}
                  <n.icon className={cn("relative h-[18px] w-[18px] shrink-0", isActive && "text-accent-glow")} aria-hidden />
                  {!collapsed && <span className="relative truncate">{n.label}</span>}
                  {!!badges[n.to] && (
                    <span className={cn("relative ml-auto rounded-full bg-status-critical px-1.5 py-0.5 font-mono text-2xs font-semibold leading-none text-white", collapsed && "absolute right-1 top-1 ml-0")}>
                      {badges[n.to]}
                    </span>
                  )}
                </div>
              )}
            </NavLink>
          ))}
        </LayoutGroup>
      </nav>

      <div className="space-y-2">
        <LangToggle collapsed={collapsed} />
        <ConnectionPill collapsed={collapsed} />
        <div className={cn("flex gap-1", collapsed ? "flex-col" : "")}>
          <button
            onClick={toggleTheme}
            className="flex h-9 flex-1 items-center justify-center gap-2 rounded-xl text-xs text-ink-3 transition-colors hover:bg-white/5 hover:text-ink"
            aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
            title={dark ? "Light mode" : "Dark mode"}
          >
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            {!collapsed && <span>{dark ? "Light" : "Dark"}</span>}
          </button>
          <button
            onClick={openShortcuts}
            className="flex h-9 flex-1 items-center justify-center gap-2 rounded-xl text-xs text-ink-3 transition-colors hover:bg-white/5 hover:text-ink"
            aria-label="Keyboard shortcuts"
            title="Keyboard shortcuts (?)"
          >
            <Keyboard className="h-4 w-4" />
            {!collapsed && <span>Shortcuts</span>}
          </button>
        </div>
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="flex h-9 w-full items-center justify-center gap-2 rounded-xl text-xs text-ink-3 transition-colors hover:bg-white/5 hover:text-ink"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <ChevronsRight className="h-4 w-4" /> : <><ChevronsLeft className="h-4 w-4" /> Collapse</>}
        </button>
      </div>
    </motion.aside>
  );
}

function MobileNav() {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-[1000] flex justify-around border-t border-white/10 bg-bg/90 px-1 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl md:hidden" aria-label="Main">
      {NAV.filter((n) => n.group === "main" || n.to === "/settings").map((n) => (
        <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => cn("flex flex-1 flex-col items-center gap-0.5 py-2 text-[10px]", isActive ? "text-accent-glow" : "text-ink-3")}>
          <n.icon className="h-5 w-5" aria-hidden />
          {n.label.split(" ")[0]}
        </NavLink>
      ))}
    </nav>
  );
}

export default function App() {
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem("aa.sidebar") === "1";
    } catch {
      return false;
    }
  });
  const [palette, setPalette] = useState(false);
  const [shortcuts, setShortcuts] = useState(false);
  const { dark, toggle: toggleTheme } = useTheme();
  const navigate = useNavigate();
  const urgent = usePoll(() => api.incidents({ priority: "critical,high", limit: 100 }), 3000);
  const { alerts, dismiss } = useIncidentAlerts(urgent.data?.items);
  const setSidebar = useCallback((v: boolean) => {
    setCollapsed(v);
    try {
      localStorage.setItem("aa.sidebar", v ? "1" : "0");
    } catch {
      /* storage unavailable */
    }
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      const isInput = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette((v) => !v);
      } else if (e.key === "?" && !isInput && !e.ctrlKey && !e.metaKey) {
        setShortcuts((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const section = "/" + (location.pathname.split("/")[1] ?? "");

  return (
    <I18nProvider>
      <>
      <div className="ambient" aria-hidden>
        <div className="ambient-grid" />
        <div className="ambient-scan" />
      </div>
      <div className="flex min-h-full">
        <Sidebar collapsed={collapsed} setCollapsed={setSidebar} openPalette={() => setPalette(true)} openShortcuts={() => setShortcuts(true)} dark={dark} toggleTheme={toggleTheme} />
        <div className="flex min-w-0 flex-1 flex-col pb-16 md:pb-0">
          <div className="border-b border-[#fab219]/20 bg-[#fab219]/[0.06] px-4 py-1.5 text-center text-2xs text-[#fab219]/80 backdrop-blur">
            SIMULATION — synthetic data · fictional places · does not dispatch responders or contact emergency services ·{" "}
            <a href="/limitations" className="underline hover:text-[#fab219]">Known Limitations</a>
          </div>
          <main className="mx-auto w-full max-w-[1800px] flex-1 px-4 py-6 md:px-8">
            <>
              <motion.div key={section} variants={pageVariants} initial="initial" animate="enter">
                <Routes location={location}>
                  <Route path="/" element={<JourneyPage />} />
                  <Route path="/live" element={<CommandCenter />} />
                  <Route path="/reports" element={<Reports />} />
                  <Route path="/incidents" element={<IncidentInvestigation />} />
                  <Route path="/incidents/:id" element={<IncidentInvestigation />} />
                  <Route path="/review" element={<Review />} />
                  <Route path="/evaluation" element={<Evaluation />} />
                  <Route path="/settings" element={<Settings />} />
                  <Route path="/limitations" element={<LimitationsPage />} />
                  <Route path="*" element={<p className="text-sm text-ink-3">Page not found.</p>} />
                </Routes>
              </motion.div>
            </>
          </main>
        </div>
      </div>
      <AlertToasts
        alerts={alerts}
        onDismiss={dismiss}
        onOpen={(a) => {
          dismiss(a.key);
          navigate(`/live?focus=${a.incidentId}`);
        }}
      />
      <MobileNav />
      <CommandPalette open={palette} onClose={() => setPalette(false)} />
      <ShortcutsModal open={shortcuts} onClose={() => setShortcuts(false)} />
      </>
    </I18nProvider>
  );
}
