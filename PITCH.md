# Aapda Awaaz: a voice assistant for disaster response

**Built with Gnani AI (Prisma + Timbre) for the Great Indian AI Internship Challenge.**
Team: Sarang Gajanan Rao and Jainam Dudhediya, Pune Institute of Computer Technology.

## The problem
In a flood, emergency lines fill up. Callers are frightened, switch languages, and many describe the same place.
Dispatchers get a pile of unstructured audio and have to decide, by ear and under pressure, who is helped first.

## What we built
People report by **Android app, Telegram bot or website**, in **10 Indian languages plus Hinglish**
(Hindi, Marathi, English, Bengali, Gujarati, Kannada, Malayalam, Punjabi, Tamil, Telugu).
**Awaaz Live** is a realtime voice call: the caller speaks, the assistant asks aloud, in their language, only for what
is still missing (where, what happened, how many people), and reads the facts back.

Behind it, a dispatcher dashboard shows each report filling in live, already ranked:
facts are extracted, **six reports about one event merge into one incident**, and a **priority score shows its reasons**.
The dispatcher verifies, corrects, merges or splits, and can send a **safety voice alert** back in each person's own language.
Every action is logged.

## How it uses Gnani
* **Prisma v3.0** streams the caller's voice live, with local village names as hints (Hindi, Marathi, English).
* **Timbre v3.0** speaks the questions, confirmations and safety alerts in the caller's language.
* **Evon:** an OpenAI-compatible adapter is built for self-hosting the open-weights model; this submission uses rule-based extraction.

## Why it is safe to trust
**AI listens, sorts and remembers. A person always decides.** It never dispatches anyone and never promises help.
Shaky transcripts and guessed locations are flagged for human review, never shown as fact. Safety alerts are fixed,
pre-written text, not generated. In the seven newer languages, facts are read from a machine translation, so those
reports are always flagged for a person to check against the original. All scenarios are synthetic; this is decision
support, not a replacement for 112.

## Try it
* Website: https://aapdaawaaz.duckdns.org
* Telegram bot: https://t.me/aapda_aawaz_bot
* Android app: https://github.com/SarangRao20/AapdaAawaz/releases
* Code, tests and limitations: this repository (see `README.md` and `docs/KNOWN_LIMITATIONS.md`)
