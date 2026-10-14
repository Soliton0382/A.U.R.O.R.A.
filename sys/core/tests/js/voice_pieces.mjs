// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// webui/js/voice.js's pieces() under node (test_voice_pieces.py): how an answer is cut for Aurora's own voice.
globalThis.window = {}; globalThis.localStorage = { getItem: () => null, setItem: () => {} };
const { pieces } = await import(process.argv[2]);
console.log(JSON.stringify(JSON.parse(process.argv[3]).map((t) => pieces(t))));
