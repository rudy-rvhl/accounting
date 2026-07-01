# Running & deploying QCRE

The web app runs the built-in **demo company** by default, so any of these give you a
working, browsable app. Point `QCRE_DB` at a saved database (`qcre seed --db my.db`) to use
your own data instead.

## 1. Run locally (Python)

```bash
git clone -b claude/practical-turing-lqagsk https://github.com/rudy-rvhl/accounting.git
cd accounting
python -m venv .venv && source .venv/bin/activate
pip install -e ".[pdf]"
uvicorn qcre.web.app:app --reload
# open http://localhost:8000
```

## 2. Run with Docker (one command, no Python setup)

```bash
docker build -t qcre .
docker run -p 8000:8000 qcre
# open http://localhost:8000
```

## 3. Deploy for a public URL

The `Dockerfile` works on any container host. Each of these gives you a live `https://…`
URL after connecting the repo:

- **Render** – New → Web Service → connect the repo → it auto-detects the Dockerfile → Create.
- **Railway** – New Project → Deploy from GitHub repo → it builds the Dockerfile.
- **Fly.io** – `fly launch` (detects the Dockerfile) → `fly deploy`.
- **Google Cloud Run** – `gcloud run deploy --source .` (reads `$PORT`, which the Dockerfile honours).

The container listens on `$PORT` (default 8000), so no extra configuration is needed. For a
persistent company database, attach a volume and set `QCRE_DB=/data/qcre.db`.

> Reminder: QCRE is decision-support only — not professional tax/accounting advice. Verify
> figures against current CRA / Revenu Québec sources and review with a CPA before relying
> on them.
