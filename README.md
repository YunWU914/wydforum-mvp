# OpenForum — multilingual community forum MVP

A self-contained, zero-cost forum MVP for a **global, open-registration community**:
Django 5.2 + SQLite, multi-language UI (English / 简体中文 / 日本語 / Español), email
activation, CAPTCHA hooks, rate limiting, and placeholder legal pages — runnable with
one Docker command or one click on GitHub Codespaces.

> This is an MVP test build. The legal documents are placeholders and must be
> reviewed by a qualified lawyer before a public launch.

---

## Features

| Area | What's included |
|---|---|
| Community | Categories, topics, replies, search, sort (latest / popular / unanswered), pinning/locking/hiding, reports, moderation admin |
| Accounts | Open registration, **email activation** (single-use, hashed, expiring tokens), username **or** email sign-in, no user enumeration |
| Anti-abuse | **Cloudflare Turnstile / Google reCAPTCHA** (server-side verification), honeypot + minimum-fill-time traps, disposable-email blocklist, DB-backed **rate limits** (register / login / topics / replies / reports / resend), fail-closed CAPTCHA verification, 429 page |
| i18n | Django i18n framework, 4 languages, header language switcher, `Accept-Language` + cookie negotiation, pure-Python `.po`/`.mo` compiler (no GNU gettext needed) |
| Compliance | Footer **Terms of Service / Privacy Policy / Guidelines** placeholders (GDPR/CCPA-aware structure, `[[PLACEHOLDER]]` markers), cookie notice, essential-cookies-only |
| Ops | Dockerfile (non-root, healthcheck), docker-compose (SQLite volume), production compose with **Caddy auto-HTTPS**, GitHub Actions CI + GHCR image, Codespaces dev container |

---

## Quickstart (Docker — recommended)

```bash
cd forum-mvp
docker compose up --build
# open http://localhost:8000
```

- Activation emails are printed to the container logs:
  `docker compose logs -f web | grep activate`
- Demo content (dev only): set `SEED_DEMO=1` in `.env`, or run
  `docker compose exec web python manage.py seed_demo --demo`
  → accounts `ada` / `lin` / `kenji`, password `DemoPass!2026`
- Admin panel: create a superuser with
  `docker compose exec web python manage.py createsuperuser`
- Data lives in the `forum_data` Docker volume (`/app/data/db.sqlite3`).

## Quickstart (bare Python 3.12+)

```bash
cd forum-mvp
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python tools/build_locales.py
mkdir -p data
python manage.py migrate
python manage.py createcachetable
python manage.py seed_demo --demo    # optional demo content
DJANGO_DEBUG=1 python manage.py runserver
```

Windows PowerShell: `$env:DJANGO_DEBUG="1"` before `runserver`.

---

## The GitHub path (zero cost)

1. **Push the project**

   ```bash
   cd forum-mvp
   git init && git add -A && git commit -m "OpenForum MVP"
   git branch -M main
   gh repo create openforum-mvp --public --source=. --push   # or add a remote manually
   ```

   CI runs automatically on every push: translation completeness check,
   `manage.py check`, migration drift check, and the test suite.

2. **Try it in the cloud — GitHub Codespaces (free tier)**

   Repo page → **Code → Codespaces → Create codespace**. The dev container installs
   deps, migrates, seeds demo data and starts the server; the browser opens the
   forwarded port automatically. Free tier includes 120 core-hours/month.

3. **Container images**

   Every push to `main` builds an image to
   `ghcr.io/<you>/openforum-mvp` (`.github/workflows/docker.yml`). Pull it anywhere:

   ```bash
   docker run -p 8000:8000 \
     -e DJANGO_DEBUG=0 -e DJANGO_SECRET_KEY=change-me \
     -e DJANGO_ALLOWED_HOSTS=forum.example.com \
     -v forum_data:/app/data \
     ghcr.io/<you>/openforum-mvp
   ```

### Hosting options that cost nothing

