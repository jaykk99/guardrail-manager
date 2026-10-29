# Guardrail Manager

One console for the refusal / guardrail policy across Jay's app templates
and agent platforms: see every repo's guard files, write the template
default policy yourself, and edit each deployment's policy per repo, with
every change committed and pushed to GitHub.

## Live app (Cloudflare, no sleeping)

**https://guardrail-manager.jayomer1234.workers.dev**

The Cloudflare version runs at that URL, signed in with GitHub, gated by an
access code. It never sleeps. The deployable bundle lives in `cloudflare/`
in this repo (single Worker file + database migration + deploy notes). The
Python version below is the original local build of the same app.

## The two layers (this split is the whole design)

**Deployment policy template (owner config).** The platforms are customer
app templates, and the policy file is a per-deployment template feature:
each deploying user writes their own refusal policy. The default you write
on the app's Template Default page is the starting policy file bundled
with the templates; it can be edited per deployment later. In this app the
config layer is fully yours:

- view and edit the raw file
- add / remove entries
- clear all entries to zero
- delete the policy file entirely
- apply the template default to any repo

Deleting or emptying the policy file is safe by design: an absent or empty
config means **no soft blocks**. Entries only ever add soft blocks.

**Hard floor.** A small set of hardcoded checks that live in code, not in
any config file: stolen cards, phishing/fraud, wallet theft, unauthorized
hacking, weapons of mass harm, CSAM, doxxing, plus the money / approval /
scope gates. In this app those files are listed **view-only**, labelled
"hard floor, not editable here". There is no edit or delete mechanism for
them here, on purpose. If the scanner is unsure whether a file is config
or floor, it treats it as floor (view-only).

Also labelled for what it is: termux-code's `lib/refusal.mjs` is a refusal
**detector** (a model refusal counts as a failed attempt and the chain
moves to the next model). It is not a block list, and it is view-only.

One special case: error-inbox keeps its deployment policy as entry lists
inside a code module (`lib/guard-policy.ts`, which the app imports). For
that file the entry lists are editable here (add / remove / clear / apply
default), but the module itself is not raw-editable or deletable from this
app, so a stray edit here can never break the host app's build.

## Run it

Python 3.11+, standard library only. Needs the `gh` CLI signed in as the
repo owner for scanning and pushing.

```sh
ACCESS_CODE='<set by the owner at deploy time>' python3 server.py
```

Env vars (names only):

- `ACCESS_CODE` - required. The server refuses to start without it.
- `PORT` - default 8790. `HOST` - default 0.0.0.0.
- `GH_OWNER` - default `jaykk99`.
- `GM_DATA_DIR` - app data (template default + scan cache), default `./data`.
- `GM_WORKTREES_DIR` - git worktrees for edits, default `~/workspace/wt`.

Or with Docker: `docker build -t guardrail-manager .` and run with the
same env vars; the container needs `gh` auth and network access to GitHub.

## How edits work

Per repo, edits happen in a dedicated git worktree
(`guardmgr-<repo>`), never in a main checkout. A save commits with a clear
message and pushes fast-forward only (no force push, ever), then verifies
the new head on origin. If a push fails, the app reports it and stops.

## Layout

- `server.py` - entry point (refuses to start without `ACCESS_CODE`)
- `app/classify.py` - config vs floor vs detector classification
- `app/scanner` logic lives in `app/service.py` + `app/source.py` (gh CLI)
- `app/gitops.py` - worktree / commit / push path
- `app/semantics.py` - reference consumer: empty config = no soft blocks
- `public/index.html` - single-page UI (dark, phone-friendly)
- `tests/` - classifier, semantics, service+git fixture, and HTTP tests

Run tests: `python3 -m unittest discover -s tests`

## Hosting note

Not deployed yet. This app needs git + GitHub access (clone/push) and a
small persistent data dir, so static hosting (Cloudflare Pages) does not
fit it. It fits any small always-on container/VM host that can run Python
and hold a `gh` login.
