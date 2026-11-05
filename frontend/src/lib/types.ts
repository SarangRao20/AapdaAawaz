// Shapes returned by the FastAPI backend (see backend/app/api/serializers.py).

export type Priority = "critical" | "high" | "medium" | "low";
export type ReviewStatus = "needs_review" | "reviewed" | "rereview_needed" | "no_review_required";
export type LocationStatus =
  | "human_verified"
  | "caller_gps"
  | "simulated_reference"
  | "caller_stated_unmapped"
  | "ambiguous"
  | "unknown";
export type Language = "mr" | "hi" | "en" | "mixed" | "unknown";

export interface Reason {
  code: string;
  field: string;
  message: string;
}

export interface Factor {
  key: string;
  label: string;
  points: number;
  detail: string;
}

export interface PriorityBreakdown {
  score: number;
  label: Priority;
  computed_label: Priority;
  factors: Factor[];
  missing_info: string[];
  notes: string[];
  thresholds: Record<"critical" | "high" | "medium", number>;
  disclaimer: string;
}

export interface AudioRef {
  id: number;
  kind: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  uploaded_at: string;
  url: string;
}

export interface Job {
  id: number;
  stage: string;
  provider: string | null;
  provider_mode: string | null;
  status: string;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  error: string | null;
  detail: Record<string, unknown> | null;
}

export interface Evidence {
  field: string;
  text: string;
  negated: boolean;
}

export interface Extraction {
  disaster_type: string;
  disaster_types_mentioned: string[];
  disaster_basis: string;
  location: {
    place_name: string | null;
    place_id: string | null;
    landmark: string | null;
    landmark_id: string | null;
    landmark_types: string[];
    district: string | null;
    state: string | null;
    latitude: number | null;
    longitude: number | null;
    source: string;
    confidence: number;
    confidence_basis: string;
    candidates: string[];
    stated_text: string[];
    status: string;
  };
  people_affected: {
    count: number | null;
    approximate: boolean;
    range: number[] | null;
    all_counts_mentioned: number[];
    families: number | null;
    confidence: number;
    confidence_basis: string;
  };
  vulnerable_people: Record<string, { count: number | null; evidence: string } | null>;
  immediate_needs: string[];
  reported_danger: string[];
  medical_emergency: boolean | null;
  medical_need: boolean | null;
  critical_medication: boolean | null;
  urgency: string;
  urgency_basis: string;
  status_claims: string[];
  language: Language;
  transcript_quality: string;
  transcript_quality_basis: string;
  summary: string;
  uncertainties: string[];
  requires_human_review: boolean;
  evidence: Evidence[];
  provider: string;
  provider_mode: string;
}

export interface FieldAssessment {
  [field: string]: { status: string; basis?: string | null; evidence_level?: number; [k: string]: unknown };
}

export interface Acknowledgement {
  id: number;
  language: string;
  text: string;
  provider: string | null;
  provider_mode: string | null;
  status: "text_only" | "audio_ready" | "audio_failed";
  error: string | null;
  audio_url: string | null;
  created_at: string;
  ai_generated_label: string;
}

export interface ReportSummary {
  id: string;
  received_at: string;
  source: string;
  is_synthetic: boolean;
  synthetic_label: string | null;
  fixture_id: string | null;
  language: Language | null;
  language_hint: Language | null;
  status: string;
  transcript: string | null;
  transcript_source: string | null;
  transcript_provider: string | null;
  transcript_provider_mode: string | null;
  has_audio: boolean;
  audio: AudioRef[];
  location_text: string | null;
  location_status: string | null;
  location_confidence: number | null;
  people_count: number | null;
  disaster_type: string | null;
  summary: string | null;
  priority_label: Priority | null;
  priority_score: number | null;
  gate_status: string | null;
  review_reasons: Reason[];
  review_resolved: boolean;
  dedup_outcome: string | null;
  incident_id: string | null;
  pending_suggestions: number;
  caller_location: { latitude: number; longitude: number; accuracy_m: number | null } | null;
  processing_ms: number | null;
  processed_at: string | null;
  error: string | null;
}

export interface TelegramConversationState {
  state: "new" | "needs_text" | "collecting" | "complete" | "incomplete";
  pending_field: string | null;
  attempts: number;
  skipped_fields: string[];
  next_followup_at: string | null;
  updated_at: string | null;
}

export interface Suggestion {
  id: number;
  report_id: string;
  source_incident_id: string;
  candidate_incident_id: string;
  score: number;
  evidence: MatchEvidence | null;
  contradictions: string[];
  status: "pending" | "confirmed" | "rejected" | "obsolete";
  created_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
  note: string | null;
}

