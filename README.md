# Get My Coach Uganda

Flask + Supabase Postgres + Render deployment.

## What changed from v1

- **Navy/red/blue theme** across every page
- **Role-based users** (`student`, `coach`, `admin`) — admin promoted via SQL
- **Coach approval flow**: coach submits → pending → admin approves → live
- **Admin can add coaches directly** (live immediately)
- **Live Events** section on home: admin uploads photos + info; multiple photos crossfade every 2 seconds
- **`Looking for a coach?`** tab — students must click it to browse
- Shows **first 8 coaches**; the rest only appear after using the search filters
- **Supabase Storage** for image uploads (replaces local `static/uploads`)
- **Postgres** instead of SQLite (works on Render's ephemeral filesystem)

## Files

```
getmycoach/
├── app.py              # Flask app
├── requirements.txt
├── Procfile            # gunicorn app:app
├── render.yaml         # Render blueprint (optional)
├── schema.sql          # Run this in Supabase SQL editor
├── static/styles.css
└── templates/
    ├── base.html
    ├── home.html       # Landing + live events carousel
    ├── coaches.html    # Looking-for-a-coach directory (8 + search)
    ├── welcome.html
    ├── login.html
    ├── signup.html     # Student or Coach role picker
    ├── coach.html      # Coach dashboard
    ├── admin.html      # Approvals + add coach + post events
    └── error.html
```

## Deployment (free tiers)

### 1. Supabase (database + storage)
1. Create a new project at https://supabase.com
2. **SQL Editor** → paste `schema.sql` → Run
3. **Storage** → New bucket named `uploads` → toggle **Public** ON
4. **Project Settings → Database** → copy the **Connection string (URI)** — that's your `DATABASE_URL`
5. **Project Settings → API** → copy `Project URL` (`SUPABASE_URL`) and `anon public` key (`SUPABASE_ANON_KEY`)

### 2. GitHub
Push this folder to a new GitHub repo.

### 3. Render
1. New → Web Service → connect your repo
2. **Build command:** `pip install -r requirements.txt`
3. **Start command:** `gunicorn app:app`
4. **Environment variables:**
   | Key | Value |
   |---|---|
   | `FLASK_SECRET` | any long random string |
   | `DATABASE_URL` | Supabase connection string |
   | `SUPABASE_URL` | `https://xxxx.supabase.co` |
   | `SUPABASE_ANON_KEY` | Supabase anon key |
   | `SUPABASE_BUCKET` | `uploads` |
5. Deploy

### 4. Create your admin account
After first deploy, sign up normally on the site (e.g. `farouk@yourdomain.com`), then in Supabase SQL Editor:
```sql
UPDATE users SET role='admin' WHERE email='farouk@yourdomain.com';
```
Log out, log back in — the **Admin** link appears in the nav.

## Local development
```bash
pip install -r requirements.txt
export DATABASE_URL="postgresql://..."
export SUPABASE_URL="https://...supabase.co"
export SUPABASE_ANON_KEY="..."
export SUPABASE_BUCKET="uploads"
export FLASK_SECRET="dev-secret"
python app.py
```
