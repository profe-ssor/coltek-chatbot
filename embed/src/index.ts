// Entry point: read the config, define <coltek-chat>, add it to the page.
// One classic script; the panel code is in this file but only *built* on first open.
import { readConfig } from "./config";
import { ColtekChatElement } from "./element";
import { ChatPanel } from "./panel/panel";

const script = document.currentScript; // must be read while the script is executing

function boot(): void {
  if (document.querySelector("coltek-chat")) return; // never add two widgets
  const config = readConfig(script);
  if (!customElements.get("coltek-chat")) customElements.define("coltek-chat", ColtekChatElement);
  const widget = document.createElement("coltek-chat") as ColtekChatElement;
  widget.init(config, (cfg, hooks) => new ChatPanel(cfg, hooks));
  document.body.appendChild(widget);
  (window as unknown as { ColtekChat: unknown }).ColtekChat = {
    open: () => widget.open(),
    close: () => widget.close(),
  };
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
else boot();
