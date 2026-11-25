import { ApiError, ChatApi, newClientMessageId } from "../api";
import { icon } from "../icons";
import { storage } from "../storage";
import type { ChatEvent, WidgetConfig } from "../types";
import { Composer } from "./composer";
import { BotMessage, MessageList, avatar } from "./messages";

const GENERIC_ERROR = "Sorry, something went wrong.";
const OFFLINE_TEXT = "You're offline. We'll try again when you're back.";

interface PanelHooks {
  isOpen: () => boolean;
  close: () => void;
  replyWhileClosed: () => void;
}

interface PendingSend {
  text: string;
  clientMessageId: string;
  userRow: HTMLElement; // the visitor's bubble
  bot: BotMessage | null; // created when this message's turn comes (right under userRow)
}

const MAX_QUEUED = 3; // messages that can wait while a reply is still coming
const QUEUE_FULL_TEXT = "Please wait a moment for a reply before sending more.";

function el<K extends keyof HTMLElementTagNameMap>(tag: K, className = "", text = ""): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

/** The chat panel. Built only the first time the visitor opens the chat. */
export class ChatPanel {
  readonly el = el("div", "cc-panel");
  private api: ChatApi;
  private messages: MessageList;
  private composer: Composer;
  private welcome = el("div", "cc-welcome");
  private notice = el("p", "cc-notice");
  private menu = el("div", "cc-menu");
  private menuButton = el("button", "cc-icon-btn");
  private sheet = el("section", "cc-sheet");
  private threadId: string | null = null;
  private threadReady: Promise<void> | null = null;
  private streaming = false;
  private controller: AbortController | null = null;
  private waitingForOnline: PendingSend | null = null;
  private queue: PendingSend[] = []; // sent while a reply was still streaming, in order
  private paused = false; // a message failed: the queue waits for Retry (or for the network to return)

  constructor(private config: WidgetConfig, private hooks: PanelHooks) {
    this.api = new ChatApi(config.apiUrl);
    this.messages = new MessageList(config);
    this.composer = new Composer((text) => this.send(text), config.privacyPolicyUrl);

    this.el.id = "coltek-chat-panel";
    this.el.setAttribute("role", "dialog");
    this.el.setAttribute("aria-label", `Chat with ${config.botName}`);
    this.el.setAttribute("aria-hidden", "true");
    this.el.inert = true;

    const body = el("div", "cc-body");
    this.notice.setAttribute("role", "status");
    this.buildWelcome();
    this.messages.list.before(this.welcome);
    body.append(this.messages.scroller, this.messages.pill, this.sheet);
    this.buildSheet();

    const footer = el("p", "cc-foot", "Powered by Coltek Technologies");
    this.el.append(this.buildHeader(), body, this.notice, this.composer.el, footer);

    window.addEventListener("online", () => this.onOnline());
    window.addEventListener("offline", () => this.showNotice(OFFLINE_TEXT));
    this.el.addEventListener("click", (event) => {
      if (!this.menu.contains(event.target as Node) && event.target !== this.menuButton &&
          !this.menuButton.contains(event.target as Node)) this.closeMenu();
    });
  }

  // ------------------------------------------------------------------ building

  private buildHeader(): HTMLElement {
    const head = el("div", "cc-head");
    const text = el("div", "cc-head-text");
    text.append(el("p", "cc-title", this.config.botName), el("p", "cc-sub", "Usually replies instantly"));

    this.menuButton.type = "button";
    this.menuButton.setAttribute("aria-label", "More options");
    this.menuButton.setAttribute("aria-haspopup", "true");
    this.menuButton.setAttribute("aria-expanded", "false");
    this.menuButton.appendChild(icon("menu", 22));
    this.menuButton.addEventListener("click", () => (this.menu.classList.contains("cc-show") ? this.closeMenu() : this.openMenu()));

    const newChat = el("button", "", "Start new conversation");
    newChat.type = "button";
    newChat.addEventListener("click", () => {
      this.closeMenu();
      void this.startNewConversation();
    });
    const person = el("button", "", "Talk to a person");
    person.type = "button";
    person.addEventListener("click", () => {
      this.closeMenu();
      this.openSheet();
    });
    this.menu.append(newChat, person);

    const minimise = el("button", "cc-icon-btn");
    minimise.type = "button";
    minimise.setAttribute("aria-label", "Minimise chat");
    minimise.appendChild(icon("minimise", 22));
    minimise.addEventListener("click", () => this.hooks.close());

    head.append(avatar(this.config), text, this.menuButton, minimise, this.menu);
    return head;
  }

