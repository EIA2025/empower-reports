# Empower Reports — Flask + PostgreSQL

A school report management system built with Flask and PostgreSQL, ready to deploy on Render.

## Default Login
- **Username:** `admin`
- **Password:** `admin123`

Change these immediately after first login.

---

## Local Development

### 1. Install PostgreSQL
Make sure PostgreSQL is installed and running locally.

### 2. Create the database
```bash
createdb empower
```

### 3. Clone and install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment
```bash
cp .env.example .env
# Edit .env and set DATABASE_URL and SECRET_KEY
```

### 5. Run the app
```bash
python app.py
```
The app will auto-create all tables and seed the default admin on first run.
Visit: http://localhost:5000

---

## Deploy to Render

### Option A — Automatic with render.yaml (recommended)

1. Push your project to a GitHub repository.
2. Go to [https://render.com](https://render.com) and sign up / log in.
3. Click **"New"** → **"Blueprint"**.
4. Connect your GitHub repo.
5. Render reads `render.yaml` automatically — it will create:
   - A **Web Service** (your Flask app)
   - A **PostgreSQL database** (free tier)
   - Auto-links `DATABASE_URL` and generates a `SECRET_KEY`
6. Click **"Apply"** and wait for the build to finish.
7. Your app will be live at: `https://empower-reports.onrender.com` (or similar).

### Option B — Manual setup on Render

#### Step 1: Create a PostgreSQL Database
1. Log in to [https://dashboard.render.com](https://dashboard.render.com)
2. Click **"New"** → **"PostgreSQL"**
3. Fill in:
   - **Name:** `empower-db`
   - **Database:** `empower`
   - **User:** `empower_user`
   - **Plan:** Free
4. Click **"Create Database"**
5. Wait for it to be ready, then copy the **"Internal Database URL"** (starts with `postgresql://`)

#### Step 2: Create the Web Service
1. Click **"New"** → **"Web Service"**
2. Connect your GitHub repository
3. Fill in:
   - **Name:** `empower-reports`
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
   - **Plan:** Free
4. Under **"Environment Variables"**, add:
   - `DATABASE_URL` → paste the Internal Database URL from Step 1
   - `SECRET_KEY` → click "Generate" or type a long random string
5. Click **"Create Web Service"**

#### Step 3: First Deploy
- Render will build and deploy automatically.
- The app auto-creates all PostgreSQL tables on first start.
- Visit your service URL and log in with `admin` / `admin123`.

---

## Free PostgreSQL on Render — Important Notes

- Render's **free PostgreSQL** plan expires after **90 days**. You will need to recreate it.
- Free web services **spin down** after 15 minutes of inactivity. The first request after sleep takes ~30 seconds.
- To keep data permanently, upgrade to a paid database plan ($7/month).

---

## Free PostgreSQL Providers (alternatives to Render's built-in)

You can use any external PostgreSQL provider by setting the `DATABASE_URL` environment variable.

| Provider | Free Tier | Notes |
|----------|-----------|-------|
| **Supabase** | 500MB, no expiry | https://supabase.com → New Project → Settings → Database → Connection String |
| **Neon** | 512MB, no expiry | https://neon.tech → New Project → Connection string |
| **Railway** | $5 free credit/month | https://railway.app → New → Database → PostgreSQL |
| **ElephantSQL** | 20MB free | https://www.elephantsql.com (small projects only) |
| **Aiven** | 5GB, 30-day trial | https://aiven.io |

### How to connect an external database to Render:
1. Get the connection string from your provider (format: `postgresql://user:password@host:5432/dbname`)
2. In Render dashboard → your Web Service → **Environment** tab
3. Set `DATABASE_URL` = your connection string
4. Redeploy

---

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | ✅ Yes | PostgreSQL connection string |
| `SECRET_KEY` | ✅ Yes | Flask session signing key (long random string) |
| `PORT` | Auto | Set by Render automatically |

---

## Project Structure

```
empower-flask/
├── app.py              # Main Flask application & all routes
├── models.py           # SQLAlchemy ORM models (PostgreSQL)
├── pdf_generator.py    # ReportLab PDF generation
├── requirements.txt    # Python dependencies
├── Procfile            # Gunicorn start command
├── render.yaml         # Render Blueprint (auto-deploy config)
├── .env.example        # Environment variable template
└── templates/          # Jinja2 HTML templates
    ├── base.html
    ├── login.html
    ├── dashboard.html
    ├── students.html
    ├── staff.html
    ├── terms.html
    ├── marks.html
    ├── behavior.html
    ├── behavior_components.html
    ├── discipline.html
    ├── communications.html
    ├── decisions.html
    ├── visitation.html
    ├── generate_reports.html
    ├── analytics.html
    ├── report_design.html
    ├── comments.html
    ├── change_login.html
    ├── admin_management.html
    └── master_admin.html
```
