import type { WidgetConfig } from "./types";

// TODO before launch: replace the brand colours and logo with Coltek's real values.
export const DEFAULTS: WidgetConfig = {
  apiUrl: "https://chat.coltektechnologies.io",
  brand: { primary: "#0B2545", accent: "#13C4A3", text: "#1B1B1B", surface: "#FFFFFF" },
  logoUrl: "",
  botName: "Coltek Assistant",
  position: "right",
  greeting: "Hi! I'm Coltek's assistant. I can help with our software services, Coltek Code Academy courses and OpenDoor.",
  bubbleText: "Hi! Need help with a website, a course or OpenDoor?",
  starterPrompts: ["I need a website or app", "Tell me about your courses", "I want to try OpenDoor for my church"],
  autoOpenPaths: [],
  contact: { phone: "+233 54 936 1771", whatsapp: "+233549361771", email: "coltektechnologies@gmail.com" },
  privacyPolicyUrl: "",
  zIndex: 2147483000,
  debug: false,
};

type Partial2<T> = { [K in keyof T]?: T[K] extends object ? Partial<T[K]> : T[K] };

const list = (value: string): string[] =>
  value.split(value.includes("|") ? "|" : ",").map((s) => s.trim()).filter(Boolean);

/** data-* attributes on the <script> tag. They override window.ColtekChatConfig. */
function fromScriptTag(script: HTMLOrSVGScriptElement | null): Partial2<WidgetConfig> {
  if (!script || !(script instanceof HTMLScriptElement)) return {};
  const d = script.dataset;
  const out: Partial2<WidgetConfig> = {};
  if (d.apiUrl) out.apiUrl = d.apiUrl;
  if (d.logoUrl) out.logoUrl = d.logoUrl;
  if (d.botName) out.botName = d.botName;
  if (d.position === "left" || d.position === "right") out.position = d.position;
  if (d.greeting) out.greeting = d.greeting;
  if (d.bubbleText) out.bubbleText = d.bubbleText;
  if (d.starterPrompts) out.starterPrompts = list(d.starterPrompts);
  if (d.autoOpenPaths) out.autoOpenPaths = list(d.autoOpenPaths);
  if (d.privacyPolicyUrl) out.privacyPolicyUrl = d.privacyPolicyUrl;
  if (d.zIndex) out.zIndex = Number(d.zIndex);
  if (d.debug) out.debug = d.debug === "true";
  const brand: Record<string, string> = {};
  for (const key of ["primary", "accent", "text", "surface"]) if (d[key]) brand[key] = d[key] as string;
  if (Object.keys(brand).length) out.brand = brand;
  const contact: Record<string, string> = {};
  for (const key of ["phone", "whatsapp", "email"]) if (d[key]) contact[key] = d[key] as string;
  if (Object.keys(contact).length) out.contact = contact;
  return out;
}

export function readConfig(script: HTMLOrSVGScriptElement | null): WidgetConfig {
  const fromWindow = ((window as unknown as { ColtekChatConfig?: Partial2<WidgetConfig> }).ColtekChatConfig || {});
  const fromTag = fromScriptTag(script);
  const merged: WidgetConfig = {
    ...DEFAULTS,
    ...fromWindow,
    ...fromTag,
    brand: { ...DEFAULTS.brand, ...fromWindow.brand, ...fromTag.brand },
    contact: { ...DEFAULTS.contact, ...fromWindow.contact, ...fromTag.contact },
  } as WidgetConfig;
  if (merged.position !== "left") merged.position = "right";
  if (!Number.isFinite(merged.zIndex)) merged.zIndex = DEFAULTS.zIndex;
  merged.apiUrl = merged.apiUrl.replace(/\/+$/, "");
  return merged;
}

// ---------------------------------------------------------------------------
// Colour contrast (WCAG): pick readable colours from the brand placeholders
// ---------------------------------------------------------------------------

function luminance(hex: string): number {
  const m = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return 0;
  let h = m[1];
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  const channel = (i: number) => {
    const v = parseInt(h.slice(i, i + 2), 16) / 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * channel(0) + 0.7152 * channel(2) + 0.0722 * channel(4);
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

export interface Palette {
  primary: string;
  onPrimary: string; // text/icons on the primary colour
  accent: string;
  text: string;
  surface: string;
  link: string; // links inside bot replies
  focus: string; // focus ring
  muted: string; // secondary text (timestamps, subtitle on surface)
}

export function palette(config: WidgetConfig): Palette {
  const { primary, accent, text, surface } = config.brand;
  const onPrimary = contrast("#FFFFFF", primary) >= contrast("#111111", primary) ? "#FFFFFF" : "#111111";
  const link = contrast(primary, surface) >= 4.5 ? primary : text;
  const focus = contrast(accent, surface) >= 3 ? accent : primary; // UI components need 3:1
  const muted = contrast("#595959", surface) >= 4.5 ? "#595959" : text;
  if (contrast(text, surface) < 4.5) console.warn("[Coltek chat] brand.text on brand.surface is below 4.5:1 contrast");
  if (contrast(onPrimary, primary) < 4.5) console.warn("[Coltek chat] no readable text colour on brand.primary (4.5:1)");
  return { primary, onPrimary, accent, text, surface, link, focus, muted };
}
