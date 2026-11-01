import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import {
  ChevronsLeft,
  ChevronsRight,
  CornerDownLeft,
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
  { to: "/", label: "New Call", hint: "Record a voice report and process it", icon: Mic, end: true },
  { to: "/live", label: "Situation Room", hint: "Live map, alerts and active incidents", icon: LayoutDashboard },
  { to: "/settings", label: "Settings", hint: "API providers and thresholds", icon: SettingsIcon },
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
          ? { key: id, title: `Open incident ${id}`, sub: "Jump to incident investigation", icon: Search, go: `/incidents/${id}` }
          : { key: id, title: `Find report ${id}`, sub: "Search reports", icon: Search, go: `/reports?q=${id}` },
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

function GnaniLogo({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="1.5" opacity="0.4" />
      <path d="M7 12c0-2.76 2.24-5 5-5s5 2.24 5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <circle cx="12" cy="14" r="2" fill="currentColor" />
    </svg>
  );
}

function Sidebar({ collapsed, setCollapsed, openShortcuts, dark, toggleTheme }: { collapsed: boolean; setCollapsed: (v: boolean) => void; openShortcuts: () => void; dark: boolean; toggleTheme: () => void }) {
  const stats = usePoll(api.stats, 5000);
  const reviewCount = (stats.data?.incidents_needing_review ?? 0) + (stats.data?.possible_duplicates_pending ?? 0);
  const badges: Record<string, number> = { "/live": reviewCount };

  return (
    <motion.aside
      animate={{ width: collapsed ? 72 : 240 }}
      transition={{ duration: 0.25, ease: EASE }}
      className="sticky top-0 z-[1000] hidden h-screen shrink-0 flex-col border-r border-white/5 bg-bg/60 px-3 py-5 backdrop-blur-xl md:flex"
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-1 pb-6">
        <div className="relative grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-[#ff6b4a]/20 bg-[#ff6b4a]/10">
          <Mic className="h-4 w-4 text-[#ff6b4a]" aria-hidden />
        </div>
        {!collapsed && (
          <div className="min-w-0">
            <div className="text-sm font-semibold leading-tight tracking-tight text-white">Aapda Awaaz</div>
            <div className="mt-0.5 flex items-center gap-1 text-2xs text-ink-3">
              <GnaniLogo size={10} />
              <span>Gnani AI</span>
            </div>
          </div>
        )}
      </div>

      <nav className="flex flex-1 flex-col gap-0.5" aria-label="Main">
        <LayoutGroup id="nav">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} title={collapsed ? n.label : undefined} className="relative block rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-accent/50">
              {({ isActive }) => (
                <div className={cn("relative flex h-10 items-center gap-3 rounded-xl px-3 text-sm transition-colors", isActive ? "text-ink" : "text-ink-3 hover:bg-white/[0.04] hover:text-ink")}>
                  {isActive && (
                    <motion.span
                      layoutId="nav-active"
                      className="absolute inset-0 rounded-xl bg-white/[0.06]"
                      transition={{ type: "spring", stiffness: 400, damping: 34 }}
                    />
                  )}
                  {isActive && <motion.span layoutId="nav-bar" className="absolute -left-3 h-5 w-0.5 rounded-r-full bg-accent" />}
                  <n.icon className={cn("relative h-4 w-4 shrink-0", isActive ? "text-accent-glow" : "")} aria-hidden />
                  {!collapsed && <span className="relative flex-1 truncate text-[13px]">{n.label}</span>}
                  {!!badges[n.to] && (
                    <span className={cn("relative rounded-full bg-status-critical px-1.5 py-0.5 font-mono text-2xs font-semibold leading-none text-white", collapsed && "absolute right-1 top-1")}>
                      {badges[n.to]}
                    </span>
                  )}
                </div>
              )}
            </NavLink>
          ))}
        </LayoutGroup>
      </nav>

      <div className="space-y-3">
        {/* Gnani model indicators */}
        {!collapsed && (
          <div className="rounded-xl border border-white/5 bg-white/[0.02] px-3 py-2.5 space-y-1.5">
            <div className="text-2xs font-medium uppercase tracking-[0.14em] text-ink-3/60">Gnani AI Models</div>
            <div className="flex items-center gap-2 text-2xs text-ink-2">
              <span className="h-1.5 w-1.5 rounded-full bg-status-good shrink-0" />
              <span>Prisma v2.5 · STT</span>
            </div>
            <div className="flex items-center gap-2 text-2xs text-ink-2">
              <span className="h-1.5 w-1.5 rounded-full bg-status-good shrink-0" />
              <span>Timbre v2.5 · TTS</span>
            </div>
            <div className="flex items-center gap-2 text-2xs text-ink-2">
              <span className="h-1.5 w-1.5 rounded-full bg-accent/70 shrink-0" />
              <span>Evon v3.3 · Extraction</span>
            </div>
          </div>
        )}
        <LangToggle collapsed={collapsed} />
        <ConnectionPill collapsed={collapsed} />
        <div className="flex gap-1">
          <button
            onClick={toggleTheme}
            className="flex h-8 flex-1 items-center justify-center gap-1.5 rounded-lg text-2xs text-ink-3 transition-colors hover:bg-white/5 hover:text-ink"
            aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
          >
            {dark ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
            {!collapsed && <span>{dark ? "Light" : "Dark"}</span>}
          </button>
          <button
            onClick={openShortcuts}
            className="flex h-8 flex-1 items-center justify-center gap-1.5 rounded-lg text-2xs text-ink-3 transition-colors hover:bg-white/5 hover:text-ink"
            aria-label="Keyboard shortcuts"
            title="?"
          >
            <Keyboard className="h-3.5 w-3.5" />
            {!collapsed && <span>Keys</span>}
          </button>
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-ink-3 transition-colors hover:bg-white/5 hover:text-ink"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? <ChevronsRight className="h-3.5 w-3.5" /> : <ChevronsLeft className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>
    </motion.aside>
  );
}

function MobileNav() {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-[1000] flex justify-around border-t border-white/[0.06] bg-bg/90 px-1 pb-[env(safe-area-inset-bottom)] pt-1 backdrop-blur-xl md:hidden" aria-label="Main">
      {NAV.map((n) => (
        <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => cn("flex flex-1 flex-col items-center gap-1 py-2 text-[10px]", isActive ? "text-accent-glow" : "text-ink-3")}>
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
        <Sidebar collapsed={collapsed} setCollapsed={setSidebar} openShortcuts={() => setShortcuts(true)} dark={dark} toggleTheme={toggleTheme} />
        <div className="flex min-w-0 flex-1 flex-col pb-16 md:pb-0">
          <div className="flex items-center justify-center gap-2 border-b border-white/[0.04] px-4 py-1.5 text-2xs text-ink-3/50">
            <span>Demo · synthetic data</span>
            <span aria-hidden>·</span>
            <span>Built on Gnani AI Prisma · Timbre · Evon</span>
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
