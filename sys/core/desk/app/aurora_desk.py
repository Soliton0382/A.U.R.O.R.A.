# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora Desktop, version 1 (N152): it learns from a demonstration and never acts on the owner's desktop.

«Mostrami» turns accessibility on (remembering the value before), lists the windows (a short-lived process),
records the chosen one (a recorder process without libatspi), and at «Fine» puts accessibility back, writes a draft
(no model), shows it in plain words and saves it, if the owner wants, in the personal library as «bozza non
approvata». «Prova sul banco» runs a saved draft on the virtual compositor with real keys, never on this desktop.
Local only in version 1; mixed and cloud need the version-2 code (bozza 7 §5).

    /usr/bin/python3 -I -B aurora_desk.py"""
import atexit
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE.parents[1]
sys.path.insert(0, str(CORE))

from PyQt6.QtCore import Qt, QTimer  # noqa: E402
from PyQt6.QtWidgets import (QApplication, QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,  # noqa
                             QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
                             QPushButton, QRadioButton, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout,
                             QWidget)

from desk.app import draft, explain, store  # noqa: E402

PY = ["/usr/bin/python3", "-I", "-B"]
KEEP_ENV = ("WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS", "HOME", "LANG", "LANGUAGE",
            "XDG_STATE_HOME")


def child_env() -> dict:
    """An environment written out, not inherited (bozza 8 §1, R1)."""
    e = {k: os.environ[k] for k in KEEP_ENV if k in os.environ}
    e["PATH"] = "/usr/bin:/bin"
    return e


class Picker(QDialog):
    """Choose the window to demonstrate on."""

    def __init__(self, parent, windows: list):
        super().__init__(parent)
        self.setWindowTitle("Quale finestra mi mostri?")
        self.windows = windows
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Scegli la finestra del programma. Registro solo quella e i dialoghi che apre."))
        self.list = QListWidget()
        for w in windows:
            self.list.addItem(QListWidgetItem(f"{w['app']} — {w['title'][:90]}"))
        lay.addWidget(self.list)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def chosen(self):
        i = self.list.currentRow()
        return self.windows[i] if 0 <= i < len(self.windows) else None


class Preview(QDialog):
    """The draft in plain words: steps, warnings, parameters (examples dropped unless kept), network, name."""

    def __init__(self, parent, built: dict, program: dict):
        super().__init__(parent)
        self.setWindowTitle("La bozza che ho scritto")
        self.built, self.program = built, program
        self.resize(760, 560)
        lay = QVBoxLayout(self)
        steps = built["procedure"]["steps"]
        lay.addWidget(QLabel(f"<b>{program['name']}</b> {program.get('version') or '(versione sconosciuta)'} — "
                             f"{len(steps)} passi"))
        txt = QTextEdit()
        txt.setReadOnly(True)
        lines = [f"{s['n']}. {explain.describe(s)}   [{s['class']}]" for s in steps]
        if built["flags"]:
            lines += ["", "Da controllare:"] + [f"• {f}" for f in built["flags"]]
        txt.setPlainText("\n".join(lines) or "Non ho visto passi.")
        lay.addWidget(txt)
        ex = built["examples"]
        self.table = QTableWidget(len(ex), 3)
        self.table.setHorizontalHeaderLabels(["parametro", "valore d'esempio", "tienilo"])
        self.keep = {}
        for r, (k, v) in enumerate(sorted(ex.items())):
            self.table.setItem(r, 0, QTableWidgetItem(k))
            self.table.setItem(r, 1, QTableWidgetItem(v))
            cb = QCheckBox()
            cb.setChecked(False)                      # dropped unless the owner keeps it (bozza 8 §4)
            self.table.setCellWidget(r, 2, cb)
            self.keep[k] = cb
        lay.addWidget(QLabel("I valori d'esempio restano solo se spunti «tienilo»."))
        lay.addWidget(self.table)
        form = QFormLayout()
        self.net = QCheckBox("il programma usa la rete (ogni azione «esce»)")
        self.net.setChecked(True)                     # with a network unless the owner says otherwise
        form.addRow(self.net)
        self.name = QLineEdit(f"{program['name']}-{time.strftime('%d%m')}-1".lower())
        form.addRow("nome della bozza", self.name)
        lay.addLayout(form)
        bb = QDialogButtonBox()
        bb.addButton("Salva nella mia libreria", QDialogButtonBox.ButtonRole.AcceptRole)
        bb.addButton("Butta via", QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def result_values(self):
        kept = {k: self.built["examples"][k] for k, cb in self.keep.items() if cb.isChecked()}
        return self.name.text().strip(), self.net.isChecked(), kept


class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Aurora Desktop — impara (versione 1)")
        self.resize(640, 420)
        self.rec = None
        w = QWidget()
        lay = QVBoxLayout(w)
        self.status = QLabel()
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        modes = QHBoxLayout()
        self.local = QRadioButton("Locale")
        self.local.setChecked(True)
        mixed, cloud = QRadioButton("Misto (versione 2)"), QRadioButton("Cloud (versione 2)")
        mixed.setEnabled(False)
        cloud.setEnabled(False)
        for b in (self.local, mixed, cloud):
            modes.addWidget(b)
        lay.addLayout(modes)
        row = QHBoxLayout()
        self.show_btn = QPushButton("Mostrami")
        self.end_btn = QPushButton("Fine")
        self.end_btn.setEnabled(False)
        self.show_btn.clicked.connect(self.start)
        self.end_btn.clicked.connect(self.finish)
        row.addWidget(self.show_btn)
        row.addWidget(self.end_btn)
        lay.addLayout(row)
        lay.addWidget(QLabel("Le mie bozze (non approvate):"))
        self.drafts = QListWidget()
        lay.addWidget(self.drafts)
        self.try_btn = QPushButton("Prova sul banco")
        self.try_btn.clicked.connect(self.try_on_bench)
        lay.addWidget(self.try_btn)
        self.setCentralWidget(w)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.refresh()
        self.say("Pronta. Premi «Mostrami»: accendo l'accessibilità solo mentre ti guardo e poi la rimetto com'era. "
                 "Finché l'accessibilità è accesa, ogni programma tuo può leggere e comandare le finestre "
                 "accessibili.")

    def say(self, text: str) -> None:
        self.status.setText(text)

    def refresh(self) -> None:
        self.drafts.clear()
        for f in store.list_drafts():
            self.drafts.addItem(str(f.relative_to(store.DRAFTS)))

    # --- recording ------------------------------------------------------------------------------------------------

    def start(self) -> None:
        try:
            store.a11y_on()
        except Exception as e:                          # noqa: BLE001
            self.say(f"Non riesco ad accendere l'accessibilità: {e}")
            return
        time.sleep(1.0)                                 # Qt exposes its tree 0.68 s after (M334 P2)
        r = subprocess.run(PY + [str(HERE / "windows.py"), "--exclude-pid", str(os.getpid())], capture_output=True,
                           text=True, timeout=30, env=child_env())
        if r.returncode != 0:
            self.say(f"Elenco delle finestre non riuscito: {r.stderr[-300:]}")
            self.put_back()
            return
        listing = json.loads(r.stdout)
        if not listing["windows"]:
            self.say("Non vedo finestre accessibili. Un programma aperto prima potrebbe dover essere riaperto.")
            self.put_back()
            return
        pk = Picker(self, listing["windows"])
        if pk.exec() != QDialog.DialogCode.Accepted or pk.chosen() is None:
            self.put_back()
            self.say("Niente registrato.")
            return
        w = pk.chosen()
        rt = store.runtime_dir()
        self.out, self.stop = rt / "rec.json", rt / "rec.stop"
        for f in (self.out, self.stop, Path(str(self.out) + ".ready")):
            if f.exists():
                f.unlink()
        self.window, self.program = w, explain.program_meta(w["pid"])
        self.rec = subprocess.Popen(PY + [str(HERE / "recorder.py"), "--addr", listing["addr"], "--app-bus",
                                          w["bus"], "--frame", w["frame"], "--out", str(self.out), "--stop",
                                          str(self.stop)], env=child_env(), stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
        self.t0 = time.monotonic()
        self.show_btn.setEnabled(False)
        self.end_btn.setEnabled(True)
        self.timer.start(1000)
        self.tick()

    def tick(self) -> None:
        # only the state, never what is recorded: this window is accessible too (bozza 8 §1, D8)
        s = int(time.monotonic() - self.t0)
        self.say(f"● Registrazione di {self.window['app']} — {s // 60}:{s % 60:02d}. Lavora normalmente; "
                 "premi «Fine» quando hai finito. Le password non le registro.")
        if self.rec is not None and self.rec.poll() is not None:
            self.finish()

    def finish(self) -> None:
        self.timer.stop()
        self.end_btn.setEnabled(False)
        self.show_btn.setEnabled(True)
        if self.rec is not None:
            self.stop.write_text("stop")
            try:
                self.rec.wait(20)
            except subprocess.TimeoutExpired:
                self.rec.kill()
            self.rec = None
        done = self.put_back()
        if not self.out.exists():
            self.say(f"La registrazione non ha prodotto niente. Accessibilità: {done}.")
            return
        data = json.loads(self.out.read_text())
        self.out.unlink()                               # the raw events never stay (bozza 7 §3)
        built = draft.build(data.get("events", []), self.program, loc="it", network=True)
        c = data.get("counters", {})
        self.say(f"Fatto. Accessibilità: {done}. Eventi tenuti {c.get('kept', 0)}, password saltate "
                 f"{c.get('password_suppressed', 0)}.")
        pv = Preview(self, built, self.program)
        if pv.exec() != QDialog.DialogCode.Accepted:
            self.say("Bozza buttata via.")
            return
        name, net, kept = pv.result_values()
        rebuilt = draft.build(data.get("events", []), self.program, loc="it", network=net)
        res = store.save_draft(rebuilt["procedure"], "linux", self.program["name"].lower(), name, kept)
        if res["errors"]:
            QMessageBox.warning(self, "Bozza non valida", "\n".join(res["errors"][:12]))
            return
        self.say(f"Salvata come bozza non approvata: {res['path']}")
        self.refresh()

    def put_back(self) -> str:
        try:
            return store.a11y_restore()
        except Exception as e:                          # noqa: BLE001
            return f"non rimessa ({e})"

    # --- the bench ------------------------------------------------------------------------------------------------

    def try_on_bench(self) -> None:
        it = self.drafts.currentItem()
        if it is None:
            self.say("Scegli una bozza dall'elenco.")
            return
        path = store.DRAFTS / it.text()
        raw = path.read_text()
        proc = json.loads(raw)
        ex_file = path.with_name(path.stem + ".esempi.json")
        examples = json.loads(ex_file.read_text()) if ex_file.exists() else {}
        params = {}
        for k, spec in proc.get("params", {}).items():
            default = examples.get(k, "{lavoro}" if spec.get("kind") == "path" else "")
            val, ok = _ask(self, f"Valore di {k} ({spec.get('kind')}) per la prova sul banco", default)
            if not ok:
                return
            params[k] = val
        store.private_dir(store.BENCH)
        job = [{"proc_json": raw, "sha256": hashlib.sha256(raw.encode()).hexdigest(), "params": params,
                "tag": "prova", "input": "keys"}]
        jf = store.runtime_dir() / "job.json"
        store.write_private(jf, json.dumps(job, ensure_ascii=False))
        self.say("Prova sul banco in corso (desktop virtuale, mai il tuo)…")
        QApplication.processEvents()
        r = subprocess.run(PY + [str(CORE / "desk/bench/lib_run.py"), "--scratch", str(store.BENCH), "--job",
                                 str(jf)], capture_output=True, text=True, timeout=600, env=child_env())
        jf.unlink()
        runs = sorted(store.BENCH.glob("run-*"), key=lambda p: p.stat().st_mtime)
        res = None
        if runs and (runs[-1] / "lib" / "prova.json").exists():
            res = json.loads((runs[-1] / "lib" / "prova.json").read_text())
        for d in runs:                                  # nothing of the trial stays (bozza 8 §5)
            shutil.rmtree(d, ignore_errors=True)
        if res is None:
            self.say(f"Prova non riuscita a partire: {r.stderr[-300:]}")
            return
        lines = [f"{s['n']}. {s['do']}: {'ok' if s.get('ok') else 'NO — ' + s.get('error', '')}" for s in res["steps"]]
        QMessageBox.information(self, "Esito sul banco", ("Riuscita.\n\n" if res.get("ok") else "Non riuscita.\n\n")
                                + "\n".join(lines))
        self.say("Prova finita; la cartella del banco è stata cancellata.")

    def closeEvent(self, ev) -> None:                   # noqa: N802 — Qt's name
        if self.rec is not None:
            self.finish()
        self.put_back()
        super().closeEvent(ev)


def _ask(parent, label: str, default: str):
    d = QDialog(parent)
    d.setWindowTitle("Prova sul banco")
    lay = QVBoxLayout(d)
    lay.addWidget(QLabel(label))
    e = QLineEdit(default)
    lay.addWidget(e)
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    lay.addWidget(bb)
    ok = d.exec() == QDialog.DialogCode.Accepted
    return e.text(), ok


def main() -> int:
    lock = store.single_instance()
    if lock is None:
        print("Aurora Desktop è già aperta.", file=sys.stderr)
        return 1
    store.private_dir(store.STATE)
    left = store.a11y_restore()                         # a recording left half-way (a crash, a logout)
    atexit.register(store.a11y_restore)
    app = QApplication(sys.argv)
    app.setApplicationName("Aurora Desktop")
    m = Main()
    if left not in ("nothing recorded",):
        m.say(f"All'avvio ho rimesso l'accessibilità dopo una registrazione interrotta: {left}.")
    m.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