| Option | Notes |
|---|---|
| **Your PC + Cloudflare Tunnel** | Run `docker compose up` locally; expose via `cloudflared tunnel`. Genuinely free; keep `DJANGO_DEBUG=0` and set keys. |
| **Oracle Cloud Always-Free VM** | 4 ARM cores / 24 GB RAM free forever. Install Docker, use `docker-compose.prod.yml` (Caddy issues a free Let's Encrypt certificate). |
| **Render / Railway free tier** | Deploys the GHCR image in minutes — but free tiers have **ephemeral disks**, so the SQLite volume resets on redeploy. Fine for a demo, not for real data. |
| **GitHub Pages / static hosts** | Not applicable: Django needs a server process, not static hosting. |

### Production compose (Caddy + HTTPS)

```bash
export DOMAIN=forum.example.com
export DJANGO_SECRET_KEY=$(python -c "import secrets;print(secrets.token_urlsafe(50))")
export TURNSTILE_SITE_KEY=... TURNSTILE_SECRET_KEY=...
export EMAIL_HOST=smtp.example.com EMAIL_HOST_USER=... EMAIL_HOST_PASSWORD=...
docker compose -f docker-compose.prod.yml up -d --build
```

---

## Configuration reference

Everything is environment-driven (see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_DEBUG` | `0` | `1` for local dev only; `0` enables HSTS/secure cookies/SSL redirect |
| `DJANGO_SECRET_KEY` | — (required when `DEBUG=0`) | Generate: `python -c "import secrets;print(secrets.token_urlsafe(50))"` |
| `DJANGO_ALLOWED_HOSTS` | localhost set | Comma-separated hosts (`example.com,.app.github.dev`) |
| `SITE_NAME` / `SITE_URL` / `SITE_TAGLINE` | OpenForum / localhost / … | Branding + activation-link base URL |
| `CAPTCHA_PROVIDER` | `none` | `turnstile` or `recaptcha` (+ site/secret keys). Without keys the widget is skipped and honeypot + rate limits still apply |
| `EMAIL_BACKEND` | console | Console prints activation links; switch to SMTP in prod |
| `EMAIL_VERIFICATION_TTL_HOURS` | `48` | Activation link lifetime |
| `TRUST_X_FORWARDED_FOR` | `0` | `1` only behind Caddy/nginx |
| `POSTGRES_HOST` (+ `POSTGRES_DB/USER/PASSWORD/PORT`) | SQLite | Switch database without code changes (`psycopg` extra required) |

**Rate limits** live in one place, `community/views.py` → `LIMITS`
(register 5/h/IP, login 10/15min, topics 5/h + 20/day per user, replies 20/h + 100/day,
reports 10/h, resend 5/h + 3/email). Tune and redeploy; they use the database cache,
so they are shared across all gunicorn workers.

## Adding a language

1. Add the code + native name to `LANGUAGES` in `config/settings.py`.
2. Copy a catalog in `tools/locales/` (e.g. `de.json`), translate the values.
3. Register it in `LOCALES` in `tools/build_locales.py` (code + plural rule).
4. `python tools/build_locales.py` → `.po`/`.mo` are regenerated (also happens in
   the Docker build and the container entrypoint).
5. `python tools/build_locales.py --check` fails CI when a catalog is incomplete.

## Legal placeholders — before you launch

The pages under `/legal/` are deliberately structured but generic:

- [ ] Replace `[[PLACEHOLDER]]` markers (entity, address, DPO, transfer mechanism)
- [ ] Set `LEGAL_COMPANY`, `LEGAL_JURISDICTION`, `LEGAL_EFFECTIVE_DATE`,
      `LEGAL_CONTACT_EMAIL` env vars
- [ ] Have counsel review Terms / Privacy / Guidelines for your jurisdiction
- [ ] Add a DMCA/copyright agent process if you accept user content publicly
- [ ] Confirm the minimum age and parental-consent rule for your audience

## Project structure

```
forum-mvp/
├── config/               Django project (settings read from env + .env)
├── community/            The app: models, views, forms, captcha, ratelimit, i18n, tests
├── templates/            base layout, forum pages, auth pages, legal/, error pages
├── static/               one stylesheet + one small JS file (CSP-safe, no build step)
├── locale/               generated .po/.mo catalogs
├── tools/
│   ├── build_locales.py  extraction + pure-Python .mo compiler (--check gates CI)
│   └── locales/*.json    editable translation sources
├── Dockerfile            multi-stage, non-root, healthcheck
├── docker-compose.yml    local dev (SQLite volume, console email)
├── docker-compose.prod.yml + Caddyfile   auto-HTTPS production profile
└── .github/workflows/    CI (tests) + GHCR image build
```

## Tests

```bash
python manage.py test          # 15 tests: registration→activation→login flow,
                               # honeypot, disposable email, posting rules,
                               # localization, rate limits, legal pages
```
