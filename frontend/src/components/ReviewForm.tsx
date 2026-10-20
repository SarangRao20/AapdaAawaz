import { useState } from "react";
import { api } from "../lib/api";
import { getReviewer, setReviewer } from "../lib/reviewer";
import type { Gazetteer, IncidentDetail } from "../lib/types";
import { Button, ErrorBanner, FieldLabel, Input, Select, Textarea } from "./ui";

/**
 * Human verification controls. Corrections are stored as incident-level overrides with an audit
 * entry (old -> new); the original transcripts and AI extractions are never modified.
 */
export function ReviewForm({ incident, gazetteer, onDone }: { incident: IncidentDetail; gazetteer: Gazetteer | null; onDone: () => void }) {
  const [reviewer, setReviewerName] = useState(getReviewer);
  const [placeId, setPlaceId] = useState("");
  const [customName, setCustomName] = useState("");
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [people, setPeople] = useState("");
  const [clearPeople, setClearPeople] = useState(false);
  const [urgency, setUrgency] = useState("");
  const [disaster, setDisaster] = useState("");
  const [notes, setNotes] = useState("");
  const [markReviewed, setMarkReviewed] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const canConfirmLocation = incident.location_status === "simulated_reference";
  const candidates = incident.location?.candidates ?? [];

  async function submit(extra: Record<string, unknown> = {}) {
    setBusy(true);
    setError(null);
    setOk(null);
    const body: Record<string, unknown> = { reviewer, notes: notes || null, mark_reviewed: markReviewed, ...extra };
    if (placeId === "__custom") {
      body.verify_location = { place_name: customName || null, latitude: lat ? Number(lat) : null, longitude: lon ? Number(lon) : null };
    } else if (placeId) {
      body.verify_location = { place_id: placeId };
    }
    if (clearPeople) body.clear_people_count = true;
    else if (people) body.people_count = Number(people);
    if (urgency) body.urgency = urgency;
    if (disaster) body.disaster_type = disaster;
    setReviewer(reviewer);
    try {
      await api.review(incident.id, body);
      setOk("Saved. The change is recorded in the audit history.");
      setPlaceId("");
      setPeople("");
      setUrgency("");
      setDisaster("");
      setNotes("");
      setClearPeople(false);
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <FieldLabel htmlFor="rv">Reviewer</FieldLabel>
          <Input id="rv" value={reviewer} onChange={(e) => setReviewerName(e.target.value)} />
        </div>
        <div>
          <FieldLabel htmlFor="loc">Verify / correct location</FieldLabel>
          <Select id="loc" value={placeId} onChange={(e) => setPlaceId(e.target.value)}>
            <option value="">— keep current —</option>
            {candidates.length > 0 && (
              <optgroup label="Candidates from the reports">
                {candidates.map((c) => {
                  const p = gazetteer?.places.find((x) => x.id === c);
                  return (
                    <option key={c} value={c}>
                      {p?.name ?? c} ({c})
                    </option>
                  );
                })}
              </optgroup>
            )}
            <optgroup label="All reference places (simulated)">
              {gazetteer?.places.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} · {p.name_local} ({p.id})
                </option>
              ))}
            </optgroup>
            <option value="__custom">Other place — enter confirmed coordinates</option>
          </Select>
        </div>
      </div>
      {placeId === "__custom" && (
        <div className="grid gap-3 sm:grid-cols-3">
          <Input placeholder="Place name" value={customName} onChange={(e) => setCustomName(e.target.value)} aria-label="Place name" />
          <Input placeholder="Latitude" inputMode="decimal" value={lat} onChange={(e) => setLat(e.target.value)} aria-label="Latitude" />
          <Input placeholder="Longitude" inputMode="decimal" value={lon} onChange={(e) => setLon(e.target.value)} aria-label="Longitude" />
          <p className="text-2xs text-ink-3 sm:col-span-3">Only enter coordinates you have confirmed (e.g. by call-back). Free text is never geocoded automatically.</p>
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-3">
        <div>
          <FieldLabel htmlFor="ppl">People count</FieldLabel>
          <Input id="ppl" type="number" min={1} placeholder={incident.people_count?.toString() ?? "unknown"} value={people} disabled={clearPeople} onChange={(e) => setPeople(e.target.value)} />
          <label className="mt-1 flex items-center gap-1.5 text-2xs text-ink-3">
            <input type="checkbox" checked={clearPeople} onChange={(e) => setClearPeople(e.target.checked)} /> mark as unknown
          </label>
        </div>
        <div>
          <FieldLabel htmlFor="urg">Dispatcher priority</FieldLabel>
          <Select id="urg" value={urgency} onChange={(e) => setUrgency(e.target.value)}>
            <option value="">— keep ({incident.priority_label}) —</option>
            <option value="critical">critical</option>
            <option value="high">high</option>
            <option value="medium">medium</option>
            <option value="low">low</option>
            <option value="unknown">remove override</option>
          </Select>
        </div>
        <div>
          <FieldLabel htmlFor="dis">Hazard</FieldLabel>
          <Select id="dis" value={disaster} onChange={(e) => setDisaster(e.target.value)}>
            <option value="">— keep ({incident.disaster_type}) —</option>
            {["flood", "landslide", "earthquake", "fire", "other", "unknown"].map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </Select>
        </div>
      </div>
      <div>
        <FieldLabel htmlFor="notes">Reviewer notes</FieldLabel>
        <Textarea id="notes" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="e.g. Caller re-contacted; confirmed the bridge is in Karanjkhed." />
      </div>
      <label className="flex items-center gap-2 text-xs text-ink-2">
        <input type="checkbox" checked={markReviewed} onChange={(e) => setMarkReviewed(e.target.checked)} /> Mark incident as reviewed (acknowledges current flags and contradictions)
      </label>
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" busy={busy} disabled={!reviewer.trim() || (placeId === "__custom" && (!lat || !lon))} onClick={() => submit()}>
          Save review
        </Button>
        {canConfirmLocation && (
          <Button busy={busy} disabled={!reviewer.trim()} onClick={() => submit({ confirm_current_location: true })} title="Confirm the reference place as the verified location">
            Confirm current location
          </Button>
        )}
      </div>
      {error && <ErrorBanner message={error} />}
      {ok && <p className="text-xs text-[#9fe0a8]">{ok}</p>}
    </div>
  );
}
