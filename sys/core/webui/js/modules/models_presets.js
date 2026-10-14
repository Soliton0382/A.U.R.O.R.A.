// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// The choices of Models → Come ragiona as assignments, without the page (tests/js/models_presets.mjs runs them in node).

export const BEST_CLOUD = ["extract", "synthesis", "self", "agent"];
const FORGE = ["forge_write", "forge_judge"];

// which of the four the roles describe now
export function choiceOf(roles, mode) {
  const out = roles.filter((r) => r.provider !== "local");
  if (!out.length) return "local";
  const core = out.map((r) => r.id).filter((id) => !FORGE.includes(id)).sort();
  if (core.join() === [...BEST_CLOUD].sort().join() && new Set(out.filter((r) => !FORGE.includes(r.id)).map((r) => r.provider)).size === 1) return "best";
  if (mode === "cloud_private") return "cloud";
  return "custom";
}

// «il meglio dei due»: every role local but the four, which go to the cloud default; the forge as it is
export function bestRoles(roles, provider, model) {
  return Object.fromEntries(roles.map((r) => [r.id, FORGE.includes(r.id) ? { provider: r.provider, model: r.model || "" }
    : BEST_CLOUD.includes(r.id) ? { provider, model } : { provider: "local", model: "" }]));
}
