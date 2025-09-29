Medicine Reminder App - This is a minimal full-stack starter for your Medicine Reminder App.
=================================

Frontend: static HTML/CSS/JS (vanilla)
Backend: Flask (Python) with MySQL (use .env to configure)
Database: MySQL (schema.sql included)

Quick start:
1. Create a MySQL database and user, run sql/schema.sql to create tables.
2. fill DB credentials and SECRET_KEY in .env
3. Create a Python virtualenv, install requirements: pip install -r requirements.txt
4. Run the Flask app: python app.py
5. Serve frontend from the same Flask app (it serves /)

Files included:
- frontend/: index.html, styles.css, app.js, i18n JSON
- backend/: app.py, requirements.txt, .env
- sql/schema.sql

