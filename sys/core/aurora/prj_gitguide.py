# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""How to commit and publish a project by hand, from its terminal (C674).

Aurora runs no git on an existing project's folder outside a cage: the folder's .git is written by
code Aurora runs, and git reads far more of it than any check can vouch for. The project's terminal (prj_term) is the
project's cage — no network, only the project's folder writable — so git there has no more power than the project's
own code: commits are made there, by the user who manages the project. Pushing needs the network, so the history
leaves as a bundle (a plain file: no configuration, no hooks), downloaded from the project's preview and pushed from
the user's own computer with the user's own GitHub credentials — Aurora's token is never involved.

`ensure` writes the guide into a project that has none (never through a link, prj_safeio) and keeps it out of the
project's commits (.gitignore): it is Aurora's note to the user, not part of the project.
"""
from __future__ import annotations

from pathlib import Path

from . import prj_safeio

NAME = "aurora-git.md"
BUNDLE = "aurora.bundle"

TEXT = f"""# Git from the project's terminal / Git dal terminale del progetto

*Written by Aurora; not committed (it is in .gitignore). Scritto da Aurora; non entra nei commit.*

## Italiano

Aurora non esegue git sui progetti da sola: i commit e la
pubblicazione li fa chi gestisce il progetto, dal **terminale del progetto** (pagina Progetti → Terminale).
Il terminale gira nella gabbia del progetto: niente rete, scrive solo in questa cartella.

**Più semplice, senza comandi**: pagina Progetti → **📦 Pubblica** → scrivi cosa è cambiato → **Prepara
pacchetto** → **Scarica** (fa i passi 1–4 qui sotto). Poi segui il passo 5 dal tuo computer.

**1. Una volta sola: chi firma i commit**

    git config user.name "Nome Cognome"
    git config user.email "nome@esempio.org"

(Progetto senza repository? `git init -b main` prima.)

**2. Commit**

    git status
    git add -A
    git commit -m "Cosa è cambiato"

**3. Preparare il pacchetto da pubblicare** (il terminale non ha rete: la storia esce come file)

    git bundle create {BUNDLE} main

**4. Scaricarlo**: pagina Progetti → Anteprima, poi aggiungi `{BUNDLE}` in fondo all'indirizzo che si apre
(`…/v1/preview/<codice>/{BUNDLE}`). L'anteprima vale 10 minuti.

**5. Dal tuo computer, con le tue credenziali GitHub**

La prima volta:

    git clone -b main {BUNDLE} mio-progetto
    cd mio-progetto
    git remote add github https://github.com/<utente>/<repository>.git
    git push github main

Le volte dopo (scaricato un nuovo `{BUNDLE}`):

    git pull /percorso/{BUNDLE} main
    git push github main

**Prima di ogni push, ricontrolla** cosa stai per pubblicare (sul tuo computer, con calma):

    git log --stat github/main..main      # i commit nuovi e i file toccati (la prima volta: git log --stat)
    git diff github/main main             # le righe cambiate

Qualcosa non va? Correggi sul tuo computer (`git commit --amend`, un nuovo commit) prima del push: niente
esce finché non lo spingi tu.

Il pacchetto è solo dati (niente configurazione né hook del progetto): clonarlo è sicuro.
Il token GitHub di Aurora non entra mai in questo giro. Puoi cancellare `{BUNDLE}` dopo averlo scaricato.

## English

Aurora does not run git on projects by herself: commits and publishing are
done by whoever manages the project, from the **project's terminal** (Projects page → Terminal), which runs in
the project's cage — no network, it writes only in this folder.

Simpler, no commands: Projects page → **📦 Publish** → write what changed → **Prepare package** → **Download**
(steps 1–4 below); then step 5 on your own computer.

1. Once: `git config user.name "Your Name"` and `git config user.email "you@example.org"`
   (no repository yet? `git init -b main` first).
2. Commit: `git status`, `git add -A`, `git commit -m "What changed"`.
3. Package the history (the terminal has no network): `git bundle create {BUNDLE} main`.
4. Download it: Projects page → Preview, then add `{BUNDLE}` at the end of the address it opens
   (`…/v1/preview/<code>/{BUNDLE}`); the preview lasts 10 minutes.
5. On your own computer, with your own GitHub credentials — first time:
   `git clone -b main {BUNDLE} my-project`, `cd my-project`,
   `git remote add github https://github.com/<user>/<repository>.git`, `git push github main`;
   later: `git pull /path/{BUNDLE} main`, `git push github main`.
6. Before every push, review what goes out: `git log --stat github/main..main` and `git diff github/main main`
   (first time: `git log --stat`); fix it on your computer if needed — nothing leaves until you push.

A bundle is data only (none of the project's configuration or hooks): cloning it is safe. Aurora's GitHub token
is never part of this. You may delete `{BUNDLE}` once downloaded.
"""


def ensure(project: Path) -> bool:
    """The guide written into `project` when missing; True when written now. Never through a link (ValueError,
    OSError are the caller's: a project whose root holds a link by that name gets no guide)."""
    if prj_safeio.is_file(project, NAME):
        return False
    prj_safeio.write_text(project, NAME, TEXT)
    ignore = prj_safeio.read_text(project, ".gitignore") if prj_safeio.is_file(project, ".gitignore") else ""
    lines = ignore.split("\n")
    missing = [n for n in (NAME, BUNDLE) if n not in lines and "/" + n not in lines]
    if missing:
        sep = "" if not ignore or ignore.endswith("\n") else "\n"
        prj_safeio.write_text(project, ".gitignore", sep + "\n".join(missing) + "\n", append=True)
    return True
