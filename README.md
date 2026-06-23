# comprehend

A knowledge-internalization interviewer delivered as **Claude.ai connectors** plus a private
dashboard. A person's *own* Claude pulls down an "interview" an owner authored — source
material, the owner's opinionated takes, a rubric, and conduct instructions — then runs a
dynamic, conversational interview (drill *and* teach) and reports a structured result back to
a dashboard the owner watches.

The idea: people learn and demonstrate understanding best talking to the Claude that already
knows them, not a stranger LLM. The server is deliberately thin — it serves the interview
package, records results, and logs timing/events. **All questioning, teaching, grading, and
profile-writing happen inside the participant's Claude, so no Anthropic API key ever lives on
the server.** Scoring is trust-based and self-reported; retakes are encouraged until you pass.

## How it works

```
  Owner's Claude ──(owner connector)──▶  authors interviews, adds people, reads results
                                              │
                                         comprehend  ──▶  SQLite (interviews, people,
                                              │                   attempts, events)
  Participant's Claude ──(per-person link)────┘
        list_interviews → get_interview (timed) → submit_result
                                              │
  Owner ──(browser, password)──────────▶  dashboard: results, pass rates, per-person history
```

Three surfaces, one Starlette process behind Caddy:

| Surface | Path | Auth |
| --- | --- | --- |
| Participant connector | `/c/{token}/mcp` | the per-person token in the URL *is* the identity |
| Owner connector | `/owner/{secret}/mcp` | one high-entropy secret (validated in middleware) |
| Dashboard API + SPA | `/api/*`, `/admin` | admin password → signed session cookie |

### The owner's flow (low-effort, Claude-driven)

Drop a link to your own Claude on the owner connector: *"METR released this report &lt;link&gt;,
make an interview."* Claude researches it, asks you 3–5 questions about your takes and cruxes,
asks what to always probe, drafts the interview, creates it, and hands you the dashboard link.
Or just: *"create a connector link for Anna."* (You can also author from the dashboard.)

### The participant's flow

Add your personal connector link in Claude.ai, then say *"get the latest interview about METR."*
Your Claude reads the material + the owner's takes, interviews you (teaching where you're shaky,
moving fast where you're solid, varying questions so you can't memorize), and records an honest
result. Didn't pass? Keep working through it with the same Claude and retake. On a retake, the
connector hands your Claude a brief memory of your prior attempts so it steers toward your gaps.

## Architecture

- `src/comprehend/` — Python 3.12 + [FastMCP](https://github.com/jlowin/fastmcp), one process:
  - `identity.py` — ASGI middleware recovers the path token/secret into contextvars.
  - `participant.py` / `owner.py` — the two FastMCP servers (tools).
  - `store.py` — all SQLite access behind a small domain API.
  - `results.py` — read-only aggregation shared by the owner connector and the dashboard.
  - `admin.py` — dashboard JSON API + cookie auth. `server.py` — assembles + serves everything.
  - `instructions.py` — the prompt heart: how each Claude should conduct itself.
- `web/` — Vite + React dashboard (self-hosted fonts, tiny dependency surface).
- `deploy/` — systemd unit, Caddy snippet, `env.example`.
- `spikes/` — runnable harnesses: `spike_path_token.py`, `smoke_e2e.py`, `seed_dev.py`.

## Local development

```bash
uv sync                                   # backend deps
cd web && npm install && npm run build    # build the SPA once (or `npm run dev` for HMR)
cd ..
COMPREHEND_OWNER_SECRET=dev-owner-secret uv run comprehend
# dashboard at http://127.0.0.1:8793/admin  (dev password: "dev")
```

With no `COMPREHEND_ADMIN_PASSWORD_HASH` set in dev, the dashboard accepts the password `dev`.
For HMR on the dashboard, run `npm run dev` in `web/` (Vite on :5173 proxies API + connector
paths to the backend on :8793).

Verify the whole stack: `uv run python spikes/smoke_e2e.py`. Seed demo data into a running
dev server: `uv run python spikes/seed_dev.py`.

## Deployment (oraclawd, behind Caddy)

1. Sync code to `/opt/comprehend`; `uv sync --frozen`; build the SPA (`web/dist`).
2. `comprehend gen-secret` (owner secret + session key), `comprehend hash-password` (admin).
3. Fill `/etc/comprehend/env` from `deploy/env.example` (chmod 600).
4. Install `deploy/comprehend.service`; `systemctl enable --now comprehend`.
5. Add `deploy/Caddyfile.snippet` as a **new** site block (do not touch the caddy-l4 config);
   reload Caddy. Add a grey-cloud A record `comprehend.fdosmith.dev`.

Owner connector URL: `https://comprehend.fdosmith.dev/owner/<secret>/mcp`.
Participant links are generated per person from the dashboard or the owner connector.
