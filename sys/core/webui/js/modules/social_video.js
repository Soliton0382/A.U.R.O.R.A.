// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🎬 Aurora's narrated videos on the Social page (owner, 2026-10-06: "we let her make one and approve it"): a topic →
// the video made on her machine (kno_story: vault, checked script, pictures, her voice, music), each step shown; then
// every video with its post, editable, and one "Publish" per platform that takes videos — that click is the approval.
import { call, followRun } from "../api.js";
import { el } from "../dom.js";
import { t } from "../i18n.js";
import { privacyBox, publishPost } from "./social.js";

const STEPS = { "run.start": "social.video.st_answer", "story.script": "social.video.st_script", "image.batch": "social.video.st_pictures",
  "image.swap": "social.video.st_pictures", "story.done": "social.video.st_done" };

export function videoSection(box) {
  const form = el("form", "import compose");
  const topic = el("input");
  topic.type = "text";
  topic.placeholder = t("social.video.topic");
  const make = el("button", "", `🎬 ${t("social.video.make")}`);
  make.type = "submit";
  const status = el("p", "muted");
  const list = el("div", "soc-videos");
  form.append(topic, make);
  box.append(el("p", "muted", t("social.video.hint")), form, status, list);

  const load = async () => {
    let r;
    try { r = await call("/v1/aurora/social/stories"); } catch (e) { list.replaceChildren(el("p", "error", t("ev.error", { m: e.message }))); return; }
    const on = r.platforms.filter((p) => p.available);
    list.replaceChildren(...(r.stories.length ? r.stories.map((s) => card(s, on)) : [el("p", "muted", t("social.video.none"))]));
  };

  const card = (s, platforms) => {
    const c = el("details", "appr-card external");
    c.append(el("summary", "", `🎬 ${s.topic || s.stamp} · ${s.length_s ? `${Math.round(s.length_s)} s` : ""} · ${s.stamp.slice(9, 11)}:${s.stamp.slice(11, 13)} ${s.stamp.slice(6, 8)}/${s.stamp.slice(4, 6)}`));
    c.addEventListener("toggle", () => {
      if (!c.open || c.dataset.ready) return;
      c.dataset.ready = "1";
      const video = el("video", "story-video");
      video.controls = true;
      video.preload = "metadata";
      video.playsInline = true;
      video.src = `/v1/aurora/social/stories/${s.stamp}/video`;
      const area = el("textarea");
      area.rows = 7;
      area.value = s.post;
      const row = el("div", "appr-actions");
      const out = el("span", "muted");
      for (const p of platforms) {
        let shape = null;                                   // Facebook: reel, post or story (its setting preselected)
        if (p.formats?.length) {
          shape = el("select");
          for (const f of p.formats) shape.append(new Option(t(`social.video.as.${f}`), f, false, f === p.format));
          shape.title = t("social.video.as_hint");
          row.append(shape);
        }
        const pub = el("button", "approve", `✔ ${t("social.publish", { p: p.label })}`);
        pub.type = "button";
        pub.addEventListener("click", async () => {
          pub.disabled = true;
          out.textContent = t("social.video.sending", { p: p.label });
          try {
            const r = await publishPost({ plugin: p.plugin, text: area.value.slice(0, p.max_chars), video: s.video, ...(shape ? { format: shape.value } : {}) });
            if (!r) { out.textContent = ""; pub.disabled = false; return; }
            out.textContent = `${p.label}: ${r.result?.text || r.status || t("social.sent")}`;
          } catch (e) { out.textContent = t("ev.error", { m: e.message }); pub.disabled = false; }
        });
        row.append(pub);
      }
      if (!platforms.length) row.append(el("span", "muted", t("social.video.no_platform")));
      row.append(out);
      c.append(video, area, privacyBox(() => area.value, (v) => { area.value = v; }), row);
    });
    return c;
  };

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const q = topic.value.trim();
    if (q.length < 3) return;
    make.disabled = true;
    status.textContent = `⏳ ${t("social.video.st_answer")}`;
    try {
      const { run_id } = await call("/v1/aurora/social/story", { method: "POST", body: JSON.stringify({ topic: q }) });
      topic.value = "";
      await follow(run_id);
    } catch (e) { status.textContent = t("ev.error", { m: e.message }); }
    make.disabled = false;
  });

  // the video is made on the server whatever the page does: followed across lost connections (the app in the
  // background, C199), and taken up again when the page opens while one is being made — also one started elsewhere
  let following = null;
  async function follow(runId) {
    if (following === runId) return;
    following = runId;
    make.disabled = true;
    let failed = "";
    try {
      await followRun(runId, (e) => {
        if (STEPS[e.event]) status.textContent = `⏳ ${t(STEPS[e.event])}`;
        if (e.event === "error") failed = e.payload?.message || "error";
        if (e.event === "story.ready") status.textContent = `✅ ${t("social.video.ready", { s: Math.round(e.payload.length_s) })}`;
      }, () => { status.textContent = `🔌 ${t("chat.reconnecting")}`; });
      if (failed) status.textContent = `⚠️ ${failed}`;
      await load();
      list.querySelector("details")?.setAttribute("open", "");
    } catch (e) { status.textContent = t("ev.error", { m: e.message }); }
    following = null;
    make.disabled = false;
  }

  async function resume() {
    const runs = await call("/v1/aurora/runs").catch(() => []);
    const live = runs.find((r) => r.origin === "story" && !r.done);
    if (live) { status.textContent = `⏳ ${t("social.video.resumed", { q: live.question })}`; follow(live.id); }
  }
  resume();
  return { load, resume };
}
