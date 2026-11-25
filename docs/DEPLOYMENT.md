# Free deployment: Vercel + Render

| Part | Host | Notes |
|---|---|---|
| Website (Next.js) | **Vercel** (Hobby) | Root directory `web`. `/api/v1/*` is proxied to the API. |
| Database (PostgreSQL) | **Vercel Storage → Neon** (free) | Created from the Vercel dashboard |
| API (FastAPI, Docker) | **Render** (free web service) | Deployed from [`render.yaml`](../render.yaml) |
| LLM (optional) | **Groq** free tier | Without a key, the assistant runs in offline mode |

Why the API isn't on Vercel: its scientific stack (NumPy, pandas, SciPy, statsmodels, LightGBM) is about 385 MB, over Vercel's limit for Python functions. The forecasting job also runs longer than a serverless function allows.

## 1. Database (in Vercel)

1. In Vercel, open **Storage → Create Database → Neon (Serverless Postgres)** and choose the free plan and a region close to the API (for example Frankfurt).
2. Open the database's **.env.local** tab and copy `DATABASE_URL`. A `postgres://…` URL is fine; the API converts it.

## 2. Load the demo data (from your machine, once)

Render's free CPU is small, so build the dataset and run the pipeline locally against the cloud database:

```bash
cd api
# PowerShell: $env:DATABASE_URL="<neon url>"   bash: export DATABASE_URL="<neon url>"
.venv/Scripts/alembic upgrade head
.venv/Scripts/python -m app.cli seed
```

## 3. API (Render)

1. Go to **New → Blueprint**, pick the GitHub repo, and Render reads `render.yaml`.
2. When prompted, paste the same `DATABASE_URL`.
3. Wait for the deploy, then open `https://<service>.onrender.com/health`. It should return `"database": "postgresql"`.
4. Optional: to use a real LLM, add `LLM_BASE_URL=https://api.groq.com/openai/v1`, `LLM_API_KEY=<key>` and `LLM_MODEL=llama-3.3-70b-versatile` under **Environment**.

Free instances sleep after about 15 minutes idle. The website shows a "waking up the demo server" banner and retries automatically.

## 4. Website (Vercel)

1. Go to **Add New → Project**, import the repo, and set **Root Directory** to `web`.
2. Add the environment variable `API_URL=https://<service>.onrender.com`. The `/api/v1` rewrite uses it at build time.
3. Click **Deploy**. If the Render URL changes later, update `API_URL` and redeploy.

## Optional: keep forecasts fresh

The in-process nightly scheduler only fires while the free instance is awake. To refresh reliably, add a GitHub Actions cron that calls the API:

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
