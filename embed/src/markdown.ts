// Tiny, safe Markdown renderer for bot replies. Builds DOM nodes with textContent only:
// never innerHTML, so nothing in a reply can inject HTML or scripts.
// Supports: paragraphs, line breaks, **bold**, *italic*, `code`, bullet and numbered
// lists, [links](https://...) and bare https:// URLs. Links: http(s), mailto and tel only.

const SAFE_PROTOCOL = /^(https?:|mailto:|tel:)/i;
const INLINE = /(\*\*[^*]+\*\*|`[^`\n]+`|\[[^\]\n]+\]\([^)\s]+\)|https?:\/\/[^\s<>()]+[^\s<>().,!?;:'"]|\*[^*\s][^*\n]*\*)/g;

function link(href: string, label: string): Node {
  if (!SAFE_PROTOCOL.test(href)) return document.createTextNode(label);
  const a = document.createElement("a");
  a.href = href;
  a.textContent = label;
  if (/^https?:/i.test(href)) {
    a.target = "_blank";
    a.rel = "noopener noreferrer";
  }
  return a;
}

function renderInline(text: string, parent: Node): void {
  let last = 0;
  for (const match of text.matchAll(INLINE)) {
    const token = match[0];
    const at = match.index ?? 0;
    if (at > last) parent.appendChild(document.createTextNode(text.slice(last, at)));
    if (token.startsWith("**")) {
      const strong = document.createElement("strong");
      renderInline(token.slice(2, -2), strong);
      parent.appendChild(strong);
    } else if (token.startsWith("`")) {
      const code = document.createElement("code");
      code.textContent = token.slice(1, -1);
      parent.appendChild(code);
    } else if (token.startsWith("[")) {
      const close = token.indexOf("](");
      parent.appendChild(link(token.slice(close + 2, -1), token.slice(1, close)));
    } else if (/^https?:/i.test(token)) {
      parent.appendChild(link(token, token));
    } else {
      const em = document.createElement("em");
      renderInline(token.slice(1, -1), em);
      parent.appendChild(em);
    }
    last = at + token.length;
  }
  if (last < text.length) parent.appendChild(document.createTextNode(text.slice(last)));
}

const BULLET = /^\s*[-*•]\s+/;
const NUMBER = /^\s*\d+[.)]\s+/;

export function renderMarkdown(text: string, target: HTMLElement): void {
  target.textContent = "";
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }
    const listType = BULLET.test(line) ? "ul" : NUMBER.test(line) ? "ol" : null;
    if (listType) {
      const list = document.createElement(listType);
      const marker = listType === "ul" ? BULLET : NUMBER;
      while (i < lines.length && marker.test(lines[i])) {
        const item = document.createElement("li");
        renderInline(lines[i].replace(marker, ""), item);
        list.appendChild(item);
        i++;
      }
      target.appendChild(list);
      continue;
    }
    const p = document.createElement("p");
    let first = true;
    while (i < lines.length && lines[i].trim() && !BULLET.test(lines[i]) && !NUMBER.test(lines[i])) {
      if (!first) p.appendChild(document.createElement("br"));
      renderInline(lines[i].replace(/^#{1,6}\s+/, ""), p);
      first = false;
      i++;
    }
    target.appendChild(p);
  }
}
