// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
// A QR code as SVG elements (vendor/qrcode, MIT), built cell by cell: never HTML. For the Authenticator's enrolment.
import qrcode from "../vendor/qrcode/qrcode.mjs";

const NS = "http://www.w3.org/2000/svg";

export function qrSvg(text, px = 220) {
  const qr = qrcode(0, "M");
  qr.addData(text);
  qr.make();
  const n = qr.getModuleCount(), m = 4, size = n + 2 * m;
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${size} ${size}`);
  svg.setAttribute("width", px);
  svg.setAttribute("height", px);
  svg.setAttribute("class", "qr");
  const bg = document.createElementNS(NS, "rect");
  bg.setAttribute("width", size); bg.setAttribute("height", size); bg.setAttribute("fill", "#fff");
  svg.append(bg);
  for (let r = 0; r < n; r++) {
    for (let c = 0; c < n; c++) {
      if (!qr.isDark(r, c)) continue;
      const cell = document.createElementNS(NS, "rect");
      cell.setAttribute("x", c + m); cell.setAttribute("y", r + m);
      cell.setAttribute("width", 1); cell.setAttribute("height", 1); cell.setAttribute("fill", "#000");
      svg.append(cell);
    }
  }
  return svg;
}
