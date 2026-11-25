import { palette } from "./config";
import { icon } from "./icons";
import type { ChatPanel } from "./panel/panel";
import { storage } from "./storage";
import { CSS } from "./styles";
import type { WidgetConfig } from "./types";

const GREETING_DELAY_MS = 5000;
const AUTO_OPEN_DELAY_MS = 20000;
const MOBILE = "(max-width: 639.98px)";

/**
 * <coltek-chat>: the launcher, greeting bubble and (built on first open) the chat panel,
 * all inside an open Shadow DOM so the website's CSS can't affect them.
 * CSP-friendly: no inline event handlers, no eval, styles only in the shadow root
 * (constructable stylesheet; a <style> element only as a fallback for old browsers).
 */
export class ColtekChatElement extends HTMLElement {
  private config!: WidgetConfig;
  private shell!: HTMLDivElement;
  private launcher!: HTMLButtonElement;
  private greet!: HTMLDivElement;
  private panel: ChatPanel | null = null;
  private createPanel!: (config: WidgetConfig, hooks: ConstructorParameters<typeof ChatPanel>[1]) => ChatPanel;
  private opened = false;
  private unread = false;
  private savedScroll: { y: number; styles: string[] } | null = null;
  private mobile = window.matchMedia(MOBILE);

  init(config: WidgetConfig, createPanel: typeof this.createPanel): void {
    this.config = config;
    this.createPanel = createPanel;
    const root = this.attachShadow({ mode: "open" });

    // Styles: constructable stylesheet (not affected by the site's CSP style-src); <style> fallback
    if ("adoptedStyleSheets" in Document.prototype && "replaceSync" in CSSStyleSheet.prototype) {
      const sheet = new CSSStyleSheet();
      sheet.replaceSync(CSS);
      root.adoptedStyleSheets = [sheet];
    } else {
      const style = document.createElement("style");
      style.textContent = CSS;
      root.appendChild(style);
    }

    // Colours as CSS variables on the host (set through CSSOM, which CSP allows)
    const colours = palette(config);
    const vars: Record<string, string> = {
      "--cc-primary": colours.primary, "--cc-on-primary": colours.onPrimary, "--cc-accent": colours.accent,
      "--cc-text": colours.text, "--cc-surface": colours.surface, "--cc-link": colours.link,
      "--cc-focus": colours.focus, "--cc-muted": colours.muted, "--cc-z": String(config.zIndex),
    };
    for (const [name, value] of Object.entries(vars)) this.style.setProperty(name, value);

    this.shell = document.createElement("div");
    this.shell.className = `cc cc-${config.position}`;
    root.appendChild(this.shell);
    this.buildLauncher();

    document.addEventListener("keydown", (event) => this.onKeydown(event));
    const onBreakpoint = () => this.applyMobileMode();
    if (this.mobile.addEventListener) this.mobile.addEventListener("change", onBreakpoint);

    if (!storage.greeted()) setTimeout(() => this.showGreeting(), GREETING_DELAY_MS);
    if (this.matchesAutoOpen() && !storage.autoOpened()) {
      setTimeout(() => {
        if (!this.opened && !this.mobile.matches && !storage.autoOpened()) {
          storage.setAutoOpened();
          this.open({ moveFocus: false }); // never steal focus from what the visitor is doing
        }
      }, AUTO_OPEN_DELAY_MS);
    }
  }

  // ------------------------------------------------------------------ launcher + greeting

  private buildLauncher(): void {
    this.launcher = document.createElement("button");
    this.launcher.type = "button";
    this.launcher.className = "cc-launcher";
    this.launcher.setAttribute("aria-expanded", "false");
    this.launcher.setAttribute("aria-controls", "coltek-chat-panel");
    this.updateLauncherLabel();
    const chat = icon("chat", 30);
    chat.classList.add("cc-i-chat");
    const close = icon("close", 28);
    close.classList.add("cc-i-close");
    const dot = document.createElement("span");
    dot.className = "cc-dot";
    this.launcher.append(chat, close, dot);
    this.launcher.addEventListener("click", () => (this.opened ? this.close() : this.open()));

    this.greet = document.createElement("div");
    this.greet.className = "cc-greet";
    this.greet.setAttribute("role", "status");
    const text = document.createElement("button");
    text.type = "button";
    text.className = "cc-greet-text";
    text.textContent = this.config.bubbleText;
    text.addEventListener("click", () => this.open());
    const dismiss = document.createElement("button");
    dismiss.type = "button";
    dismiss.className = "cc-greet-x";
    dismiss.setAttribute("aria-label", "Dismiss message");
    dismiss.appendChild(icon("close", 16));
    dismiss.addEventListener("click", () => this.hideGreeting());
    this.greet.append(text, dismiss);

    this.shell.append(this.greet, this.launcher);
  }

  private updateLauncherLabel(): void {
    const base = `Open chat with ${this.config.botName}`;
    this.launcher.setAttribute("aria-label", this.unread ? `${base} (new message)` : base);
  }

