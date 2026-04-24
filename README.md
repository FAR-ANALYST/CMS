# Get My Coach Uganda — Render Deployment

## Files
- `app.py` — Flask app (auto-creates DB on startup, ProxyFix for Render, secure cookies)
- `schema.sql` — SQLite schema (users + coach_submissions)
- `requirements.txt` — Python deps
- `Procfile` — gunicorn start command
- `render.yaml` — Render Blueprint (one-click deploy)
- `runtime.txt` — pins Python 3.11.9
- `.gitignore`
- `templates/` — base, student, coach, admin, login, signup, error
- `static/styles.css`

## Deploy on Render

1. Push these files to a new GitHub repo (preserve the `templates/` and `static/` folders).
2. On Render → **New → Blueprint** → connect the repo. `render.yaml` configures everything.
   *(Or **New → Web Service** with build `pip install -r requirements.txt` and start `gunicorn app:app --bind 0.0.0.0:$PORT`.)*
3. Set env vars (Blueprint auto-creates `FLASK_SECRET`):
   - `ADMIN_EMAIL` (default `admin@getmycoach.ug`)
   - `ADMIN_PASSWORD` (default `FAROUK`)
   - `RENDER=true`

## Default admin login
- Email: `admin@getmycoach.ug`
- Password: `FAROUK`

## Workflow
1. Coach signs up → fills profile → submits (status: *Awaiting verification*).
2. Admin sees it under **Pending** → clicks **Mark paid & live**.
3. Coach appears on the public Student directory with Call / WhatsApp / SMS buttons.
4. Admin can also **Quick add** coaches that go live immediately.

## Note on Render free tier
The filesystem is ephemeral — uploaded images and the SQLite DB reset on redeploy/sleep. For production, mount a Render Disk or migrate to PostgreSQL + S3-compatible storage.
