/** Every language the voice pipeline speaks: Gnani Prisma listens and Gnani Timbre talks back in all of them. */
export const CORE_LANGUAGES = ["hi", "mr", "en", "mixed"] as const;
export const EXTRA_LANGUAGES = ["bn", "gu", "kn", "ml", "pa", "ta", "te"] as const;
export const ALL_LANGUAGES = [...CORE_LANGUAGES, ...EXTRA_LANGUAGES] as const;
export type CallLanguageCode = (typeof ALL_LANGUAGES)[number];

export const LANGUAGE_INFO: Record<CallLanguageCode, { name: string; english: string }> = {
  hi: { name: "हिंदी", english: "Hindi" },
  mr: { name: "मराठी", english: "Marathi" },
  mixed: { name: "Hinglish", english: "Hindi + English" },
  en: { name: "English", english: "English" },
  bn: { name: "বাংলা", english: "Bengali" },
  gu: { name: "ગુજરાતી", english: "Gujarati" },
  kn: { name: "ಕನ್ನಡ", english: "Kannada" },
  ml: { name: "മലയാളം", english: "Malayalam" },
  pa: { name: "ਪੰਜਾਬੀ", english: "Punjabi" },
  ta: { name: "தமிழ்", english: "Tamil" },
  te: { name: "తెలుగు", english: "Telugu" },
};

/** Picker order: the four with hand-built fact extraction first. */
export const LANGUAGE_LIST = ALL_LANGUAGES.map((code) => ({ code, ...LANGUAGE_INFO[code] }));

/** The HTML lang for text in this language (Hinglish is written in Latin script, spoken as Hindi). */
export const htmlLang = (code: string): string => (code === "mixed" ? "hi" : code);
