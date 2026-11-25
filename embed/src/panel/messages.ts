import { icon } from "../icons";
import { renderMarkdown } from "../markdown";
import type { WidgetConfig } from "../types";

function el<K extends keyof HTMLElementTagNameMap>(tag: K, className = "", text = ""): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

/** Bot avatar: the logo, or the bot name's first letter if there's no logo or it fails to load. */
export function avatar(config: WidgetConfig): HTMLElement {
  const initials = () => {
    const span = el("span", "cc-avatar", (config.botName.trim()[0] || "C").toUpperCase());
    span.setAttribute("aria-hidden", "true");
    return span;
  };
  if (!config.logoUrl) return initials();
  const img = el("img", "cc-avatar");
  img.alt = "";
  img.src = config.logoUrl;
  img.addEventListener("error", () => img.replaceWith(initials()), { once: true });
  return img;
}

function timeLabel(date: Date): HTMLTimeElement {
  const time = el("time", "cc-time");
  time.dateTime = date.toISOString();
  time.textContent = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return time;
}

/** One bot reply while it is being written: typing dots -> status text -> streamed Markdown. */
export class BotMessage {
  readonly row = el("div", "cc-row cc-row-bot");
  private bubble = el("div", "cc-msg");
  private col = el("div", "cc-col");
  private text = "";
  private frame = 0;

  constructor(private list: MessageList, config: WidgetConfig) {
    this.row.appendChild(avatar(config));
    this.col.appendChild(this.bubble);
    this.row.appendChild(this.col);
    this.bubble.setAttribute("aria-busy", "true");
    this.typing();
  }

  typing(): void {
    this.text = "";
    this.bubble.setAttribute("aria-busy", "true");
    this.bubble.textContent = "";
    const dots = el("span", "cc-typing");
    dots.append(el("span"), el("span"), el("span"));
    const label = el("span", "cc-sr", "Typing");
    this.bubble.append(dots, label);
  }

  status(text: string): void {
    if (this.text) return; // once text is streaming, status updates are not shown
    this.bubble.textContent = "";
    this.bubble.appendChild(el("span", "cc-status", text));
    this.list.contentChanged();
  }

  append(delta: string): void {
    this.text += delta;
    if (!this.frame) {
      this.frame = requestAnimationFrame(() => {
        this.frame = 0;
        renderMarkdown(this.text, this.bubble);
        this.list.contentChanged();
      });
    }
  }

  /** "reset" event: an output guardrail blocked what was streamed so far. */
  reset(): void {
    this.text = "";
    cancelAnimationFrame(this.frame);
    this.frame = 0;
    this.typing();
  }

  finish(): void {
    cancelAnimationFrame(this.frame);
    this.frame = 0;
    renderMarkdown(this.text, this.bubble);
    this.bubble.setAttribute("aria-busy", "false");
    this.col.appendChild(timeLabel(new Date()));
    this.list.contentChanged();
  }

  error(message: string, onRetry: () => void): void {
    cancelAnimationFrame(this.frame);
    this.frame = 0;
    this.text = "";
    this.bubble.textContent = "";
    this.bubble.setAttribute("aria-busy", "false");
    const p = el("p", "cc-error", message);
    const retry = el("button", "cc-retry", "Retry");
    retry.type = "button";
    retry.addEventListener("click", onRetry, { once: true });
    this.bubble.append(p, retry);
    this.list.contentChanged();
  }

  remove(): void {
    this.row.remove();
  }

  get hasText(): boolean {
    return this.text.length > 0;
  }
}

/** The scrolling message list, with auto-scroll that pauses when the visitor scrolls up. */
export class MessageList {
  readonly scroller = el("div", "cc-scroll");
  readonly list = el("div", "cc-list");
  readonly pill = el("button", "cc-pill");
  private stick = true;

  constructor(private config: WidgetConfig) {
    this.list.setAttribute("role", "log");
    this.list.setAttribute("aria-live", "polite");
    this.list.setAttribute("aria-label", "Conversation");
    this.scroller.appendChild(this.list);
    this.pill.type = "button";
    this.pill.append(icon("down", 16), document.createTextNode("New message"));
    this.pill.addEventListener("click", () => this.scrollToBottom());
    this.scroller.addEventListener("scroll", () => {
      this.stick = this.distanceFromBottom() < 48;
      if (this.stick) this.pill.classList.remove("cc-show");
    }, { passive: true });
  }

  private distanceFromBottom(): number {
    return this.scroller.scrollHeight - this.scroller.scrollTop - this.scroller.clientHeight;
  }

  scrollToBottom(): void {
    this.stick = true;
    this.pill.classList.remove("cc-show");
    this.scroller.scrollTop = this.scroller.scrollHeight;
  }

  /** Call after content grows: follow it if the visitor is at the bottom, else offer the pill. */
  contentChanged(): void {
    if (this.stick) this.scroller.scrollTop = this.scroller.scrollHeight;
    else this.pill.classList.add("cc-show");
  }

  addUser(text: string, at = new Date()): HTMLElement {
    const row = el("div", "cc-row cc-row-user");
    const col = el("div", "cc-col");
    col.append(el("div", "cc-msg", text), timeLabel(at));
    row.appendChild(col);
    this.list.appendChild(row);
    this.scrollToBottom();
    return row;
  }

  /** A message waiting for the previous reply to finish: shown faded with "Waiting to send". */
  setQueued(row: HTMLElement, queued: boolean): void {
    row.classList.toggle("cc-queued", queued);
    const col = row.querySelector(".cc-col");
    const note = row.querySelector(".cc-queued-note");
    if (queued && !note && col) col.appendChild(el("span", "cc-queued-note", "Waiting to send…"));
    if (!queued && note) note.remove();
  }

  addBotText(text: string, at = new Date()): void {
    const row = el("div", "cc-row cc-row-bot");
    const col = el("div", "cc-col");
    const bubble = el("div", "cc-msg");
    renderMarkdown(text, bubble);
    col.append(bubble, timeLabel(at));
    row.append(avatar(this.config), col);
    this.list.appendChild(row);
    this.contentChanged();
  }

  /** A new bot reply, placed right under the visitor message it answers (so queued messages keep their order). */
  addBot(after?: HTMLElement): BotMessage {
    const message = new BotMessage(this, this.config);
    if (after && after.parentNode === this.list) after.after(message.row);
    else this.list.appendChild(message.row);
    this.contentChanged();
    return message;
  }

  clear(): void {
    this.list.textContent = "";
    this.pill.classList.remove("cc-show");
    this.stick = true;
  }
}
