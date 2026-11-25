# Coltek chat widget (`embed/`)

The floating "Coltek Assistant" chat for coltektechnologies.io, the Academy site and open-door.site.

- **One classic script, `dist/coltek-chat.js`.** It's about 12 KB gzipped, and the build fails over 25 KB.
- **No dependencies, no UI library and no ChatKit.**
- **It's a Web Component (`<coltek-chat>`) inside an open Shadow DOM,** so the website's CSS can't break it and it can't change the website.
- **It talks to our chat API in `server/`** (`/api/threads`, `/api/threads/{id}/messages`, `/api/chat` with Server-Sent Events).
- **The launcher is tiny at page load.** The chat panel is only built the first time a visitor opens it.

## Build

Node 18+ is needed only to build; the websites don't need Node.

```bash
cd embed
npm install          # once (Vite + TypeScript, dev-only)
npm run build        # type-check → build dist/coltek-chat.js → size check (fails over 25 KB gzipped)
```

Source in `src/`:

| File | What it does |
|---|---|
| `index.ts` | Reads the config, defines `<coltek-chat>` and adds it to the page |
| `element.ts` | Launcher, greeting bubble, unread dot, open/close, Escape, focus, full screen on phones, keyboard handling (`visualViewport`), scroll lock |
| `panel/panel.ts` | Header, menu ("Start new conversation", "Talk to a person"), welcome screen, the send queue (up to 3 messages waiting while a reply streams), Retry, offline handling |
| `panel/messages.ts` | Message bubbles, bot avatar (logo or initials), timestamps on hover, auto-scroll and the "New message" pill |
| `panel/composer.ts` | Auto-growing input; Enter sends, Shift+Enter adds a new line; 2000-character limit with a counter; privacy line |
| `api.ts`, `sse.ts` | `fetch` with `credentials: "include"`, and an SSE stream reader (we POST, so `EventSource` can't be used) |
| `markdown.ts` | Safe Markdown → DOM (bold, italic, code, lists, links). It never uses `innerHTML` |
| `config.ts`, `styles.ts`, `icons.ts`, `storage.ts`, `types.ts` | Settings and colour contrast, CSS, SVG icons, localStorage, types |

## Add it to a website

1. **Host the file.** Serve `dist/coltek-chat.js` from one place, for example `https://chat.coltektechnologies.io/widget/coltek-chat.js` (Nginx, next to the API). All three sites can load it from there.
2. **Paste [`snippet.html`](snippet.html) just before `</body>` on every page:**
   - **Plain HTML:** in every page, or in the shared footer include.
   - **WordPress:** in the theme's `footer.php` before `wp_footer()`, or with a "header and footer scripts" plugin. The script tag doesn't use `type="module"`, so minify/caching plugins can't break it.
   - **Angular / React / Vue:** in `index.html` (`src/index.html` or `public/index.html`), not inside a component.
3. **Set `data-api-url`** to the chat API, for example `https://chat.coltektechnologies.io`.
4. **On the server,** add every site's origin to `ALLOWED_ORIGINS` in `.env`:
   ```
   ALLOWED_ORIGINS=https://coltektechnologies.io,https://www.coltektechnologies.io,https://coltekacademy.coltektechnologies.io,https://open-door.site,https://www.open-door.site
   ```
5. **On iPhones,** the widget avoids the notch and the home bar only if the page's viewport tag has `viewport-fit=cover`:
   ```html
   <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
   ```

**How each site starts the conversation:**
- The widget sends the page's **host + path** (never the query string) with every request.
  - A page whose host or path contains `academy` (the whole Academy site) starts with the Academy advisor.
  - `open-door.site` starts with the OpenDoor specialist.
  - Everything else starts with the main assistant.
- After the first reply, the conversation stays with whoever answered last.

## Brand colours, logo and other settings

Set them as `data-*` attributes on the script tag, or in `window.ColtekChatConfig = {...}` set before the script. `data-*` wins. Leave anything out to keep its default.

| `data-*` attribute | `ColtekChatConfig` key | Default |
|---|---|---|
| `data-api-url` | `apiUrl` | `https://chat.coltektechnologies.io` |
| `data-primary` / `data-accent` / `data-text` / `data-surface` | `brand.primary` / `.accent` / `.text` / `.surface` | `#0B2545` / `#13C4A3` / `#1B1B1B` / `#FFFFFF` (placeholders until the real colours arrive) |
| `data-logo-url` | `logoUrl` | `""`, which shows a "C" avatar. A logo that fails to load also falls back to "C" |
| `data-bot-name` | `botName` | `Coltek Assistant` |
| `data-position` | `position` | `right` (`left` if a WhatsApp button already sits bottom-right) |
| `data-greeting` | `greeting` | The welcome-screen text |
| `data-bubble-text` | `bubbleText` | "Hi! Need help with a website, a course or OpenDoor?" |
| `data-starter-prompts` | `starterPrompts` | The 3 chips, separated by `\|` in the attribute |
| `data-auto-open-paths` | `autoOpenPaths` | none. For example `/academy,/pricing` opens the chat after 20 s, on desktop only, once per visit |
| `data-phone` / `data-whatsapp` / `data-email` | `contact.*` | `+233 54 936 1771` / `+233549361771` / `coltektechnologies@gmail.com` ("Talk to a person") |
| `data-privacy-policy-url` | `privacyPolicyUrl` | none. If set, it adds a "Privacy policy" link under the composer |
| `data-z-index` | `zIndex` | `2147483000` |
| `data-debug` | `debug` | `false`. `true` logs which agent replied to the browser console. Visitors never see agent names |

**Readable colours are picked automatically:**
- The text on the primary colour is white or near-black, whichever passes 4.5:1 contrast.
- The focus ring falls back to the primary colour if the accent is too light (it needs 3:1).
- If the brand text colour on the surface colour is below 4.5:1, the browser console shows a warning.

You can also open or close the chat from your own buttons with `ColtekChat.open()` and `ColtekChat.close()`. Attach these in your own script file, not in an inline `onclick`, if the site has a strict CSP.

## Content Security Policy

The widget uses no inline scripts, no inline event handlers and no `eval`. Its styles live only inside its Shadow DOM, as a constructable stylesheet that CSP doesn't block. `demo.html` runs it under `default-src 'self'; script-src 'self'; style-src 'self'`.

If a site sends a CSP header, it needs:

| Directive | Add | Why |
|---|---|---|
| `script-src` | `https://chat.coltektechnologies.io` (wherever `coltek-chat.js` is hosted) | Load the widget |
| `connect-src` | `https://chat.coltektechnologies.io` | The chat API (fetch and streaming) |
| `img-src` | The host of `logoUrl`, if it's on another domain | The bot avatar |
| `style-src` | Nothing for current browsers | Older browsers without constructable stylesheets (Safari before 16.4) fall back to a `<style>` element, which needs `'unsafe-inline'`. Without it, the widget shows unstyled there |

If you use `window.ColtekChatConfig` in an inline `<script>`, that script needs a nonce or hash. Using `data-*` attributes avoids it.

## ⚠️ Cookie note for open-door.site (Safari and iPhone)

- **The visitor is identified by an httpOnly cookie from the chat API.**
- **The problem:** when the API is on `chat.coltektechnologies.io` and the page is on `open-door.site`, that cookie is third-party. **Safari, and every iPhone browser, blocks it**, so each request looks like a new visitor and the conversation breaks after the first message.
- **Not affected:** coltektechnologies.io and the Academy subdomain, where the cookie is first-party.
- **Fix before launching on open-door.site,** pick one:
  - **(a)** Serve the same API also as `chat.open-door.site`, and point that site's `data-api-url` there.
  - **(b)** Add a header-based visitor ID fallback to the API and the widget.

## Run the demo locally

```bash
# Terminal 1: the chat API (⚠️ every message uses the OpenAI key)
cd ~/Desktop/coltek-chatbot && source venv/bin/activate
uvicorn server.main:app --reload --port 8000

# Terminal 2: build the widget and serve this folder
cd ~/Desktop/coltek-chatbot/embed && npm run build
python3 -m http.server 5500
```

Open **http://localhost:5500/demo.html**. Use `localhost`, not `127.0.0.1`, so the cookie is sent. `http://localhost:5500` is in `ALLOWED_ORIGINS` by default.

The demo page has deliberately loud site styles, a fake WhatsApp button in the bottom-left corner, and a strict CSP. To see the greeting bubble again, clear the site's storage (DevTools → Application → Clear storage).

## Test checklist

**Browsers**
- [ ] Desktop Chrome, Firefox, Safari and Edge
- [ ] Android Chrome (real phone)
- [ ] iPhone Safari (real phone; also see the cookie note above)

**Launcher and greeting**
- [ ] The launcher shows bottom-right (or left), 24px from the edges, and nothing on the site covers it.
- [ ] It doesn't overlap the WhatsApp button or a cookie banner. If it does, use `data-position="left"` or adjust the site.
- [ ] The greeting bubble appears after 5 s on the **first** visit only. It doesn't come back after a refresh, whether you dismissed it or not.
- [ ] Clicking the bubble text opens the chat.

**Conversation**
- [ ] On first open: the welcome text, 3 chips and the privacy line show. Tapping a chip sends it.
- [ ] The reply streams in. A list and a link render properly, and the link opens in a new tab.
- [ ] While a tool runs, a friendly status shows ("Checking course details...", "Booking your demo..."), never a tool name.
- [ ] You can keep sending while a reply is still coming. New messages show at once as "Waiting to send…" and are answered one after another, each reply directly under its message.
- [ ] With 3 messages waiting, a 4th stays in the box with "Please wait a moment for a reply before sending more."
- [ ] If a message fails, the ones after it wait. After Retry they go through in order.
- [ ] Enter sends. Shift+Enter adds a new line. The counter appears near 2000 characters.
- [ ] **Refresh the page and reopen: the conversation is still there.**
- [ ] **Menu → "Start new conversation":** the chat is cleared and the welcome screen returns. The old conversation doesn't come back after a refresh.
- [ ] **Menu → "Talk to a person":** the phone, WhatsApp and email links work.
- [ ] Stop the API, then send: an error with **Retry** appears. Start the API and press Retry: one reply, and no duplicate message in the history after a refresh.
- [ ] Turn the network off (DevTools → Offline): "You're offline. We'll try again when you're back." It retries when you're back online.
- [ ] Send a message, close the panel before the reply ends: **an unread dot** appears on the launcher.

**Phones (under 640px)**
- [ ] The panel opens full screen, and the page behind it doesn't scroll.
- [ ] With the keyboard open, the message box stays visible above it (iPhone and Android).
- [ ] Nothing hides under the notch or the home bar (needs `viewport-fit=cover`).
- [ ] Tapping the message box doesn't zoom the page (the input font is 16px).
- [ ] Closing returns the page to the same scroll position.

**Keyboard only and screen readers**
- [ ] Tab reaches the launcher, and the focus ring is visible.
- [ ] Enter opens the chat, with focus in the message box. Escape closes it, with focus back on the launcher.
- [ ] In the menu or the "Talk to a person" panel, Escape closes that first.
- [ ] A screen reader announces "Open chat with Coltek Assistant", expanded or collapsed, and new replies (the message list is `aria-live="polite"`).

**No clashes**
- [ ] The site's fonts, buttons and colours look unchanged with the widget on the page.
- [ ] The widget looks the same on all three sites.
- [ ] With "Reduce motion" turned on in the operating system, nothing animates.
