// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// An icon chosen from a window, not from a grid on the page (owner, 28 Oct: «nella selezione delle icone io metterei una
// vagonata di icone… che premo sull'icona allora si apre il menù icone e non avere l'elenco delle icone nella pagina
// stessa»): a button shows the icon; a click opens the window — the icons by group, a search by word (Italian or
// English), any emoji typed. iconPicker(input) turns a hidden <input name="icon"> into that button.
import { el } from "./dom.js";
import { t } from "./i18n.js";

// [group key, [[icon, "words it is found by"], …]]
export const ICONS = [
  ["net", [["🔥", "firewall fuoco"], ["🛡️", "scudo sicurezza firewall"], ["📡", "router antenna"], ["📶", "wifi segnale"],
    ["🔀", "switch rete"], ["🌐", "web internet rete globo"], ["🔐", "vpn lucchetto chiave"], ["🔒", "lucchetto sicuro https"],
    ["🔑", "chiave password"], ["🧱", "muro firewall"], ["🛰️", "satellite"], ["📟", "pager console"], ["🔌", "presa spina"],
    ["🧭", "bussola dns"], ["🚦", "semaforo traffico"], ["🕸️", "ragnatela rete"], ["🔗", "link collegamento"], ["🚪", "porta gateway"]]],
  ["server", [["🖥️", "server pc schermo"], ["💻", "portatile laptop"], ["🗄️", "nas archivio"], ["💾", "disco backup"],
    ["💿", "cd disco"], ["🧮", "calcolo"], ["🖲️", "trackball"], ["⌨️", "tastiera"], ["🖱️", "mouse"], ["🧪", "vm test laboratorio"],
    ["🔋", "ups batteria"], ["🪫", "batteria scarica"], ["⚡", "corrente energia"], ["🧊", "freddo raffreddamento"],
    ["🖨️", "stampante"], ["📠", "fax"], ["🗃️", "schedario"], ["🐳", "docker container balena"], ["☁️", "cloud nuvola"],
    ["🏗️", "cantiere build"], ["🧰", "cassetta attrezzi strumenti"], ["⚙️", "ingranaggio impostazioni altro"], ["🛠️", "attrezzi"]]],
  ["home", [["🏠", "casa"], ["🏡", "casa giardino"], ["💡", "luce lampadina"], ["🌡️", "temperatura clima"], ["🔥", "caldaia"],
    ["❄️", "condizionatore freddo"], ["🚿", "doccia acqua"], ["🚰", "acqua rubinetto"], ["🪟", "finestra"], ["🚪", "porta"],
    ["🔔", "campanello allarme"], ["🚨", "allarme sirena"], ["📷", "telecamera camera"], ["📹", "videocamera"], ["🎥", "cinepresa"],
    ["🧹", "aspirapolvere pulizia"], ["🧺", "lavatrice bucato"], ["🍳", "cucina forno"], ["🌱", "pianta giardino irrigazione"],
    ["☀️", "sole fotovoltaico pannelli"], ["🚗", "auto macchina"], ["🔌", "presa smart plug"], ["🐶", "cane animali"], ["🐱", "gatto"]]],
  ["media", [["📺", "tv televisione"], ["🔊", "audio casse"], ["🎧", "cuffie musica"], ["🎵", "musica nota"], ["🎶", "musica"],
    ["🎬", "film cinema"], ["🎞️", "pellicola"], ["📻", "radio"], ["🎮", "giochi console"], ["🕹️", "joystick"], ["📸", "foto"],
    ["🖼️", "immagini quadro"], ["🎙️", "microfono podcast"], ["📽️", "proiettore"], ["🎤", "karaoke"], ["🎛️", "mixer dj"]]],
  ["science", [["🔭", "telescopio astro"], ["🔬", "microscopio scienza"], ["🧪", "provetta chimica"], ["🧬", "dna biologia"],
    ["⚛️", "atomo fisica"], ["🧲", "magnete"], ["🌌", "galassia cielo"], ["🪐", "pianeta"], ["🌍", "terra"], ["📐", "squadra geometria"],
    ["📏", "righello misura"], ["🧮", "abaco matematica"], ["📊", "grafico statistiche"], ["📈", "crescita grafico"],
    ["📚", "libri biblioteca zenodo pubblicazioni"], ["📄", "documento paper"], ["📑", "documenti"], ["🎓", "università laurea orcid"],
    ["🏛️", "istituzione museo"], ["📜", "brevetto pergamena"], ["⚗️", "alambicco"], ["🌡️", "termometro"], ["🛰️", "satellite"]]],
  ["web", [["🌐", "sito web"], ["🔎", "ricerca cerca"], ["📰", "notizie giornale"], ["✉️", "email posta"], ["📧", "email"],
    ["💬", "chat messaggi"], ["🗨️", "commenti"], ["📣", "social annunci"], ["🐦", "uccello social"], ["📌", "segnalibro"],
    ["🔖", "etichetta bookmark"], ["🗺️", "mappa"], ["🛒", "negozio carrello"], ["🏦", "banca"], ["💳", "carta pagamenti"],
    ["💶", "euro soldi spese"], ["📦", "pacco spedizioni"], ["🎟️", "biglietti"], ["✈️", "viaggi volo"], ["🏥", "salute ospedale"]]],
  ["dev", [["🧑‍💻", "sviluppatore programmazione"], ["💻", "codice"], ["📝", "note editor"], ["🐍", "python serpente"],
    ["🦀", "rust granchio"], ["☕", "java caffè"], ["🐙", "polpo repository git"], ["🔧", "chiave inglese"], ["🔩", "bullone"],
    ["🐛", "bug insetto"], ["🚀", "deploy razzo"], ["📋", "appunti"], ["🗂️", "cartelle"], ["📁", "cartella"], ["🔁", "ciclo"],
    ["🤖", "robot ai bot"], ["🧠", "cervello ai modello"], ["⚡", "veloce"], ["🧾", "log ricevuta"]]],
  ["signs", [["⭐", "stella preferito"], ["❤️", "cuore"], ["✅", "ok fatto"], ["⚠️", "attenzione avviso"], ["❗", "importante"],
    ["❓", "domanda"], ["🔴", "rosso"], ["🟠", "arancione"], ["🟡", "giallo"], ["🟢", "verde"], ["🔵", "blu"], ["🟣", "viola"],
    ["⚫", "nero"], ["⚪", "bianco"], ["🏷️", "etichetta"], ["📍", "posizione"], ["🕒", "orologio tempo"], ["📅", "calendario"],
    ["🔔", "notifica"], ["🎯", "obiettivo"], ["🏁", "bandiera fine"], ["💎", "gemma"], ["🌈", "arcobaleno"], ["✨", "magia"]]],
];