  private showGreeting(): void {
    if (this.opened || storage.greeted()) return;
    storage.setGreeted(); // shown once, ever (per browser)
    this.greet.classList.add("cc-show");
  }

  private hideGreeting(): void {
    this.greet.classList.remove("cc-show");
    storage.setGreeted();
  }

  setUnread(on: boolean): void {
    this.unread = on;
    this.shell.classList.toggle("cc-unread", on);
    this.updateLauncherLabel();
  }

  private matchesAutoOpen(): boolean {
    const path = window.location.pathname;
    return this.config.autoOpenPaths.some((p) => p && (path === p || path.startsWith(p.endsWith("/") ? p : `${p}/`)));
  }

  // ------------------------------------------------------------------ open / close

  open(options: { moveFocus?: boolean } = {}): void {
    if (this.opened) return;
    if (!this.panel) {
      // First open: build the panel now (keeps page load light)
      this.panel = this.createPanel(this.config, {
        isOpen: () => this.opened,
        close: () => this.close(),
        replyWhileClosed: () => this.setUnread(true),
      });
      this.shell.insertBefore(this.panel.el, this.greet);
    }
    this.opened = true;
    this.hideGreeting();
    this.setUnread(false);
    this.shell.classList.add("cc-open");
    this.launcher.setAttribute("aria-expanded", "true");
    this.panel.setVisible(true);
    this.applyMobileMode();
    if (options.moveFocus !== false) {
      // wait a frame so the panel is visible (focus on hidden elements is ignored)
      requestAnimationFrame(() => this.panel?.focusInput());
    }
  }

  close(): void {
    if (!this.opened || !this.panel) return;
    this.opened = false;
    this.shell.classList.remove("cc-open");
    this.launcher.setAttribute("aria-expanded", "false");
    this.panel.setVisible(false);
    this.applyMobileMode();
    this.launcher.focus();
  }

  private onKeydown(event: KeyboardEvent): void {
    if (!this.opened || !this.panel) return;
    if (event.key === "Escape") {
      if (!this.panel.closeOverlays()) this.close();
      event.stopPropagation();
    } else if (event.key === "Tab" && this.mobile.matches) {
      this.trapFocus(event); // full screen on phones behaves like a modal dialog
    }
  }

  private trapFocus(event: KeyboardEvent): void {
    const focusable = Array.from(
      this.panel!.el.querySelectorAll<HTMLElement>("button:not([disabled]), a[href], textarea, [tabindex]:not([tabindex='-1'])"),
    ).filter((node) => node.offsetParent !== null);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const active = this.shadowRoot!.activeElement;
    if (event.shiftKey && active === first) {
      last.focus();
      event.preventDefault();
    } else if (!event.shiftKey && active === last) {
      first.focus();
      event.preventDefault();
    }
  }

  // ------------------------------------------------------------------ phones: full screen

  /** Lock page scroll and follow the on-screen keyboard while open full screen on a phone. */
  private applyMobileMode(): void {
    const fullScreen = this.opened && this.mobile.matches;
    this.panel?.el.setAttribute("aria-modal", fullScreen ? "true" : "false");
    const viewport = window.visualViewport;
    if (fullScreen) {
      this.lockScroll();
      if (viewport) {
        viewport.addEventListener("resize", this.onViewport);
        viewport.addEventListener("scroll", this.onViewport);
      }
      this.onViewport();
    } else {
      this.unlockScroll();
      if (viewport) {
        viewport.removeEventListener("resize", this.onViewport);
        viewport.removeEventListener("scroll", this.onViewport);
      }
      this.style.removeProperty("--cc-vv-height");
      this.style.removeProperty("--cc-vv-top");
    }
  }

  /** The visual viewport shrinks when the keyboard opens (iPhone and Android): size the panel to it. */
  private onViewport = (): void => {
    const viewport = window.visualViewport;
    if (!viewport) return;
    this.style.setProperty("--cc-vv-height", `${Math.round(viewport.height)}px`);
    this.style.setProperty("--cc-vv-top", `${Math.round(viewport.offsetTop)}px`);
    this.panel?.keepBottomVisible();
  };

  private lockScroll(): void {
    if (this.savedScroll) return;
    const body = document.body.style;
    this.savedScroll = { y: window.scrollY, styles: [body.position, body.top, body.left, body.right, body.width, document.documentElement.style.overflow] };
    // position:fixed on <body> is what reliably stops iOS Safari scrolling the page behind
    body.position = "fixed";
    body.top = `-${this.savedScroll.y}px`;
    body.left = "0";
    body.right = "0";
    body.width = "100%";
    document.documentElement.style.overflow = "hidden";
  }

  private unlockScroll(): void {
    if (!this.savedScroll) return;
    const body = document.body.style;
    const [position, top, left, right, width, overflow] = this.savedScroll.styles;
    Object.assign(body, { position, top, left, right, width });
    document.documentElement.style.overflow = overflow;
    window.scrollTo(0, this.savedScroll.y);
    this.savedScroll = null;
  }
}
