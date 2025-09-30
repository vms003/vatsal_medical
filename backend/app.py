from flask import Flask, request, jsonify, send_from_directory
import os
import json
import bcrypt
import jwt
import datetime
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
from functools import wraps

# ---------------------------
# Load environment variables
# ---------------------------
load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY", "devkey")

# ---------------------------
# JSON Database Setup
# ---------------------------
DB_FILE = "db.json"
if not os.path.exists(DB_FILE):
    with open(DB_FILE, "w") as f:
        json.dump({"users": [], "medicines": [], "doctors": [], "prescriptions": []}, f)


def read_db():
    with open(DB_FILE, "r") as f:
        return json.load(f)


def write_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ---------------------------
# Upload folder
# ---------------------------
UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Flask setup
app = Flask(__name__, static_folder="../frontend", static_url_path="/")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# ---------------------------
# Auth Middleware
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
# Static Routes
# ---------------------------
@app.route("/")
def index():
    return app.send_static_file("login.html")


@app.route("/<path:fname>")
def static_files(fname):
    return app.send_static_file(fname)


# ---------------------------
# Register
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

    db = read_db()
    if any(u["email"] == email for u in db["users"]):
        return jsonify({"error": "email exists"}), 400

    user_id = len(db["users"]) + 1
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    db["users"].append({
        "id": user_id,
        "name": name,
        "email": email,
        "password_hash": pw_hash,
        "language": language,
        "created_at": datetime.datetime.utcnow().isoformat()
    })
    write_db(db)

    token = jwt.encode(
        {"id": user_id, "email": email, "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7)},
        SECRET_KEY, algorithm="HS256"
    )
    return jsonify({"token": token})


# ---------------------------
# Login
# ---------------------------
@app.route("/api/login", methods=["POST"])
def login():
    data = request.json or {}
    email = data.get("email")
    password = data.get("password")

    db = read_db()
    user = next((u for u in db["users"] if u["email"] == email), None)

    if not user or not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return jsonify({"error": "invalid"}), 401

    token = jwt.encode(
        {"id": user["id"], "email": user["email"], "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7)},
        SECRET_KEY, algorithm="HS256"
    )

    return jsonify({"token": token, "user": {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "language": user["language"]
    }})


# ---------------------------
# Profile
# ---------------------------
@app.route("/api/profile", methods=["GET", "PUT"])
@auth_required
def profile():
    db = read_db()
    user_id = request.user["id"]
    user = next((u for u in db["users"] if u["id"] == user_id), None)

    if not user:
        return jsonify({"error": "not found"}), 404

    if request.method == "GET":
        return jsonify({"user": user})

    data = request.json or {}
    user["name"] = data.get("name", user["name"])
    user["language"] = data.get("language", user["language"])
    if data.get("password"):
        user["password_hash"] = bcrypt.hashpw(data["password"].encode(), bcrypt.gensalt()).decode()

    write_db(db)
    return jsonify({"ok": True})


# ---------------------------
# Medicines CRUD
# ---------------------------
@app.route("/api/medicines", methods=["GET", "POST"])
@auth_required
def medicines():
    db = read_db()
    user_id = request.user["id"]

    if request.method == "POST":
        data = request.json or {}
        med_id = len(db["medicines"]) + 1
        db["medicines"].append({
            "id": med_id,
            "user_id": user_id,
            "name": data.get("name"),
            "dosage": data.get("dosage"),
            "schedules": data.get("schedules", [])
        })
        write_db(db)
        return jsonify({"ok": True})

    meds = [m for m in db["medicines"] if m["user_id"] == user_id]
    return jsonify({"medicines": meds})


@app.route("/api/medicines/<int:med_id>", methods=["PUT", "DELETE"])
@auth_required
def medicine_detail(med_id):
    db = read_db()
    user_id = request.user["id"]
    med = next((m for m in db["medicines"] if m["id"] == med_id and m["user_id"] == user_id), None)

    if not med:
        return jsonify({"error": "not found"}), 404

    if request.method == "PUT":
        data = request.json or {}
        med["name"] = data.get("name", med["name"])
        med["dosage"] = data.get("dosage", med["dosage"])
        med["schedules"] = data.get("schedules", med["schedules"])
        write_db(db)
        return jsonify({"ok": True})

    db["medicines"].remove(med)
    write_db(db)
    return jsonify({"ok": True})


# ---------------------------
# Doctors CRUD
# ---------------------------
@app.route("/api/doctors", methods=["GET", "POST"])
@auth_required
def doctors():
    db = read_db()
    user_id = request.user["id"]

    if request.method == "POST":
        data = request.json or {}
        doc_id = len(db["doctors"]) + 1
        db["doctors"].append({
            "id": doc_id,
            "user_id": user_id,
            "name": data.get("name"),
            "specialty": data.get("specialty"),
            "phone": data.get("phone"),
            "email": data.get("email"),
            "notes": data.get("notes", "")
        })
        write_db(db)
        return jsonify({"ok": True})

    docs = [d for d in db["doctors"] if d["user_id"] == user_id]
    return jsonify({"doctors": docs})


@app.route("/api/doctors/<int:doc_id>", methods=["DELETE"])
@auth_required
def delete_doctor(doc_id):
    db = read_db()
    user_id = request.user["id"]
    doc = next((d for d in db["doctors"] if d["id"] == doc_id and d["user_id"] == user_id), None)
    if not doc:
        return jsonify({"error": "not found"}), 404
    db["doctors"].remove(doc)
    write_db(db)
    return jsonify({"ok": True})


# ---------------------------
# Prescriptions (Upload + CRUD)
# ---------------------------
@app.route("/api/prescriptions", methods=["GET"])
@auth_required
def get_prescriptions():
    db = read_db()
    user_id = request.user["id"]
    pres = [p for p in db["prescriptions"] if p["user_id"] == user_id]
    return jsonify({"prescriptions": pres})


@app.route("/api/upload_prescription", methods=["POST"])
@auth_required
def upload_prescription():
    db = read_db()
    user_id = request.user["id"]
    doctor_name = request.form.get("doctor_name")
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    filename = secure_filename(file.filename)
    file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

    pres_id = len(db["prescriptions"]) + 1
    db["prescriptions"].append({
        "id": pres_id,
        "user_id": user_id,
        "doctor_name": doctor_name,
        "filename": filename,
        "original_name": file.filename
    })
    write_db(db)
    return jsonify({"ok": True})


@app.route("/api/prescriptions/<int:pres_id>", methods=["DELETE"])
@auth_required
def delete_prescription(pres_id):
    db = read_db()
    user_id = request.user["id"]
    pres = next((p for p in db["prescriptions"] if p["id"] == pres_id and p["user_id"] == user_id), None)
    if not pres:
        return jsonify({"error": "not found"}), 404
    db["prescriptions"].remove(pres)
    write_db(db)
    return jsonify({"ok": True})


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# ---------------------------
# Health Check
# ---------------------------
@app.route("/api/ping")
def ping():
    return jsonify({"ok": True, "time": datetime.datetime.utcnow().isoformat()})


# ---------------------------
# Run
# ---------------------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