export interface MatchEvidence {
  incident_id: string;
  score: number;
  outcome: string;
  evidence: { feature: string; points: number; detail: string }[];
  contradictions: string[];
  caps: string[];
}

export interface AuditEntry {
  id: number;
  entity_type: string;
  entity_id: string;
  action: string;
  field: string | null;
  old_value: unknown;
  new_value: unknown;
  actor: string;
  note: string | null;
  created_at: string;
}

export interface ReportDetail extends ReportSummary {
  transcript_raw: Record<string, unknown> | null;
  transcript_request_id: string | null;
  stt_error: string | null;
  extraction_original: Extraction | null;
  extraction_current: Extraction | null;
  extraction_provider: string | null;
  extraction_mode: string | null;
  field_assessment: FieldAssessment | null;
  priority_breakdown: PriorityBreakdown | null;
  dedup_evidence: { outcome: string; best: MatchEvidence | null; suggestions: MatchEvidence[]; considered: number } | MatchEvidence | null;
  auto_incident_id: string | null;
  follow_up_needed: boolean;
  follow_up_questions: string[];
  follow_up_missing_fields: string[];
  follow_up_status: "none" | "pending" | "answered" | "unanswered";
  /** The channel that can really reach the caller. null = nobody has been (or can be) contacted. */
  follow_up_channel: "telegram" | "live_call" | null;
  telegram: TelegramConversationState | null;
  jobs: Job[];
  links: { incident_id: string; outcome: string; score: number | null; active: boolean; actor: string; created_at: string; deactivated_at: string | null }[];
  suggestions: Suggestion[];
  acknowledgement: Acknowledgement | null;
  audit: AuditEntry[];
  ground_truth: Record<string, unknown> | null;
}

export interface IncidentLocation {
  place_id: string | null;
  place_name: string | null;
  landmark: string | null;
  landmark_id: string | null;
  landmark_types: string[];
  candidates: string[];
  unmapped_name: string | null;
  district: string | null;
  state: string | null;
  coordinate_source: string | null;
  stated_text: string[];
  verified_by?: string;
  gps_accuracy_m?: number | null;
}

export interface Incident {
  id: string;
  status: string;
  merged_into_id: string | null;
  created_at: string;
  updated_at: string;
  last_report_at: string | null;
  disaster_type: string;
  location: IncidentLocation | null;
  location_status: LocationStatus;
  latitude: number | null;
  longitude: number | null;
  coordinates_are_simulated: boolean;
  people_count: number | null;
  people_detail: {
    per_report: { report_id: string; count: number | null; approximate: boolean; range: number[] | null; families: number | null }[];
    families: number | null;
    basis: string;
  } | null;
  vulnerable: Record<string, { count: number | null; reports: string[]; evidence: string[] }>;
  needs: string[];
  dangers: string[];
  medical_emergency: boolean | null;
  urgency: string;
  languages: string[];
  summary: string | null;
  priority_score: number;
  priority_label: Priority;
  priority_breakdown: PriorityBreakdown | null;
  info_confidence: {
    overall: "high" | "medium" | "low";
    location: string;
    people_count: string;
    reports: number;
    languages: string[];
    low_quality_transcripts: number;
    basis: string[];
    method: string;
  } | null;
  review_reasons: Reason[];
  contradictions: string[];
  missing_info: string[];
  recommended_action: string | null;
  review_status: ReviewStatus;
  human_overrides: Record<string, unknown>;
  report_count: number;
}

export interface IncidentMember extends ReportSummary {
  link_outcome: string;
  link_score: number | null;
  link_evidence: MatchEvidence | Record<string, unknown> | null;
  linked_at: string;
  extraction_current: Extraction | null;
  extraction_original: Extraction | null;
  field_assessment: FieldAssessment | null;
  priority_breakdown: PriorityBreakdown | null;
  acknowledgement: Acknowledgement | null;
}

export interface IncidentDetail extends Incident {
  reports: IncidentMember[];
  link_history: { report_id: string; outcome: string; active: boolean; actor: string; score: number | null; created_at: string; deactivated_at: string | null }[];
  suggestions: Suggestion[];
  audit: AuditEntry[];
  reviews: { id: number; reviewer: string; action: string; notes: string | null; payload: unknown; created_at: string }[];
}

export interface Stats {
  total_reports: number;
  processed_reports: number;
  unique_incidents: number;
  critical_awaiting_review: number;
  critical_incidents: number;
  reports_needing_verification: number;
  duplicates_linked: number;
  possible_duplicates_pending: number;
  avg_processing_ms: number | null;
  processing_sample: number;
  incidents_needing_review: number;
  by_priority: Record<string, number>;
  by_review_status: Record<string, number>;
  by_location_status: Record<string, number>;
  by_disaster: Record<string, number>;
  report_status: Record<string, number>;
  report_languages: Record<string, number>;
  transcript_modes: Record<string, number>;
  synthetic_reports: number;
  people_reported_in_critical: number;
}

