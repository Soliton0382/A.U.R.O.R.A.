// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🎚️ Two decks (owner, 2026-10-10: «un classico remix su due brani… facendoti decidere un po' tutto»): shown when two
// tracks are ticked; A and B in the order they were ticked (⇄ swaps them); every choice the user's, «auto» a DJ's
// (aud_deck): the tempo, B in A's key, mix or mashup, where B comes in and over how many bars, the transition, the beat
// added, each deck's volume.
import { el } from "../dom.js";
import { t } from "../i18n.js";

const sel = (name, pairs) => {
  const s = el("select");
  s.name = name;
  for (const [v, label] of pairs) { const o = el("option", "", label); o.value = v; s.append(o); }
  return s;
};
const field = (label, input) => { const l = el("label", "dj-field"); l.append(el("span", "muted", label), input); return l; };

export function deckPanel(onSwap) {
  const box = el("div", "dj-deck");
  box.hidden = true;
  const names = el("p", "dj-deck-names");
  const swap = el("button", "", "⇄");
  swap.type = "button";
  swap.title = t("deck.swap");
  swap.addEventListener("click", onSwap);
  const mode = sel("mode", [["mix", t("deck.mix")], ["mashup", t("deck.mashup")]]);
  const bpm = sel("bpm", [["a", t("deck.bpm_a")], ["b", t("deck.bpm_b")], ["style", t("deck.bpm_style")], ["custom", t("deck.bpm_custom")]]);
  const bpmNum = el("input");
  Object.assign(bpmNum, { type: "number", min: 60, max: 200, step: 0.5, value: 124, hidden: true });
  bpm.addEventListener("change", () => { bpmNum.hidden = bpm.value !== "custom"; });
  const key = sel("key", [["match", t("deck.key_match")], ["keep", t("deck.key_keep")]]);
  const at = el("input");
  Object.assign(at, { type: "number", min: 0, step: 1, placeholder: t("deck.at_auto") });
  const bars = sel("bars", [["16", "16"], ["8", "8"], ["32", "32"], ["4", "4"]]);
  const tr = sel("transition", [["bass_swap", t("deck.t_bass")], ["crossfade", t("deck.t_fade")], ["filter", t("deck.t_filter")], ["echo", t("deck.t_echo")]]);
  const drums = sel("drums", [["none", t("deck.d_none")], ["light", t("deck.d_light")], ["full", t("deck.d_full")]]);
  const gain = (n) => { const i = el("input"); Object.assign(i, { type: "range", min: -12, max: 6, step: 1, value: 0, name: n }); return i; };
  const ga = gain("gain_a"), gb = gain("gain_b");
  const mixOnly = [field(t("deck.at"), at), field(t("deck.bars"), bars), field(t("deck.transition"), tr)];
  mode.addEventListener("change", () => mixOnly.forEach((f) => { f.hidden = mode.value !== "mix"; }));
  const grid = el("div", "dj-deck-grid");
  grid.append(field(t("deck.mode"), mode), field(t("deck.bpm"), bpm), bpmNum, field(t("deck.key"), key), ...mixOnly,
    field(t("deck.drums"), drums), field(t("deck.gain_a"), ga), field(t("deck.gain_b"), gb));
  const head = el("div", "appr-actions");
  head.append(el("strong", "", `🎚️ ${t("deck.title")}`), names, swap);
  box.append(head, el("p", "muted", t("deck.hint")), grid);
  box.show = (a, b) => { box.hidden = !(a && b); names.textContent = a && b ? `A: ${a} · B: ${b}` : ""; };
  box.options = () => ({
    mode: mode.value, bpm: bpm.value === "custom" ? Number(bpmNum.value) : bpm.value, key: key.value,
    at: at.value === "" ? "auto" : Number(at.value), bars: Number(bars.value), transition: tr.value, drums: drums.value,
    gain_a: Number(ga.value), gain_b: Number(gb.value),
  });
  return box;
}
