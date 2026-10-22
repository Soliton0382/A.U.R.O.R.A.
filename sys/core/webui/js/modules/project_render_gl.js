// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// 🎨 The realistic view's renderer (ROADMAP N42): WebGL2, no library (as astro_mount3d: the page draws its own). A
// physically based shading — GGX highlights, Fresnel, metals tinted by their colour — lit by a key light that casts
// shadows (a depth map, filtered 3×3), a fill light and a photographer's studio around the model (two soft boxes over a
// grey sweep, reflected by metals: blurred by the roughness). The floor takes the shadow and fades into the backdrop.
// World: millimetres, z up (OpenSCAD's).
const M = {
  mul(a, b) {
    const o = new Float32Array(16);
    for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) {
      o[c * 4 + r] = a[r] * b[c * 4] + a[4 + r] * b[c * 4 + 1] + a[8 + r] * b[c * 4 + 2] + a[12 + r] * b[c * 4 + 3];
    }
    return o;
  },
  persp(fov, asp, n, f) {
    const t = 1 / Math.tan(fov / 2);
    return new Float32Array([t / asp, 0, 0, 0, 0, t, 0, 0, 0, 0, (f + n) / (n - f), -1, 0, 0, (2 * f * n) / (n - f), 0]);
  },
  ortho(r, n, f) {
    return new Float32Array([1 / r, 0, 0, 0, 0, 1 / r, 0, 0, 0, 0, -2 / (f - n), 0, 0, 0, -(f + n) / (f - n), 1]);
  },
  look(eye, at, up) {
    const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
    const nrm = (a) => { const l = Math.hypot(...a) || 1; return a.map((v) => v / l); };
    const crs = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
    const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
    const z = nrm(sub(eye, at)), x = nrm(crs(up, z)), y = crs(z, x);
    return new Float32Array([x[0], y[0], z[0], 0, x[1], y[1], z[1], 0, x[2], y[2], z[2], 0, -dot(x, eye), -dot(y, eye), -dot(z, eye), 1]);
  },
};

