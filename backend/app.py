
from flask import Flask, request, jsonify, send_from_directory
import os
import pymysql
import bcrypt
import jwt
import datetime
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
from functools import wraps
import urllib.parse

# ---------------------------
# Load environment variables
# ---------------------------
load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY", "devkey")

# ---------------------------
# MySQL Config (Auto-detect Railway)
# ---------------------------
db_url = os.getenv("DATABASE_URL")
if db_url:
    url = urllib.parse.urlparse(db_url)
    DB = {
        "host": url.hostname,
        "port": url.port or 3306,
        "user": url.username,
        "password": url.password,
        "db": url.path[1:],  # remove leading '/'
        "cursorclass": pymysql.cursors.DictCursor,
    }
else:
    DB = {
        "host": os.getenv("DB_HOST", "127.0.0.1"),
        "port": int(os.getenv("DB_PORT", 3306)),
        "user": os.getenv("DB_USER", "root"),
        "password": os.getenv("DB_PASS", ""),
        "db": os.getenv("DB_NAME", "medreminder"),
        "cursorclass": pymysql.cursors.DictCursor,
    }

# ---------------------------
# Uploads folder
# ---------------------------
UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Flask app setup (frontend folder for static files)
app = Flask(__name__, static_folder="../frontend", static_url_path="/")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


def get_conn():
    return pymysql.connect(**DB)


# ---------------------------
# Authentication Middleware
# ---------------------------
def auth_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not auth:
            return jsonify({"error": "missing token"}), 401
        try:
            payload = jwt.decode(auth, SECRET_KEY, algorithms=["HS256"])
            request.user = payload
        except Exception:
            return jsonify({"error": "invalid token"}), 401
        return f(*args, **kwargs)

    return wrapper


# ---------------------------
# Routes (static frontend)
# ---------------------------
@app.route("/")
def index():
    return app.send_static_file("login.html")


@app.route("/<path:fname>")
def static_files(fname):
    return app.send_static_file(fname)


