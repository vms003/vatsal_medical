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
# Paths
# ---------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "db.json")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------------------------
# JSON Database helpers
# ---------------------------
def ensure_db_exists():
    """Create db file with default structure if missing or empty/invalid."""
    default = {"users": [], "medicines": [], "doctors": [], "prescriptions": []}
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w") as f:
            json.dump(default, f, indent=2)
        return
    try:
        # If file exists but empty or invalid, overwrite with default
        if os.path.getsize(DB_FILE) == 0:
            with open(DB_FILE, "w") as f:
                json.dump(default, f, indent=2)
            return
        with open(DB_FILE, "r") as f:
            data = json.load(f)
        # Validate top-level keys
        changed = False
        for k in default:
            if k not in data:
                data[k] = default[k]
                changed = True
        if changed:
            with open(DB_FILE, "w") as f:
                json.dump(data, f, indent=2)
    except Exception:
        # If any error parsing JSON, reset to default (safe for demo)
        with open(DB_FILE, "w") as f:
            json.dump(default, f, indent=2)


def read_db():
    ensure_db_exists()
    with open(DB_FILE, "r") as f:
        return json.load(f)


def write_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=2)


def next_id(items):
    if not items:
        return 1
    # find max id (ensure numeric)
    try:
        return max(int(i.get("id", 0)) for i in items) + 1
    except Exception:
        return len(items) + 1


# ---------------------------
# Flask setup
# ---------------------------
app = Flask(__name__, static_folder="../frontend", static_url_path="/")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# ---------------------------
# Utility: read incoming payload (json or form)
# ---------------------------
def get_request_data():
    """
    Returns a dict of incoming data supporting:
      - application/json
      - form data (request.form)
      - query parameters (request.values)
    """
    data = {}
    # try JSON first (silent=True avoids raising)
    json_data = request.get_json(silent=True)
    if isinstance(json_data, dict):
        data.update(json_data)
    # then form fields
    if request.form:
        data.update(request.form.to_dict())
    # also include values (query params or form)
    if request.values:
        data.update(request.values.to_dict())
    return data


