# Get My Coach Uganda — Flask version

Multi-coach submissions, admin approval queue, admin quick-add (auto-live), local photo uploads.

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000

A SQLite DB is auto-created at `instance/getmycoach.db` on first run.

## Default admin

- Email: `admin@getmycoach.ug`
- Password: `FAROUK`

The password `FAROUK` also works as an admin shortcut on the login page for any email — it will create/promote that account to admin.

## Roles & flow

- **Coach**: signs up, submits multiple coaches → each one sits in admin queue with status `submitted` until approved.
- **Admin**: at `/admin`, can directly add a coach (goes LIVE immediately), approve pending submissions, or remove any coach.
- **Student**: at `/student`, browses live coaches (verified + paid). Tap a card to reveal contact (call / WhatsApp / SMS).

## Deploy

- **Render**: push to GitHub, connect the repo. `render.yaml` is included.
- **Any host**: `gunicorn app:app` (see `Procfile`).

## File structure

```
app.py              # Flask app
schema.sql          # DB schema
requirements.txt
Procfile, render.yaml
templates/          # Jinja templates
static/styles.css
static/uploads/     # Photo uploads (gitignored)
```