# ---------------------------
# User Registration
# ---------------------------
@app.route("/api/register", methods=["POST"])
def register():
    data = request.json or {}
    name = data.get("name")
    email = data.get("email")
    password = data.get("password")
    language = data.get("language", "en")

    if not (name and email and password):
        return jsonify({"error": "missing fields"}), 400

    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (name,email,password_hash,language) VALUES (%s,%s,%s,%s)",
                (name, email, pw_hash, language),
            )
            conn.commit()
            user_id = cur.lastrowid
    except pymysql.err.IntegrityError:
        return jsonify({"error": "email exists"}), 400
    finally:
        conn.close()

    token = jwt.encode(
        {"id": user_id, "email": email, "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7)},
        SECRET_KEY,
        algorithm="HS256",
    )
    if isinstance(token, bytes):
        token = token.decode()

    return jsonify({"token": token})


# ---------------------------
# User Login
# ---------------------------
@app.route("/api/login", methods=["POST"])
def login():
    data = request.json or {}
    email = data.get("email")
    password = data.get("password")

    if not (email and password):
        return jsonify({"error": "missing fields"}), 400

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE email=%s", (email,))
            user = cur.fetchone()

        if not user or not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
            return jsonify({"error": "invalid"}), 401

        token = jwt.encode(
            {"id": user["id"], "email": user["email"], "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7)},
            SECRET_KEY,
            algorithm="HS256",
        )
        if isinstance(token, bytes):
            token = token.decode()

        return jsonify(
            {
                "token": token,
                "user": {
                    "id": user["id"],
                    "name": user["name"],
                    "email": user["email"],
                    "language": user["language"],
                },
            }
        )
    finally:
        conn.close()


# ---------------------------
# Profile (GET + UPDATE)
# ---------------------------
@app.route("/api/profile", methods=["GET", "PUT"])
@auth_required
def profile():
    user_id = request.user["id"]
    conn = get_conn()
    try:
        if request.method == "GET":
            with conn.cursor() as cur:
                cur.execute("SELECT id, name, email, language, created_at FROM users WHERE id=%s", (user_id,))
                user = cur.fetchone()
            return jsonify({"user": user})

        if request.method == "PUT":
            data = request.json or {}
            name = data.get("name")
            language = data.get("language")
            password = data.get("password")

            with conn.cursor() as cur:
                if password:
                    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
                    cur.execute(
                        "UPDATE users SET name=%s, language=%s, password_hash=%s WHERE id=%s",
                        (name, language, pw_hash, user_id),
                    )
                else:
                    cur.execute("UPDATE users SET name=%s, language=%s WHERE id=%s", (name, language, user_id))
                conn.commit()
            return jsonify({"ok": True})
    finally:
        conn.close()


# ---------------------------
# Medicines (CRUD)
# ---------------------------
@app.route("/api/medicines", methods=["GET", "POST"])
@auth_required
def medicines():
    user_id = request.user["id"]
    conn = get_conn()
    try:
        if request.method == "POST":
            data = request.json or {}
            name = data.get("name")
            dosage = data.get("dosage")
            schedules = data.get("schedules", [])

            if not name:
                return jsonify({"error": "missing name"}), 400

            with conn.cursor() as cur:
                cur.execute("INSERT INTO medicines (user_id,name,dosage) VALUES (%s,%s,%s)", (user_id, name, dosage))
                med_id = cur.lastrowid

                for s in schedules:
                    t = s.get("time")
                    days = ",".join(s.get("days", [])) if s.get("days") else None
                    cur.execute(
                        "INSERT INTO medicine_schedules (medicine_id,time,days_of_week) VALUES (%s,%s,%s)",
                        (med_id, t + ":00" if t and len(t.split(":")) == 2 else t, days),
                    )
                conn.commit()
            return jsonify({"ok": True})

        # GET medicines
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT m.*,
                       (SELECT GROUP_CONCAT(CONCAT(time,'|',IFNULL(days_of_week,'')) SEPARATOR ';')
                        FROM medicine_schedules
                        WHERE medicine_id=m.id) AS schedules
                FROM medicines m
                WHERE m.user_id=%s
                """,
                (user_id,),
            )
            meds = cur.fetchall()

            for m in meds:
                sc = m.pop("schedules")
                rows = []
                if sc:
                    for part in sc.split(";"):
                        if not part:
                            continue
                        if "|" in part:
                            time, days = part.split("|", 1)
                        else:
                            time, days = part, ""
                        rows.append({"time": time, "days": days.split(",") if days else []})
                m["schedules"] = rows

        return jsonify({"medicines": meds})
    finally:
        conn.close()


@app.route("/api/medicines/<int:med_id>", methods=["PUT", "DELETE"])
@auth_required
def medicine_detail(med_id):
    user_id = request.user["id"]
    conn = get_conn()
    try:
        if request.method == "PUT":
            data = request.json or {}
            name = data.get("name")
            dosage = data.get("dosage")
            schedules = data.get("schedules", [])

            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE medicines SET name=%s, dosage=%s WHERE id=%s AND user_id=%s",
                    (name, dosage, med_id, user_id),
                )
                cur.execute("DELETE FROM medicine_schedules WHERE medicine_id=%s", (med_id,))
                for s in schedules:
                    t = s.get("time")
                    days = ",".join(s.get("days", [])) if s.get("days") else None
                    cur.execute(
                        "INSERT INTO medicine_schedules (medicine_id,time,days_of_week) VALUES (%s,%s,%s)",
                        (med_id, t + ":00" if t and len(t.split(":")) == 2 else t, days),
                    )
                conn.commit()
            return jsonify({"ok": True})

        if request.method == "DELETE":
            with conn.cursor() as cur:
                cur.execute("DELETE FROM medicine_schedules WHERE medicine_id=%s", (med_id,))
                cur.execute("DELETE FROM medicines WHERE id=%s AND user_id=%s", (med_id, user_id))
                conn.commit()
            return jsonify({"ok": True})
    finally:
        conn.close()


# ---------------------------
# Doctors (CRUD)
# ---------------------------
@app.route("/api/doctors", methods=["GET", "POST"])
@auth_required
def doctors():
    user_id = request.user["id"]
    conn = get_conn()
    try:
        if request.method == "POST":
            data = request.json or {}
            name = data.get("name")
            specialty = data.get("specialty")
            phone = data.get("phone")
            email = data.get("email")
            notes = data.get("notes", "")
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO doctors (user_id,name,phone,email,notes) VALUES (%s,%s,%s,%s,%s)",
                    (user_id, name, phone, email, notes),
                )
                conn.commit()
            return jsonify({"ok": True})

        if request.method == "GET":
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM doctors WHERE user_id=%s", (user_id,))
                docs = cur.fetchall()
            return jsonify({"doctors": docs})
    finally:
        conn.close()


@app.route("/api/doctors/<int:doc_id>", methods=["DELETE"])
@auth_required
def delete_doctor(doc_id):
    user_id = request.user["id"]
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM doctors WHERE id=%s AND user_id=%s", (doc_id, user_id))
            conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()


# ---------------------------
# Prescriptions (CRUD + Upload)
# ---------------------------
@app.route("/api/prescriptions", methods=["GET"])
@auth_required
def get_prescriptions():
    user_id = request.user["id"]
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM prescriptions WHERE user_id=%s", (user_id,))
            pres = cur.fetchall()
        return jsonify({"prescriptions": pres})
    finally:
        conn.close()


@app.route("/api/upload_prescription", methods=["POST"])
@auth_required
def upload_prescription():
    user_id = request.user["id"]
    doctor_name = request.form.get("doctor_name")
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    filename = secure_filename(file.filename)
    file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO prescriptions (user_id, doctor_name, filename, original_name) VALUES (%s,%s,%s,%s)",
                (user_id, doctor_name, filename, file.filename),
            )
            conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()


@app.route("/api/prescriptions/<int:pres_id>", methods=["DELETE"])
@auth_required
def delete_prescription(pres_id):
    user_id = request.user["id"]
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM prescriptions WHERE id=%s AND user_id=%s", (pres_id, user_id))
            conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# ---------------------------
# Health check
# ---------------------------
@app.route("/api/ping")
def ping():
    return jsonify({"ok": True, "time": datetime.datetime.utcnow().isoformat()})


# ---------------------------
# Main Entry
# ---------------------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
