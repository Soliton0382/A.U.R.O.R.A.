// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🧮 A simulator's formulas (prj_sim, ROADMAP N42): arithmetic read by a small parser of its own — no eval (the page's
// CSP forbids it, and a project's file must never run code). Numbers, names, + − * / ^ (power, right to left), unary
// minus, one comparison (< <= > >=, giving 1 or 0), and the functions the server allows (prj_sim.FUNCS);
// if(c, a, b) picks a when c is not 0. compile(text) gives a function of the scope (name → number).
const FUNCS = {
  sqrt: Math.sqrt, abs: Math.abs, min: Math.min, max: Math.max, sin: Math.sin, cos: Math.cos, tan: Math.tan,
  asin: Math.asin, acos: Math.acos, atan: Math.atan, atan2: Math.atan2, exp: Math.exp, log: Math.log,
  log10: Math.log10, floor: Math.floor, ceil: Math.ceil, round: Math.round, if: (c, a, b) => (c ? a : b),
};
export const CONSTS = { pi: Math.PI, e: Math.E, mu0: 4e-7 * Math.PI };

function tokens(src) {
  const out = [];
  const rx = /\s*(?:(\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?)|([A-Za-z_]\w*)|(<=|>=|[-+*/^(),<>]))/y;
  let m;
  rx.lastIndex = 0;
  while (rx.lastIndex < src.length) {
    const at = rx.lastIndex;
    if (!(m = rx.exec(src))) {
      if (/^\s*$/.test(src.slice(at))) break;
      throw new Error(`formula not understood at «${src.slice(at, at + 8)}»`);
    }
    out.push(m[1] !== undefined ? { n: parseFloat(m[1]) } : m[2] !== undefined ? { id: m[2] } : { op: m[3] });
  }
  return out;
}

export function compile(src) {
  const ts = tokens(String(src));
  let i = 0;
  const peek = (op) => ts[i] && ts[i].op === op;
  const take = (op) => { if (!peek(op)) throw new Error(`«${op}» expected in ${src}`); i++; };
  const cmp = () => {
    const a = sum();
    for (const op of ["<=", ">=", "<", ">"]) {
      if (peek(op)) {
        i++;
        const b = sum();
        return { "<=": (s) => +(a(s) <= b(s)), ">=": (s) => +(a(s) >= b(s)), "<": (s) => +(a(s) < b(s)), ">": (s) => +(a(s) > b(s)) }[op];
      }
    }
    return a;
  };
  const sum = () => {
    let a = prod();
    while (peek("+") || peek("-")) {
      const op = ts[i++].op, l = a, r = prod();
      a = op === "+" ? (s) => l(s) + r(s) : (s) => l(s) - r(s);
    }
    return a;
  };
  const prod = () => {
    let a = unary();
    while (peek("*") || peek("/")) {
      const op = ts[i++].op, l = a, r = unary();
      a = op === "*" ? (s) => l(s) * r(s) : (s) => l(s) / r(s);
    }
    return a;
  };
  const unary = () => {
    if (peek("-")) { i++; const a = unary(); return (s) => -a(s); }
    if (peek("+")) { i++; return unary(); }
    return power();
  };
  const power = () => {
    const b = atom();
    if (peek("^")) { i++; const x = unary(); return (s) => b(s) ** x(s); }   // 2^-1, a^b^c = a^(b^c)
    return b;
  };
  const atom = () => {
    const tk = ts[i++];
    if (!tk) throw new Error(`formula ends too soon: ${src}`);
    if (tk.n !== undefined) return () => tk.n;
    if (tk.op === "(") { const a = cmp(); take(")"); return a; }
    if (tk.id !== undefined) {
      if (peek("(")) {
        const f = FUNCS[tk.id];
        if (!f) throw new Error(`unknown function ${tk.id}`);
        i++;
        const args = [];
        if (!peek(")")) { args.push(cmp()); while (peek(",")) { i++; args.push(cmp()); } }
        take(")");
        return (s) => f(...args.map((a) => a(s)));
      }
      const id = tk.id;
      return (s) => {
        const v = id in s ? s[id] : CONSTS[id];
        if (v === undefined) throw new Error(`unknown name ${id}`);
        return v;
      };
    }
    throw new Error(`«${tk.op}» out of place in ${src}`);
  };
  const f = cmp();
  if (i < ts.length) throw new Error(`«${ts[i].op ?? ts[i].id ?? ts[i].n}» out of place in ${src}`);
  return f;
}

// the outputs in order, each seeing the parameters, the constants and the outputs above it
export function evaluate(sim, values, compiled) {
  const s = { ...sim.consts, ...values };
  for (const o of sim.outputs) {
    try { s[o.id] = compiled[o.id](s); } catch { s[o.id] = NaN; }
  }
  return s;
}
