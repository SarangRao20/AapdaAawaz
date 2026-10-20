import { AlertOctagon, AlertTriangle, BadgeCheck, Bot, CircleDot, FlaskConical, HelpCircle, MapPin, MapPinOff, ShieldCheck, ShieldQuestion, User } from "lucide-react";
import { cn } from "../lib/cn";
import { PRIORITY_COLOR, label } from "../lib/format";
import type { LocationStatus, Priority, ReviewStatus } from "../lib/types";
import { Badge } from "./ui";

const PRIORITY_ICON = { critical: AlertOctagon, high: AlertTriangle, medium: CircleDot, low: CircleDot };

/** Priority is a status colour, so it always ships with an icon and a text label. */
export function PriorityBadge({ value, score, className }: { value: Priority; score?: number; className?: string }) {
  const Icon = PRIORITY_ICON[value];
  return (
    <span
      className={cn("inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-2xs font-semibold uppercase tracking-wide", className)}
      style={{ color: PRIORITY_COLOR[value], background: `${PRIORITY_COLOR[value]}1f`, border: `1px solid ${PRIORITY_COLOR[value]}55` }}
    >
      <Icon className="h-3 w-3" aria-hidden />
      {value}
      {score !== undefined && <span className="font-mono font-normal opacity-80">{score.toFixed(0)}</span>}
    </span>
  );
}

export function ReviewBadge({ value }: { value: ReviewStatus }) {
  const map: Record<ReviewStatus, [string, typeof ShieldCheck]> = {
    needs_review: ["border-[#5b4413] text-[#f6c75a]", ShieldQuestion],
    rereview_needed: ["border-[#5b4413] text-[#f6c75a]", ShieldQuestion],
    reviewed: ["border-[#1f4a2a] text-[#9fe0a8]", ShieldCheck],
    no_review_required: ["border-line text-ink-3", ShieldCheck],
  };
  const [cls, Icon] = map[value];
  return (
    <Badge className={cls}>
      <Icon className="h-3 w-3" aria-hidden />
      {label(value)}
    </Badge>
  );
}

export function LocationBadge({ value }: { value: LocationStatus }) {
  if (value === "human_verified")
    return (
      <Badge className="border-[#1f4a2a] text-[#9fe0a8]" title="Location confirmed by a dispatcher">
        <BadgeCheck className="h-3 w-3" aria-hidden /> Verified location
      </Badge>
    );
  if (value === "simulated_reference")
    return (
      <Badge title="Matched to a SIMULATED reference village; the point is the village reference, not the exact spot. Not verified.">
        <MapPin className="h-3 w-3" aria-hidden /> Reference match · unverified
      </Badge>
    );
  return (
    <Badge className="border-[#5b4413] text-[#f6c75a]" title="No reliable coordinates — not shown on the map">
      <MapPinOff className="h-3 w-3" aria-hidden /> {label(value)}
    </Badge>
  );
}

/** Where a value came from: real provider, mock, authored fixture, rule engine or a human. */
export function ModeBadge({ mode, provider }: { mode: string | null | undefined; provider?: string | null }) {
  const m = mode ?? "none";
  const styles: Record<string, [string, typeof Bot, string]> = {
    real: ["border-[#1c3f6b] text-[#8fc0f5]", Bot, "Real provider output"],
    mock: ["border-[#5b4413] text-[#f6c75a]", FlaskConical, "MOCK — not real model output"],
    fixture: ["border-line text-ink-2", FlaskConical, "Synthetic fixture text (not ASR)"],
    rule_based: ["border-line text-ink-2", CircleDot, "Deterministic rules"],
    human: ["border-[#1f4a2a] text-[#9fe0a8]", User, "Entered by a human"],
    template: ["border-line text-ink-2", CircleDot, "Fixed template"],
    none: ["border-line text-ink-3", HelpCircle, "No transcript yet"],
    unavailable: ["border-line text-ink-3", HelpCircle, "Unavailable"],
  };
  const [cls, Icon, text] = styles[m] ?? styles.none;
  return (
    <Badge className={cls} title={provider ?? undefined}>
      <Icon className="h-3 w-3" aria-hidden />
      {text}
    </Badge>
  );
}

export function ConfidenceBadge({ value }: { value: "high" | "medium" | "low" | undefined }) {
  if (!value) return null;
  const cls = { high: "text-[#9fe0a8] border-[#1f4a2a]", medium: "text-ink-2", low: "text-[#f6c75a] border-[#5b4413]" }[value];
  return (
    <Badge className={cls} title="Information confidence (separate from severity): rule-based, not a probability">
      Info confidence: {value}
    </Badge>
  );
}

export function SyntheticTag() {
  return (
    <Badge className="border-[#3d2f5c] text-[#c4b5f5]" title="Synthetic demonstration data — not a real emergency">
      <FlaskConical className="h-3 w-3" aria-hidden /> Synthetic
    </Badge>
  );
}
