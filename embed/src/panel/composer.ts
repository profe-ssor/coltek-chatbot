import { icon } from "../icons";

export const MAX_LENGTH = 2000;
const COUNTER_FROM = 1800; // show "1850 / 2000" near the limit

/** Message input: auto-growing textarea, Enter sends, Shift+Enter adds a line, 2000-character limit.
 *  Visitors can keep sending while a reply is still coming: the panel queues the messages. */
export class Composer {
  readonly el = document.createElement("form");
  readonly input = document.createElement("textarea");
  private send = document.createElement("button");
  private counter = document.createElement("p");
  readonly privacy = document.createElement("p");
  private full = false; // true only when the panel's send queue is full

  /** onSend returns false if the message could not be accepted (queue full): the text then stays in the box. */
  constructor(onSend: (text: string) => boolean, privacyPolicyUrl: string) {
    this.el.className = "cc-composer";
    this.el.noValidate = true;

    const row = document.createElement("div");
    row.className = "cc-input-row";

    this.input.className = "cc-input";
    this.input.rows = 1;
    this.input.maxLength = MAX_LENGTH;
    this.input.placeholder = "Type your message...";
    this.input.setAttribute("aria-label", "Type your message");
    this.input.setAttribute("enterkeyhint", "send");

    this.send.type = "submit";
    this.send.className = "cc-send";
    this.send.setAttribute("aria-label", "Send message");
    this.send.appendChild(icon("send", 20));

    this.counter.className = "cc-counter";
    this.counter.setAttribute("aria-live", "polite");

    this.privacy.className = "cc-privacy";
    this.privacy.textContent = "Messages are stored to help us respond. Don't share passwords or PINs.";
    if (privacyPolicyUrl) {
      const link = document.createElement("a");
      link.href = privacyPolicyUrl;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = "Privacy policy";
      this.privacy.append(" ", link);
    }

    row.append(this.input, this.send);
    this.el.append(row, this.counter, this.privacy);

    this.input.addEventListener("input", () => this.update());
    this.input.addEventListener("keydown", (event) => {
      // Enter sends; Shift+Enter is a new line; never send while an IME is composing (e.g. Twi keyboards)
      if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        this.submit(onSend);
      }
    });
    this.el.addEventListener("submit", (event) => {
      event.preventDefault();
      this.submit(onSend);
    });
    this.update();
  }

  private submit(onSend: (text: string) => boolean): void {
    const text = this.input.value.trim();
    if (!text) return;
    if (!onSend(text)) return; // the panel refused (queue full) and shows why; the text stays in the box
    this.input.value = "";
    this.update();
  }

  private update(): void {
    // auto-grow up to the CSS max-height (only once it's on the page: before that scrollHeight is 0)
    if (this.input.isConnected && this.input.scrollHeight > 0) {
      this.input.style.height = "auto";
      this.input.style.height = `${this.input.scrollHeight}px`;
    }
    const length = this.input.value.length;
    this.counter.textContent = `${length} / ${MAX_LENGTH}`;
    this.counter.classList.toggle("cc-show", length >= COUNTER_FROM);
    this.send.disabled = this.full || !this.input.value.trim();
  }

  /** Disable sending only while the queue of waiting messages is full. */
  setFull(full: boolean): void {
    this.full = full;
    this.update();
  }

  showPrivacy(show: boolean): void {
    this.privacy.classList.toggle("cc-show", show);
  }

  focus(): void {
    this.input.focus({ preventScroll: true });
  }
}