  private buildWelcome(): void {
    this.welcome.appendChild(el("p", "cc-welcome-text", this.config.greeting));
    const chips = el("div", "cc-chips");
    for (const prompt of this.config.starterPrompts) {
      const chip = el("button", "cc-chip", prompt);
      chip.type = "button";
      chip.addEventListener("click", () => this.send(prompt));
      chips.appendChild(chip);
    }
    this.welcome.appendChild(chips);
  }

  private buildSheet(): void {
    const { phone, whatsapp, email } = this.config.contact;
    this.sheet.setAttribute("aria-label", "Talk to a person");
    this.sheet.append(el("h2", "", "Talk to a person"), el("p", "", "Our team is happy to help. Reach us directly:"));
    const contact = (href: string, iconName: "phone" | "whatsapp" | "mail", label: string) => {
      const a = el("a", "cc-contact");
      a.href = href;
      if (href.startsWith("https:")) {
        a.target = "_blank";
        a.rel = "noopener noreferrer";
      }
      a.append(icon(iconName, 20), document.createTextNode(label));
      this.sheet.appendChild(a);
    };
    if (phone) contact(`tel:${phone.replace(/[^\d+]/g, "")}`, "phone", `Call ${phone}`);
    if (whatsapp) contact(`https://wa.me/${whatsapp.replace(/\D/g, "")}`, "whatsapp", "Chat on WhatsApp");
    if (email) contact(`mailto:${email}`, "mail", email);
    const close = el("button", "cc-sheet-close", "Back to chat");
    close.type = "button";
    close.addEventListener("click", () => this.closeSheet());
    this.sheet.appendChild(close);
  }

  // ------------------------------------------------------------------ menu / sheet

  private openMenu(): void {
    this.menu.classList.add("cc-show");
    this.menuButton.setAttribute("aria-expanded", "true");
    (this.menu.querySelector("button") as HTMLButtonElement | null)?.focus();
  }

  closeMenu(): boolean {
    if (!this.menu.classList.contains("cc-show")) return false;
    this.menu.classList.remove("cc-show");
    this.menuButton.setAttribute("aria-expanded", "false");
    return true;
  }

  private openSheet(): void {
    this.sheet.classList.add("cc-show");
    (this.sheet.querySelector("a, button") as HTMLElement | null)?.focus();
  }

  closeSheet(): boolean {
    if (!this.sheet.classList.contains("cc-show")) return false;
    this.sheet.classList.remove("cc-show");
    this.composer.focus();
    return true;
  }

  /** Escape: close the menu or contact sheet first. Returns true if something was closed. */
  closeOverlays(): boolean {
    return this.closeMenu() || this.closeSheet();
  }

  // ------------------------------------------------------------------ open / visibility

  setVisible(visible: boolean): void {
    this.el.setAttribute("aria-hidden", visible ? "false" : "true");
    this.el.inert = !visible;
    if (visible && !this.threadReady) this.threadReady = this.loadThread();
    if (!visible) this.closeOverlays();
  }

  focusInput(): void {
    this.composer.focus();
  }

  /** Keep the newest message visible after the on-screen keyboard resizes the view. */
  keepBottomVisible(): void {
    this.messages.contentChanged();
  }

  private showNotice(text: string | null): void {
    this.notice.textContent = text || "";
    this.notice.classList.toggle("cc-show", Boolean(text));
  }

  private showWelcome(show: boolean): void {
    this.welcome.hidden = !show;
    this.composer.showPrivacy(show);
  }

  // ------------------------------------------------------------------ threads

  /** First open: reload the saved conversation, or create a new thread. */
  private async loadThread(): Promise<void> {
    this.showWelcome(true);
    try {
      const saved = storage.threadId();
      if (saved) {
        const history = await this.api.getMessages(saved);
        if (history) {
          this.threadId = saved;
          for (const message of history) {
            const at = new Date(message.created_at);
            if (message.role === "user") this.messages.addUser(message.content, at);
            else this.messages.addBotText(message.content, at);
          }
          this.showWelcome(history.length === 0);
          this.messages.scrollToBottom();
          return;
        }
        storage.setThreadId(null); // 404: gone or not ours any more
      }
      this.threadId = await this.api.createThread();
      storage.setThreadId(this.threadId);
    } catch {
      this.threadReady = null; // try again on the next send / open
      this.showNotice(navigator.onLine ? "We couldn't connect to the chat. Please try again." : OFFLINE_TEXT);
    }
  }

  private async startNewConversation(): Promise<void> {
    this.controller?.abort();
    this.streaming = false;
    this.queue = [];
    this.paused = false;
    this.composer.setFull(false);
    this.waitingForOnline = null;
    this.messages.clear();
    this.showWelcome(true);
    this.showNotice(null);
    try {
      this.threadId = await this.api.createThread();
      storage.setThreadId(this.threadId);
    } catch {
      this.threadId = null;
      storage.setThreadId(null);
      this.threadReady = null;
      this.showNotice("We couldn't start a new conversation. Please try again.");
    }
    this.composer.focus();
  }