function windowFor(current, onPick) {
  const dlg = el("dialog", "icon-picker");
  const head = el("div", "icon-picker-head");
  const find = el("input", "icon-picker-find");
  find.placeholder = t("icons.find");
  const own = el("input", "icon-picker-own");
  own.maxLength = 8;
  own.placeholder = t("icons.own");
  const close = el("button", "", "✕");
  close.type = "button";
  head.append(find, own, close);
  const body = el("div", "icon-picker-body");
  const pick = (icon) => { onPick(icon); dlg.close(); dlg.remove(); };
  const draw = () => {
    const q = find.value.trim().toLowerCase();
    body.replaceChildren();
    for (const [group, list] of ICONS) {
      const shown = list.filter(([, words]) => !q || words.includes(q) || words.split(" ").some((w) => w.startsWith(q)));
      if (!shown.length) continue;
      const grid = el("div", "icon-picker-grid");
      for (const [icon, words] of shown) {
        const b = el("button", icon === current ? "on" : "", icon);
        b.type = "button";
        b.title = words;
        b.addEventListener("click", () => pick(icon));
        grid.append(b);
      }
      body.append(el("div", "icon-picker-group", t(`icons.g.${group}`)), grid);
    }
    if (!body.children.length) body.append(el("p", "muted", t("icons.none")));
  };
  find.addEventListener("input", draw);
  own.addEventListener("keydown", (e) => { if (e.key === "Enter" && own.value.trim()) { e.preventDefault(); pick(own.value.trim()); } });
  close.addEventListener("click", () => { dlg.close(); dlg.remove(); });
  dlg.addEventListener("cancel", () => dlg.remove());
  dlg.append(head, body);
  draw();
  document.body.append(dlg);
  dlg.showModal();
  find.focus();
}

// the hidden input keeps the value for the form; the button shows it and opens the window
export function iconPicker(input, fallback = "🖥️") {
  input.type = "hidden";
  const b = el("button", "icon-picker-btn", input.value || fallback);
  b.type = "button";
  b.title = t("icons.choose");
  const set = (icon) => { input.value = icon; b.textContent = icon || fallback; };
  b.addEventListener("click", () => windowFor(input.value, set));
  input.after(b);
  return { set };
}