# ---------------------------
# Auth Middleware
# ---------------------------
def auth_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        token = auth_header.replace("Bearer ", "").strip()
        if not token:
            return jsonify({"error": "missing token"}), 401
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
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
    data = get_request_data()
    name = data.get("name")
    email = data.get("email")
    password = data.get("password")
    language = data.get("language", "en")

    if not (name and email and password):
        return jsonify({"error": "missing fields"}), 400

    db = read_db()
    if any(u.get("email") == email for u in db["users"]):
        return jsonify({"error": "email exists"}), 400

    user_id = next_id(db["users"])
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    user = {
        "id": user_id,
        "name": name,
        "email": email,
        "password_hash": pw_hash,
        "language": language,
        "created_at": datetime.datetime.utcnow().isoformat()
    }
    db["users"].append(user)
    write_db(db)

    token = jwt.encode(
        {"id": user_id, "email": email, "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7)},
        SECRET_KEY, algorithm="HS256"
    )
    if isinstance(token, bytes):
        token = token.decode()

    # Return token + user so frontend can show dashboard immediately
    return jsonify({"token": token, "user": {"id": user_id, "name": name, "email": email, "language": language}})


# ---------------------------
# Login
# ---------------------------
@app.route("/api/login", methods=["POST"])
def login():
    data = get_request_data()
    email = data.get("email")
    password = data.get("password")

    if not (email and password):
        return jsonify({"error": "missing fields"}), 400

    db = read_db()
    user = next((u for u in db["users"] if u.get("email") == email), None)

    if not user or not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return jsonify({"error": "invalid"}), 401

    token = jwt.encode(
        {"id": user["id"], "email": user["email"], "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7)},
        SECRET_KEY, algorithm="HS256"
    )
    if isinstance(token, bytes):
        token = token.decode()

    return jsonify({"token": token, "user": {"id": user["id"], "name": user["name"], "email": user["email"], "language": user.get("language", "en")}})


# ---------------------------
# Profile
# ---------------------------
@app.route("/api/profile", methods=["GET", "PUT"])
@auth_required
def profile():
    db = read_db()
    user_id = request.user.get("id")
    user = next((u for u in db["users"] if u.get("id") == user_id), None)

    if not user:
        return jsonify({"error": "not found"}), 404

    if request.method == "GET":
        # avoid returning password_hash
        user_safe = {k: v for k, v in user.items() if k != "password_hash"}
        return jsonify({"user": user_safe})

    data = get_request_data()
    user["name"] = data.get("name", user.get("name"))
    user["language"] = data.get("language", user.get("language"))
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
    user_id = request.user.get("id")

    if request.method == "POST":
        data = get_request_data()
        name = data.get("name")
        if not name:
            return jsonify({"error": "missing name"}), 400
        med_id = next_id(db["medicines"])
        db["medicines"].append({
            "id": med_id,
            "user_id": user_id,
            "name": name,
            "dosage": data.get("dosage"),
            "schedules": data.get("schedules") or []
        })
        write_db(db)
        return jsonify({"ok": True})

    meds = [m for m in db["medicines"] if m.get("user_id") == user_id]
    return jsonify({"medicines": meds})


@app.route("/api/medicines/<int:med_id>", methods=["PUT", "DELETE"])
@auth_required
def medicine_detail(med_id):
    db = read_db()
    user_id = request.user.get("id")
    med = next((m for m in db["medicines"] if int(m.get("id", -1)) == med_id and m.get("user_id") == user_id), None)

    if not med:
        return jsonify({"error": "not found"}), 404

    if request.method == "PUT":
        data = get_request_data()
        med["name"] = data.get("name", med.get("name"))
        med["dosage"] = data.get("dosage", med.get("dosage"))
        med["schedules"] = data.get("schedules", med.get("schedules"))
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
    user_id = request.user.get("id")

    if request.method == "POST":
        data = get_request_data()
        name = data.get("name")
        if not name:
            return jsonify({"error": "missing name"}), 400
        doc_id = next_id(db["doctors"])
        doc = {
            "id": doc_id,
            "user_id": user_id,
            "name": name,
            "specialty": data.get("specialty"),
            "phone": data.get("phone"),
            "email": data.get("email"),
            "notes": data.get("notes", "")
        }
        db["doctors"].append(doc)
        write_db(db)
        return jsonify({"ok": True})

    docs = [d for d in db["doctors"] if d.get("user_id") == user_id]
    return jsonify({"doctors": docs})


@app.route("/api/doctors/<int:doc_id>", methods=["DELETE"])
@auth_required
def delete_doctor(doc_id):
    db = read_db()
    user_id = request.user.get("id")
    doc = next((d for d in db["doctors"] if int(d.get("id", -1)) == doc_id and d.get("user_id") == user_id), None)
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
    user_id = request.user.get("id")
    pres = [p for p in db["prescriptions"] if p.get("user_id") == user_id]
    # attach URL for convenience
    for p in pres:
        p["url"] = f"/uploads/{p.get('filename')}" if p.get("filename") else None
    return jsonify({"prescriptions": pres})


@app.route("/api/upload_prescription", methods=["POST"])
@auth_required
def upload_prescription():
    db = read_db()
    user_id = request.user.get("id")
    # doctor_name might be in form or json
    doctor_name = (request.form.get("doctor_name") or request.values.get("doctor_name") or request.args.get("doctor_name"))
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    filename = secure_filename(file.filename)
    # ensure unique filename to avoid collisions
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    filename_saved = f"{user_id}_{timestamp}_{filename}"
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename_saved)
    file.save(file_path)

    pres_id = next_id(db["prescriptions"])
    pres_entry = {
        "id": pres_id,
        "user_id": user_id,
        "doctor_name": doctor_name,
        "filename": filename_saved,
        "original_name": file.filename,
        "created_at": datetime.datetime.utcnow().isoformat()
    }
    db["prescriptions"].append(pres_entry)
    write_db(db)

    # return the new prescription including url for immediate UI update
    pres_entry["url"] = f"/uploads/{filename_saved}"
    return jsonify({"ok": True, "prescription": pres_entry})


@app.route("/api/prescriptions/<int:pres_id>", methods=["DELETE"])
@auth_required
def delete_prescription(pres_id):
    db = read_db()
    user_id = request.user.get("id")
    pres = next((p for p in db["prescriptions"] if int(p.get("id", -1)) == pres_id and p.get("user_id") == user_id), None)
    if not pres:
        return jsonify({"error": "not found"}), 404
    # delete file if exists
    try:
        if pres.get("filename"):
            path = os.path.join(app.config["UPLOAD_FOLDER"], pres.get("filename"))
            if os.path.exists(path):
                os.remove(path)
    except Exception:
        pass
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
