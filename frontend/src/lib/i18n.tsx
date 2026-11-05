import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

export type Locale = string; // Any language code

const CACHE_KEY = "aa.translations";
const LANG_KEY = "aa.lang";

// Get browser's preferred language
function getBrowserLanguage(): string {
  try {
    const lang = navigator.language || (navigator as any).userLanguage;
    return lang.split("-")[0]; // Get language code without region (en from en-US)
  } catch {
    return "en";
  }
}

// Google Translate API for free translation (no key needed)
async function translateText(text: string, targetLang: string, sourceLang: string = "auto"): Promise<string> {
  if (targetLang === "en") return text; // No need to translate to English
  if (!text || text.length === 0) return text;

  try {
    // Use Google Translate free API
    const encodedText = encodeURIComponent(text);
    const url = `https://translate.googleapis.com/translate_a/single?client=gtx&sl=${sourceLang}&tl=${targetLang}&dt=t&q=${encodedText}`;

    const response = await fetch(url);
    const data = await response.json();

    if (data && data[0] && data[0][0]) {
      return data[0][0][0];
    }
    return text;
  } catch (error) {
    console.warn(`Translation failed for "${text}" to ${targetLang}:`, error);
    return text;
  }
}

// Translation cache
class TranslationCache {
  private cache: Map<string, Map<string, string>> = new Map();

  async translate(text: string, targetLang: string, sourceLang: string = "auto"): Promise<string> {
    // Check memory cache
    if (this.cache.has(targetLang)) {
      const langCache = this.cache.get(targetLang)!;
      if (langCache.has(text)) {
        return langCache.get(text)!;
      }
    }

    // Check localStorage
    try {
      const stored = localStorage.getItem(`${CACHE_KEY}:${targetLang}`);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (parsed[text]) {
          // Update memory cache
          if (!this.cache.has(targetLang)) {
            this.cache.set(targetLang, new Map());
          }
          this.cache.get(targetLang)!.set(text, parsed[text]);
          return parsed[text];
        }
      }
    } catch { }

    // Translate and cache
    const translated = await translateText(text, targetLang, sourceLang);

    // Update memory cache
    if (!this.cache.has(targetLang)) {
      this.cache.set(targetLang, new Map());
    }
    this.cache.get(targetLang)!.set(text, translated);

    // Update localStorage
    try {
      const stored = localStorage.getItem(`${CACHE_KEY}:${targetLang}`);
      const parsed = stored ? JSON.parse(stored) : {};
      parsed[text] = translated;
      localStorage.setItem(`${CACHE_KEY}:${targetLang}`, JSON.stringify(parsed));
    } catch { }

    return translated;
  }

  clear() {
    this.cache.clear();
  }
}

const cache = new TranslationCache();

interface I18nContextType {
  locale: string;
  setLocale: (l: string) => void;
  t: ((text: string) => string) & Record<string, string>;
  translate: (text: string, targetLang?: string) => Promise<string>;
}

const I18nContext = createContext<I18nContextType>({
  locale: "en",
  setLocale: () => {},
  t: Object.assign((text: string) => text, {}) as any,
  translate: async (text) => text,
});

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<string>(() => {
    try {
      const saved = localStorage.getItem(LANG_KEY);
      if (saved) return saved;
    } catch { }
    return getBrowserLanguage();
  });

  const [translations, setTranslations] = useState<Map<string, string>>(new Map());

  const setLocale = useCallback((l: string) => {
    console.log("[i18n] Setting locale to:", l);
    setLocaleState(l);
    try {
      localStorage.setItem(LANG_KEY, l);
    } catch { }
  }, []);

  // Pre-translate common UI strings when locale changes
  useEffect(() => {
    if (locale === "en") {
      console.log("[i18n] Locale is English, clearing translations");
      setTranslations(new Map());
      return;
    }

    console.log("[i18n] Fetching translations for locale:", locale);
    const commonStrings = [
      // Navigation & UI
      "New Call", "Situation Room", "Settings", "Record a voice report and process it",
      "Live map, alerts and active incidents", "API providers and thresholds",
      "Keyboard Shortcuts", "Open command palette", "Show keyboard shortcuts",
      "Navigate command palette results", "Select result", "Close modal / palette",

      // CommandCenter
      "No incidents yet", "Critical", "High", "Medium", "Low",
      "Globe", "Map", "Timeline", "Filters", "Recent",
      "Incidents by priority", "Active incidents",
      "Back to list", "Needs attention", "All incidents", "Tap one to find it on the globe",
      "Urgent", "All", "All types", "Detailed incident table",
      "Scores, confidence and review flags for every incident",
      "Live · Situation Room",

      // Common actions
      "Loading...", "Error", "Save", "Cancel", "Delete", "Edit", "View",
      "Submit", "Back", "Next", "Previous", "Close", "Open",

      // Status
      "Draft", "Submitted", "Processed", "Complete", "Pending",
      "Location", "People", "Urgency",
    ];

    // Pre-fetch translations for common strings
    const fetchTranslations = async () => {
      console.log("[i18n] Starting fetch for", commonStrings.length, "strings");
      const newTranslations = new Map();  // START FRESH - don't copy old translations!
      let count = 0;
      for (const str of commonStrings) {
        try {
          const translated = await cache.translate(str, locale);
          newTranslations.set(str, translated);
          count++;
          console.log(`[i18n] Translated: "${str}" → "${translated}"`);
        } catch (e) {
          console.error(`[i18n] Failed to translate "${str}":`, e);
        }
      }
      console.log(`[i18n] Fetched ${count} translations, updating state`);
      setTranslations(newTranslations);
    };

    fetchTranslations();
  }, [locale]);

  // Translate text with caching - support both function call and property access
  const tFunc = useCallback((text: string): string => {
    if (locale === "en") return text;
    return translations.get(text) || text;
  }, [locale, translations]);

  // Create a function that also works as an object with properties
  const t = Object.assign(tFunc, {
    critical: tFunc("Critical"),
    high: tFunc("High"),
    medium: tFunc("Medium"),
    low: tFunc("Low"),
    location: tFunc("Location"),
    people: tFunc("People"),
    urgency: tFunc("Urgency"),
  }) as unknown as ((text: string) => string) & Record<string, string>;

  // Keep document lang attribute in sync
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const translate = useCallback(async (text: string, targetLang?: string): Promise<string> => {
    const lang = targetLang || locale;
    if (lang === "en") return text;
    return cache.translate(text, lang);
  }, [locale]);

  return (
    <I18nContext.Provider value={{ locale, setLocale, t, translate }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n() {
  return useContext(I18nContext);
}

// Hook for auto-translating content
export function useAutoTranslate(text: string) {
  const { locale, translate } = useI18n();
  const [translated, setTranslated] = useState(text);

  useEffect(() => {
    if (locale === "en") {
      setTranslated(text);
      return;
    }

    translate(text, locale).then(setTranslated);
  }, [text, locale, translate]);

  return translated;
}

// Simple component for translatable text - just use <T>{"Your text"}</T>
export function T({ children }: { children: string }) {
  const { t, locale } = useI18n();
  // Include locale in output to make component re-render when language changes
  return <>{locale && t(children)}</>;
}