const SHADOW_VS = `#version 300 es
uniform mat4 uLightVP; uniform vec3 uOffset; in vec3 aPos;
void main() { gl_Position = uLightVP * vec4(aPos + uOffset, 1.0); }`;
const SHADOW_FS = `#version 300 es
precision mediump float; void main() {}`;
const VS = `#version 300 es
uniform mat4 uVP, uLightVP; uniform vec3 uOffset; in vec3 aPos; in vec3 aNrm;
out vec3 vW; out vec3 vN; out vec4 vL;
void main() { vec3 w = aPos + uOffset; vW = w; vN = aNrm; vL = uLightVP * vec4(w, 1.0); gl_Position = uVP * vec4(w, 1.0); }`;
const FS = `#version 300 es
precision highp float; precision highp sampler2DShadow;
uniform sampler2DShadow uShadow; uniform vec3 uEye, uKey, uFill, uColor, uBg, uCenter;
uniform float uMetal, uRough, uFloor, uFloorR, uExposure, uTexel;
in vec3 vW; in vec3 vN; in vec4 vL; out vec4 o;
const float PI = 3.14159265;
float panel(vec3 d, vec3 at, float size, float r) {   // a soft box seen along d: brighter when small, wider when rough
  float c = cos(size + 0.7 * r * r);
  return smoothstep(c - 0.015 - 0.25 * r * r, c + 0.004, dot(d, normalize(at))) / (1.0 + 10.0 * r * r);
}
vec3 studio(vec3 d, float r) {          // the studio seen along d, blurred by the roughness r
  float h = d.z;
  vec3 c = mix(vec3(0.012), vec3(0.07, 0.072, 0.078), smoothstep(-0.2, 0.9, h));
  c += vec3(0.22, 0.225, 0.235) * exp(-pow(h / (0.12 + 0.3 * r), 2.0));          // the lit walls around, at the horizon
  c += vec3(0.42, 0.43, 0.45) * smoothstep(0.55 - 0.3 * r, 0.9, h);              // the overhead dome
  return c + vec3(6.0) * panel(d, vec3(0.55, -0.55, 0.75), 0.22, r)
           + vec3(2.4, 2.35, 2.3) * panel(d, vec3(-0.9, -0.1, 0.35), 0.18, r)
           + vec3(1.6, 1.65, 1.8) * panel(d, vec3(0.0, 0.95, 0.25), 0.15, r);
}
float shadow() {
  vec3 p = vL.xyz / vL.w * 0.5 + 0.5;
  if (p.x < 0.0 || p.x > 1.0 || p.y < 0.0 || p.y > 1.0 || p.z > 1.0) return 1.0;
  float s = 0.0;
  for (int i = -1; i <= 1; i++) for (int j = -1; j <= 1; j++)
    s += texture(uShadow, vec3(p.xy + vec2(i, j) * uTexel * 1.5, p.z - 0.0015));
  return s / 9.0;
}
vec3 aces(vec3 x) { return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0); }
void main() {
  vec3 n = normalize(gl_FrontFacing ? vN : -vN), v = normalize(uEye - vW);
  float r = clamp(uRough, 0.04, 1.0), a2 = pow(r * r, 2.0);
  vec3 base = uColor;
  if (uFloor > 0.5) { n = vec3(0, 0, 1); base = vec3(0.09); r = 0.85; }
  float nv = max(dot(n, v), 1e-3);
  vec3 f0 = mix(vec3(0.04), base, uMetal), col = vec3(0.0);
  float sh = shadow();
  for (int k = 0; k < 2; k++) {
    vec3 l = k == 0 ? uKey : uFill;
    vec3 rad = k == 0 ? vec3(2.6, 2.55, 2.45) * sh : vec3(0.45, 0.5, 0.6);
    vec3 h = normalize(l + v);
    float nl = max(dot(n, l), 0.0), nh = max(dot(n, h), 0.0), vh = max(dot(v, h), 0.0);
    float d = a2 / (PI * pow(nh * nh * (a2 - 1.0) + 1.0, 2.0));
    float q = pow(r + 1.0, 2.0) / 8.0;
    float g = nv / (nv * (1.0 - q) + q) * nl / (nl * (1.0 - q) + q);
    vec3 f = f0 + (1.0 - f0) * pow(1.0 - vh, 5.0);
    vec3 kd = (1.0 - f) * (1.0 - uMetal);
    col += (kd * base / PI + d * g * f / (4.0 * nv * nl + 1e-4)) * rad * nl;
  }
  vec3 fr = f0 + (max(vec3(1.0 - r), f0) - f0) * pow(1.0 - nv, 5.0);
  float occl = mix(0.55, 1.0, sh);                         // the key light's shadow dims the studio too, a little
  col += (studio(n, 1.0) * 0.8 * base * (1.0 - uMetal) + studio(reflect(-v, n), r) * fr) * occl;
  col *= uExposure;
  col = pow(aces(col), vec3(1.0 / 2.2));
  if (uFloor > 0.5) col = mix(col, uBg, smoothstep(uFloorR * 0.25, uFloorR, length(vW.xy - uCenter.xy)));
  o = vec4(col, 1.0);
}`;

function program(gl, vs, fs) {
  const p = gl.createProgram();
  for (const [type, src] of [[gl.VERTEX_SHADER, vs], [gl.FRAGMENT_SHADER, fs]]) {
    const s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
    gl.attachShader(p, s);
  }
  gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
  const u = {};
  for (let i = 0; i < gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS); i++) {
    const n = gl.getActiveUniform(p, i).name;
    u[n] = gl.getUniformLocation(p, n);
  }
  return { p, u, aPos: gl.getAttribLocation(p, "aPos"), aNrm: gl.getAttribLocation(p, "aNrm") };
}

export const BG = [0.16, 0.165, 0.175];

