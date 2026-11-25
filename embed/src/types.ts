export interface Brand {
  primary: string; // launcher, header, visitor bubbles, send button
  accent: string; // unread dot, focus ring (when it has enough contrast)
  text: string; // body text
  surface: string; // panel background
}

export interface Contact {
  phone: string; // shown as a tel: link
  whatsapp: string; // number, opened as https://wa.me/<digits>
  email: string; // shown as a mailto: link
}

export interface WidgetConfig {
  apiUrl: string; // base URL of the chat API, e.g. "https://chat.coltektechnologies.io"
  brand: Brand;
  logoUrl: string; // "" = initials avatar
  botName: string;
  position: "right" | "left";
  greeting: string; // welcome screen text
  bubbleText: string; // greeting bubble next to the launcher (first visit only)
  starterPrompts: string[];
  autoOpenPaths: string[]; // open automatically after 20 s on these paths (desktop only)
  contact: Contact;
  privacyPolicyUrl: string; // "" = no link
  zIndex: number;
  debug: boolean; // log "agent" events etc. to the console
}

/** Server-Sent Events from POST /api/chat (see server/chat_service.py). */
export type ChatEvent =
  | { type: "start"; thread_id: string }
  | { type: "agent"; name: string } // debug only: never shown to visitors
  | { type: "status"; text: string }
  | { type: "delta"; text: string }
  | { type: "reset" }
  | { type: "done"; message_id: string; agent: string }
  | { type: "error"; text: string };

export interface HistoryMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  blocked: boolean;
}