  // ------------------------------------------------------------------ sending

  /**
   * Called by the composer and the starter chips. The visitor can keep sending while a reply is
   * still coming: the message is shown at once and queued. The server allows one reply at a time
   * per conversation (so the AI's memory stays in order), so queued messages go one after another.
   * Returns false if the queue is full (the text then stays in the input box).
   */
  private send(text: string): boolean {
    if (this.queue.length >= MAX_QUEUED) {
      this.showNotice(QUEUE_FULL_TEXT);
      return false;
    }
    this.showWelcome(false);
    const userRow = this.messages.addUser(text);
    this.queue.push({ text, clientMessageId: newClientMessageId(), userRow, bot: null });
    this.refreshQueue();
    void this.processQueue();
    return true;
  }

  /** Mark waiting messages, and stop accepting more while the queue is full. */
  private refreshQueue(): void {
    for (const pending of this.queue) this.messages.setQueued(pending.userRow, true);
    this.composer.setFull(this.queue.length >= MAX_QUEUED);
    if (this.queue.length < MAX_QUEUED && this.notice.textContent === QUEUE_FULL_TEXT) this.showNotice(null);
  }

  /** Send the next queued message, if no reply is streaming and nothing is waiting for Retry. */
  private async processQueue(): Promise<void> {
    if (this.streaming || this.paused) return;
    const next = this.queue.shift();
    if (!next) return;
    this.messages.setQueued(next.userRow, false);
    this.refreshQueue();
    if (next.bot) next.bot.typing();
    else next.bot = this.messages.addBot(next.userRow);
    await this.run(next);
    void this.processQueue();
  }

  /** Send (or re-send, on Retry) one message. The same clientMessageId makes a retry safe on the server. */
  private async run(pending: PendingSend): Promise<void> {
    const bot = pending.bot as BotMessage;
    this.streaming = true;
    if (this.notice.textContent !== QUEUE_FULL_TEXT) this.showNotice(null);
    let finished = false;
    try {
      if (!this.threadId) {
        this.threadReady = this.threadReady || this.loadThread();
        await this.threadReady;
        if (!this.threadId) throw new ApiError(0, "network");
      }
      this.controller = new AbortController();
      const events = this.api.sendMessage(
        { threadId: this.threadId, message: pending.text, clientMessageId: pending.clientMessageId },
        this.controller.signal,
      );
      for await (const event of events) {
        finished = this.handle(event, pending, bot) || finished;
      }
      if (!finished) throw new ApiError(0, "network"); // stream ended without done/error
    } catch (error) {
      if ((error as { name?: string }).name === "AbortError") return;
      this.failed(pending, bot, error);
    } finally {
      this.streaming = false;
      this.controller = null;
    }
  }

  /** Returns true when the turn is over (done or error event). */
  private handle(event: ChatEvent, pending: PendingSend, bot: BotMessage): boolean {
    switch (event.type) {
      case "agent":
        if (this.config.debug) console.debug("[Coltek chat] agent:", event.name); // never shown to visitors
        return false;
      case "status":
        bot.status(event.text);
        return false;
      case "delta":
        bot.append(event.text);
        return false;
      case "reset":
        bot.reset();
        return false;
      case "done":
        bot.finish();
        if (!this.hooks.isOpen()) this.hooks.replyWhileClosed();
        return true;
      case "error":
        this.paused = true; // keep later messages waiting (in order) until Retry
        bot.error(event.text || GENERIC_ERROR, () => this.retry(pending));
        return true;
      default:
        return false; // "start" and anything new
    }
  }

  private failed(pending: PendingSend, bot: BotMessage, error: unknown): void {
    this.paused = true; // later messages wait, in order, until this one gets through
    if (!navigator.onLine) {
      this.waitingForOnline = pending; // sent again automatically when the network is back
      this.showNotice(OFFLINE_TEXT);
      bot.error(OFFLINE_TEXT, () => this.retry(pending));
      return;
    }
    const message = error instanceof ApiError && error.message && error.message !== "network"
      ? error.message                                         // the server's friendly text (429, 409, 422)
      : GENERIC_ERROR + " Please try again.";
    bot.error(message, () => this.retry(pending));
  }

  /** Retry a failed message first, then carry on with the queue. Same clientMessageId: never sent twice. */
  private retry(pending: PendingSend): void {
    this.waitingForOnline = null;
    this.paused = false;
    if (!this.queue.includes(pending)) this.queue.unshift(pending);
    void this.processQueue();
  }

  private onOnline(): void {
    this.showNotice(null);
    if (this.waitingForOnline) this.retry(this.waitingForOnline);
  }
}
