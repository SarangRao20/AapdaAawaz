# 60-second demo script

The story of this video is Gnani's voice. Keep the conversation on screen for as long as possible, and let
people hear both sides of it.

**The contest allows synthetic data only.** Speak the scripted lines below, and don't show a real phone
number, a real location or a real report. Check the contest terms on whether your own acted voice is allowed.

## Before recording

1. Run the backend and dashboard (README, Quick start), then log in.
2. Open two browser windows side by side:
   * **Left, the caller:** Awaaz Live (`/awaaz`), language set to Hinglish.
   * **Right, the dispatcher:** Situation Room (`/live`).
3. Use speakers rather than headphones, so the recording picks up both voices.
4. To start from an empty screen, press **Reset** twice. **This deletes every report in that database**, so use
   a separate copy (`AAPDA_VAR_DIR`, see the README) if you have reports you want to keep.

## The script

| Time | Do | Say or show |
|---|---|---|
| **0–5 s** | Show the landing page, then cut to the call screen. | Voiceover: "In a flood, the phone lines fill up. Aapda Awaaz still answers, in your language, using Gnani's voice AI." |
| **5–30 s** | Press **Start call** and speak the lines below. | Let the conversation play with no voiceover. It's the whole point. |
| **30–40 s** | Bring the dispatcher window forward. | "While that happens, a dispatcher watches the report fill in live, already ranked, with no typing." |
| **40–48 s** | Open the incident and press **Hear it** in Voice alert, in two languages. | "Then a dispatcher can speak back: fixed safety messages, in each person's language, using Gnani Timbre." |
| **48–55 s** | Show the results table in `docs/STT_BENCHMARK.md`. | State the village result and the noise result. Read the numbers from the table, and don't round them up. |
| **55–60 s** | Back to the call screen. | "Gnani Prisma listens. Gnani Timbre speaks. A person always decides." |

### Lines to speak (Hinglish)

The assistant asks only for what's missing, so wait for each question:

1. "Yahan baadh aa gayi hai, paani bahut tezi se badh raha hai, log phanse hue hain."
2. *(it asks where)* "Main Nandwadi gaon se bol raha hoon."
3. *(it asks how many)* "Pachees log hain."

It then reads the place, the event and the head count back to you, and tells you to call 112.

### If you have time for a second take

Run the call in Marathi or Hindi too and cut between them. Showing several languages on the same screen is
what the Main Character and Mixed Vibes awards look for.

## If something goes wrong

* **Nothing happens when you speak:** check the browser allowed the microphone, then press **I've finished speaking**.
* **A word is misheard:** that's real, so keep going. The assistant asks again if the answer didn't fill the field.
* **No internet or no credits:** a live call needs Gnani, so it can't run. Use **1 · Incoming call** and **2 · Load
  sample reports** on the Situation Room instead, which give 40 reports, 22 incidents, 18 duplicates linked,
  7 possible duplicates, 13 critical incidents and 22 reports needing verification on a fresh reset.