export function makeRenderer(canvas) {
  const gl = canvas.getContext("webgl2", { antialias: true, preserveDrawingBuffer: true });
  if (!gl) throw new Error("WebGL2");
  const main = program(gl, VS, FS), depth = program(gl, SHADOW_VS, SHADOW_FS);
  const SM = 2048;
  const tex = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, tex);
  gl.texStorage2D(gl.TEXTURE_2D, 1, gl.DEPTH_COMPONENT24, SM, SM);
  for (const [k, v] of [[gl.TEXTURE_MIN_FILTER, gl.LINEAR], [gl.TEXTURE_MAG_FILTER, gl.LINEAR], [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE],
    [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE], [gl.TEXTURE_COMPARE_MODE, gl.COMPARE_REF_TO_TEXTURE]]) gl.texParameteri(gl.TEXTURE_2D, k, v);
  const fbo = gl.createFramebuffer();
  gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT, gl.TEXTURE_2D, tex, 0);
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  let meshes = [], floor = null;
  const upload = (pos, nrm) => {
    const vao = gl.createVertexArray();
    gl.bindVertexArray(vao);
    for (const [loc, data] of [[main.aPos, pos], [main.aNrm, nrm]]) {
      const b = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, b);
      gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, 3, gl.FLOAT, false, 0, 0);
    }
    gl.bindVertexArray(null);
    return { vao, count: pos.length / 3 };
  };
  return {
    // parts: [{pos, nrm, color, metal, rough}] → the meshes drawn; the page sets their .offset ([x, y, z] mm), .visible, look
    setMeshes(parts) {
      meshes = parts.map((p) => ({ ...p, ...upload(p.pos, p.nrm), offset: [0, 0, 0], visible: true }));
      return meshes;
    },
    // view: {eye, at, fov}; bounds: {c, r, zmin}; light: azimuth of the key light (radians)
    draw(view, bounds, light = -0.8, exposure = 0.6) {
      const { c, r, zmin } = bounds;
      const key = [Math.cos(light) * 0.55, Math.sin(light) * 0.55, 0.83], fill = [-key[0] * 0.8, -key[1] * 0.8, 0.45];
      const kl = Math.hypot(...key), fl = Math.hypot(...fill);
      const keyN = key.map((v) => v / kl), fillN = fill.map((v) => v / fl);
      const lightVP = M.mul(M.ortho(r * 1.6, 0.1 * r, 8 * r), M.look(c.map((v, i) => v + keyN[i] * 4 * r), c, [0, 0, 1]));
      const fz = zmin - 0.002 * r, R = r * 6;
      const fpos = new Float32Array([c[0] - R, c[1] - R, fz, c[0] + R, c[1] - R, fz, c[0] + R, c[1] + R, fz,
        c[0] - R, c[1] - R, fz, c[0] + R, c[1] + R, fz, c[0] - R, c[1] + R, fz]);
      if (floor) gl.deleteVertexArray(floor.vao);
      floor = upload(fpos, new Float32Array(18).map((_, i) => (i % 3 === 2 ? 1 : 0)));
      gl.enable(gl.DEPTH_TEST);
      gl.disable(gl.CULL_FACE);
      // 1. the key light's depth map (the floor casts nothing)
      gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
      gl.viewport(0, 0, SM, SM);
      gl.clear(gl.DEPTH_BUFFER_BIT);
      gl.useProgram(depth.p);
      gl.uniformMatrix4fv(depth.u.uLightVP, false, lightVP);
      for (const m of meshes) {
        if (!m.visible) continue;
        gl.uniform3fv(depth.u.uOffset, m.offset);
        gl.bindVertexArray(m.vao);
        gl.drawArrays(gl.TRIANGLES, 0, m.count);
      }
      // 2. the picture
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.clearColor(...BG, 1);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      gl.useProgram(main.p);
      const dist = Math.hypot(...view.eye.map((v, i) => v - view.at[i]));
      const vp = M.mul(M.persp(view.fov, canvas.width / canvas.height, dist / 50, dist + 10 * r), M.look(view.eye, view.at, [0, 0, 1]));
      const u = main.u;
      gl.uniformMatrix4fv(u.uVP, false, vp);
      gl.uniformMatrix4fv(u.uLightVP, false, lightVP);
      gl.uniform3fv(u.uEye, view.eye); gl.uniform3fv(u.uKey, keyN); gl.uniform3fv(u.uFill, fillN);
      gl.uniform3fv(u.uBg, BG); gl.uniform3fv(u.uCenter, c);
      gl.uniform1f(u.uFloorR, r * 2.2); gl.uniform1f(u.uExposure, exposure); gl.uniform1f(u.uTexel, 1 / SM);
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, tex);
      gl.uniform1i(u.uShadow, 0);
      const one = (m, isFloor) => {
        gl.uniform3fv(u.uOffset, isFloor ? [0, 0, 0] : m.offset);
        gl.uniform3fv(u.uColor, isFloor ? [0.3, 0.3, 0.3] : m.color);
        gl.uniform1f(u.uMetal, isFloor ? 0 : m.metal); gl.uniform1f(u.uRough, isFloor ? 0.85 : m.rough);
        gl.uniform1f(u.uFloor, isFloor ? 1 : 0);
        gl.bindVertexArray(m.vao);
        gl.drawArrays(gl.TRIANGLES, 0, m.count);
      };
      one(floor, true);
      for (const m of meshes) if (m.visible) one(m, false);
      gl.bindVertexArray(null);
    },
  };
}
