# Free deployment

Everything below has a free tier with no credit card required (at the time of writing). Check each provider's current limits.

| Piece | Free option | Alternative |
|---|---|---|
| PostgreSQL | [Neon](https://neon.tech) | Supabase |
| API (Docker) | [Render](https://render.com) web service | Fly.io, Koyeb, Railway trial |
| Web | [Vercel](https://vercel.com) Hobby | Netlify, Cloudflare Pages |
| LLM | [Groq](https://console.groq.com) free tier | Google AI Studio (Gemini), OpenRouter free models |
| CI | GitHub Actions (free for public repos) | |

## 1. Database (Neon)

1. Create a project and copy the connection string. Change the scheme to `postgresql+psycopg://`.
2. In the Neon SQL editor, create the read-only role used by the assistant:

   ```sql
   CREATE ROLE rafta_readonly LOGIN PASSWORD '<strong-password>';
   GRANT USAGE ON SCHEMA public TO rafta_readonly;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO rafta_readonly;
   ALTER ROLE rafta_readonly SET default_transaction_read_only = on;
   ```

   If the tables already exist, also run `GRANT SELECT ON ALL TABLES IN SCHEMA public TO rafta_readonly;`.

## 2. API (Render)

1. Create a new **Web Service** from your GitHub repo, with root directory `api` and the **Docker** runtime.
2. Set these environment variables:

   ```
   DATABASE_URL=postgresql+psycopg://<user>:<pw>@<neon-host>/<db>?sslmode=require
   DATABASE_READONLY_URL=postgresql+psycopg://rafta_readonly:<pw>@<neon-host>/<db>?sslmode=require
   CORS_ORIGINS=["https://<your-app>.vercel.app"]
   SEED_ON_STARTUP=true
   LLM_BASE_URL=https://api.groq.com/openai/v1
   LLM_API_KEY=<groq key>
   ```

3. Set the health check path to `/health`. The Dockerfile already runs `alembic upgrade head` on start.

Free instances sleep when idle, so the first request after a sleep takes about 30–60 s. The in-process nightly scheduler only fires while the instance is awake. To keep it reliable on a free tier, add a GitHub Actions cron that calls `POST /api/v1/jobs {"job_type":"refresh"}`.

## 3. Web (Vercel)

1. Import the repo with root directory `web`.
2. Add the environment variable `API_URL=https://<your-api>.onrender.com`. It is used by the `/api/v1` rewrite at build time.
3. Deploy.

## Optional: scheduled refresh with GitHub Actions

```yaml
# .github/workflows/nightly.yml
on:
  schedule: [{ cron: "0 2 * * *" }]
  workflow_dispatch:
jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - run: |
          curl -fsS -X POST "${{ secrets.API_URL }}/api/v1/jobs" \
            -H 'content-type: application/json' -d '{"job_type":"refresh"}'
```
