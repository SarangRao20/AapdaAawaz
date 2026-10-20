// The reviewer name is a per-browser convenience only; storage may be unavailable (private mode).
const KEY = "aapda.reviewer";

export function getReviewer(): string {
  try {
    return localStorage.getItem(KEY) || "dispatcher";
  } catch {
    return "dispatcher";
  }
}

export function setReviewer(name: string): void {
  try {
    localStorage.setItem(KEY, name);
  } catch {
    /* storage unavailable */
  }
}
