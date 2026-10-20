import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

export type Locale = "en" | "hi" | "mr";

const strings = {
  en: {
    newCall: "New call",
    liveSituation: "Live situation",
    toReview: "To review",
    allReports: "All reports",
    critical: "Critical",
    high: "High",
    medium: "Medium",
    low: "Low",
    location: "Location",
    people: "People affected",
    urgency: "Urgency",
    needsAttention: "Needs attention",
    allClear: "All clear",
    reports: "Reports",
    incidentDetails: "Incident details",
    accuracy: "Accuracy",
    settings: "Settings",
  },
  hi: {
    newCall: "नई कॉल",
    liveSituation: "लाइव स्थिति",
    toReview: "समीक्षा हेतु",
    allReports: "सभी रिपोर्ट",
    critical: "गंभीर",
    high: "उच्च",
    medium: "मध्यम",
    low: "सामान्य",
    location: "स्थान",
    people: "प्रभावित लोग",
    urgency: "तात्कालिकता",
    needsAttention: "ध्यान आवश्यक",
    allClear: "सब सुरक्षित",
    reports: "रिपोर्ट",
    incidentDetails: "घटना विवरण",
    accuracy: "सटीकता",
    settings: "सेटिंग",
  },
  mr: {
    newCall: "नवीन कॉल",
    liveSituation: "थेट परिस्थिती",
    toReview: "तपासणीसाठी",
    allReports: "सर्व अहवाल",
    critical: "गंभीर",
    high: "उच्च",
    medium: "मध्यम",
    low: "सामान्य",
    location: "ठिकाण",
    people: "बाधित लोक",
    urgency: "तातडी",
    needsAttention: "लक्ष आवश्यक",
    allClear: "सर्व सुरक्षित",
    reports: "अहवाल",
    incidentDetails: "घटना तपशील",
    accuracy: "अचूकता",
    settings: "सेटिंग्ज",
  },
};

export type Strings = typeof strings.en;

const I18nContext = createContext<{
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: Strings;
}>({
  locale: "en",
  setLocale: () => {},
  t: strings.en,
});

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(() => {
    try {
      const saved = localStorage.getItem("aa.lang") as Locale | null;
      if (saved && (saved === "en" || saved === "hi" || saved === "mr")) return saved;
    } catch {
      /* storage unavailable */
    }
    return "en";
  });

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    try {
      localStorage.setItem("aa.lang", l);
    } catch {
      /* storage unavailable */
    }
  }, []);

  // Keep document lang attribute in sync
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  return (
    <I18nContext.Provider value={{ locale, setLocale, t: strings[locale] }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n() {
  return useContext(I18nContext);
}
