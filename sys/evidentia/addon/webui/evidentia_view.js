// 🕵️ Evidentia (this installation's own, never published): the pieces its pages share — the page viewer (a document's
// page opened over the page, with the words to find marked), a citation as a button that opens it, and the fixed
// address of Evidentia's route in Aurora (local/api_evidentia: fixed paths, the admin's alone).
import { call } from "/static/js/api.js";
import { el } from "/static/js/dom.js";
import { lang, t } from "/static/js/i18n.js";

export const API = "/v1/aurora/evidentia";

// «ABC:ABC0001234» + 2 → the page over the page; `mark`: words to find in it (a quote, a name)
export async function openPage(doc, page, mark = "") {
  const box = el("dialog", "evd-page");
  const head = el("div", "evd-bar");
  const close = el("button", "", "✕");
  close.addEventListener("click", () => box.close());
  const prev = el("button", "", "◀");
  const next = el("button", "", "▶");
  const title = el("strong", "", `${doc.split(":")[1] || doc} · p. ${page}`);
  const text = el("div", "evd-page-text", "…");
  head.append(prev, title, next, close);
  box.append(head, text);
  box.addEventListener("close", () => box.remove());
  document.body.append(box);
  box.showModal();
  const load = async (n) => {
    try {
      const r = await call(`${API}/doc/${encodeURIComponent(doc)}/page/${n}`);
      title.textContent = `${r.cite} · ${r.source === "ocr" ? "OCR" : "PDF"}`;
      text.replaceChildren(...marked(r.text || "", mark));
      page = n;
    } catch (e) { text.textContent = t("evd.page_none", { m: e.message }); }
  };
  prev.addEventListener("click", () => page > 1 && load(page - 1));
  next.addEventListener("click", () => load(page + 1));
  await load(page);
  box.querySelector("mark")?.scrollIntoView({ block: "center" });
}

// the text with the marked words wrapped in <mark>, built as nodes (never as HTML: the documents are data); the words
// are found with any spacing and case, as the server's quote check does
function marked(text, mark) {
  const words = String(mark || "").trim().split(/\s+/).filter(Boolean).slice(0, 30);
  if (!words.length) return [document.createTextNode(text)];
  const rx = new RegExp(words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("\\s+"), "i");
  const m = rx.exec(text);
  if (!m) return [document.createTextNode(text)];
  return [document.createTextNode(text.slice(0, m.index)), el("mark", "", m[0]),
    document.createTextNode(text.slice(m.index + m[0].length))];
}

// a citation that opens its page: {doc, page, cite} as the server gives it
export function citeButton(c, mark = "") {
  const b = el("button", "link evd-cite", `📄 ${c.cite || `${c.doc} p. ${c.page}`}`);
  b.addEventListener("click", () => openPage(c.doc, c.page, mark));
  return b;
}

// «ABC:ABC0001234|2» (the network's «seen in») → a citation button
export function seenButton(seen) {
  const [doc, page] = String(seen).split("|");
  return citeButton({ doc, page: Number(page) || 1, cite: `${doc.split(":")[1] || doc} p. ${page}` });
}


// 🌐 a text of the investigation in the reader's language (owner, 10 Nov: «almeno un tasto traduci così l'indagine è
// comprensibile per la lingua di chi legge»): Aurora's model translates it, the quotes stay in their own words with
// their meaning beside them; a second click shows the original again
export function translateButton(text, into) {
  const b = el("button", "link evd-cite", `🌐 ${t("evd.translate")}`);
  let shown = null;
  b.addEventListener("click", async () => {
    if (shown) { shown.remove(); shown = null; b.textContent = `🌐 ${t("evd.translate")}`; return; }
    b.disabled = true;
    b.textContent = `🌐 ${t("evd.translating")}`;
    try {
      const r = await call("/v1/aurora/evidentia-translate", { method: "POST", body: JSON.stringify({ text, lang }) });
      shown = el("div", "evd-translated");
      try {
        const { renderMarkdown } = await import("/static/js/md.js");
        shown.append(renderMarkdown(r.text));
      } catch { shown.textContent = r.text; }
      into.append(shown);
      b.textContent = `🌐 ${t("evd.original")}`;
    } catch (e) { b.textContent = `⚠️ ${e.message}`; }
    b.disabled = false;
  });
  return b;
}
