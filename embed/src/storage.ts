// localStorage / sessionStorage wrapped in try/catch: they can throw in private mode or when blocked.
const THREAD_KEY = "coltek-chat:thread";
const GREETED_KEY = "coltek-chat:greeted";
const AUTO_OPENED_KEY = "coltek-chat:auto-opened";

function get(storage: () => Storage, key: string): string | null {
  try {
    return storage().getItem(key);
  } catch {
    return null;
  }
}

function set(storage: () => Storage, key: string, value: string | null): void {
  try {
    if (value === null) storage().removeItem(key);
    else storage().setItem(key, value);
  } catch {
    /* storage unavailable: the widget still works, it just forgets */
  }
}

const local = () => window.localStorage;
const session = () => window.sessionStorage;

export const storage = {
  threadId: () => get(local, THREAD_KEY),
  setThreadId: (id: string | null) => set(local, THREAD_KEY, id),
  greeted: () => get(local, GREETED_KEY) === "1",
  setGreeted: () => set(local, GREETED_KEY, "1"),
  autoOpened: () => get(session, AUTO_OPENED_KEY) === "1",
  setAutoOpened: () => set(session, AUTO_OPENED_KEY, "1"),
};