export interface Paged<T> {
  total: number;
  limit: number;
  offset: number;
  items: T[];
  worker_queue?: number;
}

export interface Place {
  id: string;
  name: string;
  name_local: string;
  latitude: number;
  longitude: number;
  coordinate_source: string;
}

export interface Gazetteer {
  notice: string;
  district: string;
  state: string;
  is_simulated: boolean;
  places: Place[];
  landmarks: { id: string; place_id: string; type: string; name: string }[];
}

export interface ProviderStatus {
  gnani_api_key_configured: boolean;
  gnani_base_url: string;
  speech_to_text: { active: string | null; mode: string; prisma_available: boolean; note: string | null };
  extraction: { active: string; mode: string; evon_available: boolean; note: string };
  text_to_speech: { active: string | null; mode: string; timbre_available: boolean; note: string | null };
}

export interface RuntimeConfig {
  gate: {
    min_location_confidence: number;
    min_people_confidence: number;
    unknown_people_review_at: string;
    flag_low_quality_transcript: boolean;
    flag_unclear_urgency: boolean;
  };
  dedup: {
    likely_threshold: number;
    possible_threshold: number;
    time_window_minutes: number;
    max_suggestions: number;
    weights: Record<string, number>;
    coords_near_km: number;
    coords_far_km: number;
  };
  priority: { weights: Record<string, number>; thresholds: Record<string, number>; unclear_floor: string; safe_status_cap: string };
  providers: { stt: string; tts: string };
}

export interface SuggestionItem extends Suggestion {
  report: { id: string; transcript: string | null; language: string | null; summary: string | null } | null;
  source_incident: Incident | null;
  candidate_incident: Incident | null;
}

export interface Fixture {
  id: string;
  language_hint: string;
  scenario_tags: string[];
  transcript: string;
  has_audio: boolean;
  loaded: boolean;
}

export interface PRF {
  tp: number;
  fp: number;
  fn: number;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  support?: number;
}

export interface Breakdown {
  correct: number;
  correct_unknown: number;
  wrong: number;
  missed: number;
  false_value: number;
  n: number;
  accuracy: number | null;
  definition: string;
}

export interface EvaluationResult {
  generated_at: string;
  run_id: number;
  dataset: { label: string; version: string; n_reports: number; synthetic: boolean };
  providers: { extraction: string; evon_available?: boolean; transcripts: string };
  caveats: string[];
  splits: Record<"development" | "holdout", EvaluationSplit>;
  stt: {
    audio_fixtures: number;
    measured: boolean;
    provider: string | null;
    note: string;
    success_rate?: number | null;
    mean_cer?: number | null;
    samples: { fixture_id: string; success: boolean; cer?: number; error?: string; transcript?: string }[];
  };
}

export interface EvaluationSplit {
  description: string;
  n_reports: number;
  rows: Record<string, string | number | boolean | null>[];
  clusters: Record<string, string[]>;
  metrics: {
    n_reports: number;
    location: Breakdown;
    people_count: Breakdown;
    disaster_type: Breakdown;
    vulnerable: { per_group: Record<string, PRF>; micro: PRF };
    medical_emergency: PRF;
    priority: {
      accuracy: number | null;
      confusion: Record<string, Record<string, number>>;
      per_class: Record<string, PRF>;
      labels: string[];
      under_triaged: string[];
      over_triaged: string[];
    };
    language: { accuracy: number | null; confusion: Record<string, Record<string, number>> };
    deduplication: {
      pairwise: PRF;
      definition: string;
      gt_incidents: number;
      predicted_incidents: number;
      possible_duplicate_suggestions: { total: number; true_duplicate: number; not_duplicate: number };
    };
    human_review: { rate: number | null; count: number; reasons: Record<string, number> };
    latency_ms: { mean: number | null; p95: number | null; note: string };
  };
}

export interface LiveCallSummary {
  id: string;
  language: string;
  state: string;
  started_at: number;
  ended_at: number | null;
  turns: { speaker: "caller" | "assistant"; text: string; at: number }[];
  facts: { place: string | null; disaster: string | null; people: number | null; priority: string | null; score: number | null; report_id: string | null; needs_review: boolean };
  asking_for: string | null;
  last_response_ms: number | null;
}

export interface VoiceAlertOptions {
  templates: { id: string; label: string; text: Record<string, string> }[];
  recipients: { total: number; languages: Record<string, number> };
}
