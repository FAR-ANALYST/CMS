# Get My Coach Uganda — Flask edition

A Python/Flask + Jinja rebuild of the Lovable React app.

## Features
- Three roles: **admin**, **coach**, **student** (stored in a separate `user_roles` table)
- Coaches submit a profile with photo upload → status becomes **submitted**
- Admin sees all submissions in **Pending verification**, can approve → status **paid + verified**
- Verified coaches appear in the public **Student directory** (filterable by sport / location)
- Admin (FAROUK) can also register coaches from the Coach page; their submission shows up in admin verification too
- FAROUK super-admin shortcut: log in with username `FAROUK` / password `FAROUK2020` (auto-seeded on first run)

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
Open http://localhost:5000

## Deploy on Render
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app` (add `gunicorn` to requirements.txt)
- Set env var `SECRET_KEY` to a random string

## Project layout
```
app.py                 # all routes, models, auth
requirements.txt
templates/
  base.html            # shared shell + nav
  auth.html            # login + signup
  coach.html           # coach profile editor
  admin.html           # verification dashboard
  student.html         # public directory
static/
  styles.css
  uploads/             # profile photos
instance/
  app.db               # sqlite database (auto-created)
```
