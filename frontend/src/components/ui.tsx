import { AlertTriangle, Loader2, WifiOff } from "lucide-react";
import type { ButtonHTMLAttributes, HTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import { forwardRef } from "react";
import { cn } from "../lib/cn";
import { CountUp } from "../lib/motion";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-2xl border border-white/[0.06] bg-surface-1", className)} {...props} />;
}

export function CardHeader({ title, subtitle, right, className }: { title: ReactNode; subtitle?: ReactNode; right?: ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-start justify-between gap-3 border-b border-white/5 px-5 py-3.5", className)}>
      <div className="min-w-0">
        <h2 className="text-sm font-semibold tracking-tight text-ink">{title}</h2>
        {subtitle && <p className="mt-0.5 text-xs text-ink-3">{subtitle}</p>}
      </div>
      {right && <div className="flex shrink-0 items-center gap-2">{right}</div>}
    </div>
  );
}

type Variant = "primary" | "secondary" | "ghost" | "danger" | "success";
const variants: Record<Variant, string> = {
  primary: "bg-gradient-to-b from-[#5aa8ff] to-[#2f7fe0] text-white border-white/10 shadow-[0_6px_20px_-6px_rgba(77,157,255,0.7)] hover:brightness-110",
  secondary: "bg-white/5 text-ink border-white/10 hover:bg-white/10",
  ghost: "bg-transparent text-ink-2 border-transparent hover:bg-white/5 hover:text-ink",
  danger: "bg-[#3a1717] text-[#f3b0b0] border-[#5a2323] hover:bg-[#4a1d1d]",
  success: "bg-[#12301a] text-[#9fe0a8] border-[#1f4a2a] hover:bg-[#173b21]",
};

export const Button = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md"; busy?: boolean }>(
  function Button({ className, variant = "secondary", size = "md", busy, disabled, children, ...props }, ref) {
    return (
      <button
        ref={ref}
        disabled={disabled || busy}
        className={cn(
          "inline-flex items-center justify-center gap-1.5 rounded-lg border font-medium transition-all duration-200 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent",
          size === "sm" ? "h-7 px-2.5 text-xs" : "h-9 px-3.5 text-sm",
          variants[variant],
          className,
        )}
        {...props}
      >
        {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />}
        {children}
      </button>
    );
  },
);

export function Badge({ className, children, title }: { className?: string; children: ReactNode; title?: string }) {
  return (
    <span title={title} className={cn("inline-flex items-center gap-1 whitespace-nowrap rounded-md border border-white/10 bg-white/5 px-1.5 py-0.5 text-2xs font-medium text-ink-2", className)}>
      {children}
    </span>
  );
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 p-4 text-sm text-ink-3" role="status">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> {label}
    </div>
  );
}

export function Empty({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-10 text-center">
      {icon && <div className="text-ink-3">{icon}</div>}
      <p className="text-sm font-medium text-ink-2">{title}</p>
      {children && <div className="max-w-md text-xs text-ink-3">{children}</div>}
    </div>
  );
}

export function ErrorBanner({ message, offline }: { message: string; offline?: boolean }) {
  return (
    <div role="alert" className="flex items-start gap-2 rounded-md border border-[#5a2323] bg-[#2a1414] px-3 py-2 text-sm text-[#f3b0b0]">
      {offline ? <WifiOff className="mt-0.5 h-4 w-4 shrink-0" /> : <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />}
      <span>{message}</span>
    </div>
  );
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "critical" | "warning" | "default" }) {
  return (
    <Card className={cn("glass-hover relative overflow-hidden px-4 py-3.5", tone === "critical" && "shadow-crit")}>
      <div
        aria-hidden
        className={cn(
          "pointer-events-none absolute -right-8 -top-8 h-24 w-24 rounded-full blur-2xl",
          tone === "critical" ? "bg-status-critical/25" : tone === "warning" ? "bg-status-warning/20" : "bg-accent/15",
        )}
      />
      <div className="relative text-2xs font-medium uppercase tracking-wider text-ink-3">{label}</div>
      <div
        className={cn(
          "relative mt-1.5 font-mono text-3xl font-semibold tabular-nums text-ink",
          tone === "critical" && "text-[#ff8f8f]",
          tone === "warning" && "text-[#ffd068]",
        )}
      >
        {typeof value === "number" ? <CountUp value={value} /> : value}
      </div>
      {hint && <div className="relative mt-1 text-2xs text-ink-3">{hint}</div>}
    </Card>
  );
}

export function FieldLabel({ children, htmlFor }: { children: ReactNode; htmlFor?: string }) {
  return (
    <label htmlFor={htmlFor} className="mb-1 block text-xs font-medium text-ink-2">
      {children}
    </label>
  );
}

const control = "w-full rounded-lg border border-white/10 bg-white/[0.04] px-3 text-sm text-ink placeholder:text-ink-3 transition-colors focus:border-accent focus:bg-white/[0.07] focus:outline-none focus:ring-2 focus:ring-accent/25";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...p }, ref) {
  return <input ref={ref} className={cn(control, "h-9", className)} {...p} />;
});

export function Select({ className, children, ...p }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cn(control, "h-9 pr-7", className)} {...p}>
      {children}
    </select>
  );
}

export function Textarea({ className, ...p }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn(control, "py-2 leading-relaxed", className)} {...p} />;
}

export function KV({ k, children, className }: { k: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={cn("grid grid-cols-[8.5rem_1fr] gap-2 py-1 text-sm", className)}>
      <dt className="text-ink-3">{k}</dt>
      <dd className="min-w-0 text-ink">{children}</dd>
    </div>
  );
}

export function Section({ title, children, right, className }: { title: ReactNode; children: ReactNode; right?: ReactNode; className?: string }) {
  return (
    <section className={cn("space-y-2", className)}>
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-3">{title}</h3>
        {right}
      </div>
      {children}
    </section>
  );
}

export function CountUpStat({ label, value, tone }: { label: string; value: number; tone?: "critical" | "warning" | "default" }) {
  return (
    <Card className={cn("relative overflow-hidden px-5 py-4", tone === "critical" && value > 0 && "shadow-crit")}>
      <div
        aria-hidden
        className={cn(
          "pointer-events-none absolute -right-10 -top-10 h-28 w-28 rounded-full blur-2xl",
          tone === "critical" ? "bg-status-critical/25" : tone === "warning" ? "bg-status-warning/20" : "bg-accent/15",
        )}
      />
      <div className="relative text-xs font-medium text-ink-3">{label}</div>
      <div className={cn("relative mt-1 font-mono text-4xl font-semibold tabular-nums", tone === "critical" ? "text-[#ff8f8f]" : tone === "warning" ? "text-[#ffd068]" : "text-ink")}>
        <CountUp value={value} />
      </div>
    </Card>
  );
}
