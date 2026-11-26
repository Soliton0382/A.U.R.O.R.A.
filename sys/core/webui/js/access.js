// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// N165: the pages this person may not open (the machine's, and the features the admin keeps from them), set by main.js
// from /me; read by the pieces that link pages among themselves (the chat's tabs).
let hidden = new Set();
export function setHidden(ids) { hidden = new Set(ids); }
export const isHidden = (id) => hidden.has(id);
