# How well Gnani Prisma hears a disaster report

Measured on November 3, 2026 against the live Gnani API. Run it again with `backend/scripts/benchmark_stt.py`.

**The score is what a dispatcher needs:** did the village, the disaster type and the number of people all come
out right after Prisma's text went through the normal extraction? "All 3" counts clips where every one was right.

## Results

12 clips: 3 each in Hindi, Marathi, Hinglish and English.

| Audio | Model | Village | Disaster | People | **All 3** |
|---|---|---:|---:|---:|---:|
| Clean | Prisma v2.5 | 6/12 | 10/12 | 11/12 | **6/12** |
| Clean | Prisma v3.0 + hints | 12/12 | 11/12 | 11/12 | **11/12** |
| Phone quality | Prisma v2.5 | 6/12 | 10/12 | 11/12 | **6/12** |
| Phone quality | Prisma v3.0 + hints | 11/12 | 11/12 | 11/12 | **11/12** |
| Phone + noise at 10 dB | Prisma v2.5 | 8/12 | 10/12 | 10/12 | **6/12** |
| Phone + noise at 10 dB | Prisma v3.0 + hints | 12/12 | 11/12 | 11/12 | **11/12** |
| Phone + noise at 0 dB | Prisma v2.5 | 6/12 | 11/12 | 11/12 | **6/12** |
| Phone + noise at 0 dB | Prisma v3.0 + hints | 11/12 | 11/12 | 11/12 | **10/12** |

At 0 dB the noise is as loud as the speech.

**What made the difference:** sending Prisma v3.0 a list of local village names and disaster words (`keyterms`).
v2.5 got every Hindi and Marathi clip right but none of the English or Hinglish ones on clean audio, mostly because
it misheard village names written in English, such as "Nandwadi" as "nandwati". Those are the words a dispatcher
can least afford to get wrong.

**Our own noise filter didn't help.** Running the optional filter (`AUDIO_PREPROCESSING=true`) before Prisma:

| Audio (Prisma v3.0 + hints) | Without filter, all 3 | With filter, all 3 |
|---|---:|---:|
| Phone + noise at 10 dB | 11/12 | 11/12 |
| Phone + noise at 0 dB | 10/12 | 9/12 |

So the filter stays off by default. Prisma copes better with the noise left in.

## How it was tested

* **All the speech is synthetic,** as the contest rules require. Hindi, Marathi and Hinglish clips were spoken by
  Gnani Timbre from the synthetic reports, and the rest are bundled clips from a local text-to-speech voice. The
  bundled Hinglish clip, SYN-001, is the one clean-audio failure, and its robotic voice is hard to follow.
* **Phone quality** means down to 8 kHz and through mu-law, as on a voice call. **Noise** is generated pink-ish noise
  with a fixed seed, so every model hears the same thing.
* **Which clips count was decided before any audio was heard:** extraction must get all the fields right from the
  written text, so that speech recognition is the only thing being measured.

## What this doesn't show

* **12 clips is a small sample,** so one clip moves a score by about 8 points. Read these as a direction, not a precise rate.
* **Timbre and clean text-to-speech are easier than real people.** Nothing here used a frightened caller, a dialect, a
  bad line or real background sound like rain and crowds, because the contest allows synthetic data only.
* **The hints contain the villages being tested,** which is realistic for a district that loads its own place list,
  but a village missing from the list wouldn't get this benefit.
* **The filter comparison is one filter, one kind of generated noise.** It doesn't say filtering can never help.
