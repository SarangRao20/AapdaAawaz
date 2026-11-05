import type { useI18n } from "./i18n";

// Recursively translate object values
export async function translateObject(
  obj: any,
  locale: string,
  translate: Awaited<ReturnType<typeof useI18n>>["translate"]
): Promise<any> {
  if (typeof obj !== "object" || obj === null) {
    return obj;
  }

  if (Array.isArray(obj)) {
    return Promise.all(obj.map((item) => translateObject(item, locale, translate)));
  }

  const translated: any = {};
  for (const [key, value] of Object.entries(obj)) {
    if (typeof value === "string" && value.length > 0 && locale !== "en") {
      // Translate string values (but not IDs or codes that are too short)
      if (value.length > 2 && !value.match(/^[A-Z0-9_-]+$/)) {
        translated[key] = await translate(value, locale);
      } else {
        translated[key] = value;
      }
    } else if (typeof value === "object") {
      translated[key] = await translateObject(value, locale, translate);
    } else {
      translated[key] = value;
    }
  }

  return translated;
}

// Translate API response
export async function translateApiResponse(
  response: any,
  locale: string,
  translate: Awaited<ReturnType<typeof useI18n>>["translate"]
): Promise<any> {
  if (locale === "en") return response;
  return translateObject(response, locale, translate);
}
