# Empower Reports — Flask + Supabase (PostgreSQL)

A school report management system built with Flask and Supabase (PostgreSQL), deployable on Render.

## Default Login
- **Username:** `admin`
- **Password:** `admin123`

Change these immediately after first login.

---

## Supabase Database Setup (one time)

1. Go to [https://supabase.com](https://supabase.com) and create a free account.
2. Click **"New project"** — give it a name, set a strong database password, choose a region.
3. Wait ~2 minutes for the project to be ready.
4. Go to **Project Settings → Database → Connection string**.
5. Click the **"Transaction pooler"** tab (port **6543** — NOT Session mode).
6. Copy the connection string. It looks like:
   ```
   postgresql://postgres.xxxxxxxxxxxx:[YOUR-PASSWORD]@aws-0-xx-xxxx.pooler.supabase.com:6543/postgres
   ```
7. Replace `[YOUR-PASSWORD]` with the password you set when creating the project.

> **Important:** Use the **Transaction pooler** tab (port 6543), not Session mode (port 5432).
> The Transaction pooler is required for stateless web servers like Render's free tier.

---

## Deploy to Render

1. Push this folder to a GitHub repository.
2. Go to [https://render.com](https://render.com) → **New → Web Service**.
3. Connect your GitHub repo.
4. Fill in:
   - **Environment:** Python
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
5. Under **Environment Variables**, add:
   - `DATABASE_URL` → paste your Supabase transaction pooler URL (from step 6 above)
   - `SECRET_KEY` → click **Generate** or paste a long random string
   - `PYTHON_VERSION` → `3.11.9`
6. Click **Create Web Service**.
7. The app auto-creates all tables and seeds default data on first start.
8. Log in with `admin` / `admin123`.

---

## Local Development

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up environment
cp .env.example .env
# Edit .env — paste your Supabase DATABASE_URL

# 3. Run
python app.py
# Visit http://localhost:5000
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | ✅ Yes | Supabase Transaction Pooler URL (port 6543) |
| `SECRET_KEY` | ✅ Yes | Flask session key — long random string |
| `PYTHON_VERSION` | Render only | Set to `3.11.9` |

---

## Project Structure

```
empower-flask/
├── app.py              # Flask app — all routes and logic
├── models.py           # SQLAlchemy ORM models
├── pdf_generator.py    # ReportLab PDF generation
├── requirements.txt    # Python dependencies (no pandas/numpy)
├── Procfile            # Gunicorn start command
├── render.yaml         # Render deployment config
├── runtime.txt         # Pin Python 3.11.9
├── .env.example        # Environment variable template
└── templates/          # 23 Jinja2 HTML templates
```
