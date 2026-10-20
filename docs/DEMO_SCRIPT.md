# 60-second demo script

**Before you start:** backend and frontend running (README → Quick start), browser at
http://127.0.0.1:5173, Command Center open. Press **Reset** (click it twice — the first click asks
for confirmation) so the database is empty. Every number you will show comes from the live database
after the steps below; nothing is hard-coded.

| Time | Do | Say |
|---|---|---|
| **0–10 s — the call arrives** | Click **1 · Incoming call**. In the *Live incoming reports* panel `R-SYN-001` appears, already processed. Click its ID; press play on the audio; show *Processing stages*. | "A synthetic Hinglish call from a flooded village. Two Gnani models ran in sequence: **Prisma v2.5** transcribed the audio from speech to text, and **Timbre v2.5** synthesised the spoken acknowledgement the caller would hear back — in their own language. Both tested live with the contest API." |
| **10–20 s — structured extraction** | Scroll to *Structured extraction*. Point at the extracted fields (place, people count, vulnerable groups, needs, urgency) and the *Uncertainties* section. | "The rule-based extractor read the transcript and pulled out structured fields: Nandwadi, about 25 people, elderly and children, trapped on a roof, water rising, boat needed. Any field it's not sure about appears in Uncertainties — not a confident wrong answer. The system also includes a full Evon v3.3 LLM adapter for self-hosted deployment, but Evon is Hugging Face open weights only — not available via API for this contest." |
| **20–35 s — the map** | Back to Command Center, click **2 · Load all synthetic reports**. KPIs jump to 40 reports → **22 candidate incidents**, 18 duplicates linked, 7 possible duplicates pending. | "Forty reports in Marathi, Hindi, Hinglish and English. Deterministic matching on place, landmark, hazard, facts and time groups them into 22 candidate incidents. Contradictory or noisy reports are *not* merged automatically — they wait for a human." |
| **35–45 s — prioritisation** | Scroll to the *Prioritized incident queue*; point at the top critical incident (e.g. Kothale temple: pregnant woman in labour, house surrounded by water). | "The queue is ordered by an explainable score: explicit threat to life +55, medical emergency +45, and so on. Severity is separate from information confidence, and the score never decides rescue order — a dispatcher does." |
| **45–55 s — responsible AI** | Click **3 · Ambiguous-location case**. Show "Ambiguous / conflicting", "Info confidence: low", the review flags, and that it is **not on the map**. In *Human verification* choose *Karanjkhed (P08)*, add a note, **Save review**. | "The caller only said 'the big bridge'. Three villages have one, so we refuse to guess a coordinate — but it stays *critical*. After a call-back the dispatcher verifies it: it now appears on the map with a solid ring, and the audit trail keeps the original extraction output." |
| **55–60 s — impact** | Back to Command Center; read the *Impact summary* line at the bottom. | "40 synthetic reports, 22 candidate incidents, 18 duplicates linked — every uncertain case routed to a human. Fully offline on a laptop, with Prisma and Timbre working live via the Gnani API." |

### Exact numbers you should see (default settings, fresh reset)

After step 2: **40** reports · **22** incidents · **18** duplicates linked · **7** possible duplicates
pending · **13** critical incidents · **10** critical awaiting review · **21** reports needing
verification. After verifying the ambiguous case, *critical awaiting review* drops to **9**.

If you changed thresholds on the Settings page, the numbers will differ — that is expected.

### Backup paths

* No internet: the map shows a "tiles could not load" banner; markers still render on a blank map.
* No microphone: use the demo buttons or type a transcript on *Incoming Reports*.
* To re-run: **Reset** (two clicks) and start again — the result is deterministic.
