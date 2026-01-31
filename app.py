import os
import sqlite3
from flask import (
    Flask, request, jsonify,
    render_template, session,
    redirect
)
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# ---------- LOAD ENV ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# ---------- CONFIG ----------
DB_PATH = os.path.join(BASE_DIR, "leads.db")

SECRET_KEY = os.getenv("SECRET_KEY")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

if not SECRET_KEY or not ADMIN_USERNAME or not ADMIN_PASSWORD:
    raise RuntimeError("Missing environment variables")

ADMIN_PASSWORD_HASH = generate_password_hash(ADMIN_PASSWORD)

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static")
)

app.secret_key = SECRET_KEY

# ---------- DATABASE ----------
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ---------- PUBLIC ----------
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/contact", methods=["POST"])
def contact():
    if not request.is_json:
        return jsonify({"status": "error"}), 400

    data = request.get_json()
    name = data.get("name")
    phone = data.get("phone")
    message = data.get("message")

    if not name or not phone or not message:
        return jsonify({"status": "error"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO leads (name, phone, message) VALUES (?, ?, ?)",
        (name, phone, message)
    )
    conn.commit()
    conn.close()

    return jsonify({"status": "success"}), 200

# ---------- LOGIN ----------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if (
            username == ADMIN_USERNAME and
            check_password_hash(ADMIN_PASSWORD_HASH, password)
        ):
            session["admin_logged_in"] = True
            return redirect("/admin")

        return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")

# ---------- ADMIN ----------
@app.route("/admin")
def admin():
    if not session.get("admin_logged_in"):
        return redirect("/admin/login")

    conn = get_db_connection()
    cursor = conn.cursor()
    leads = cursor.execute(
        "SELECT * FROM leads ORDER BY created_at DESC"
    ).fetchall()
    conn.close()

    return render_template("admin.html", leads=leads)

# ---------- LOGOUT ----------
@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect("/admin/login")

# ---------- RUN ----------
if __name__ == "__main__":
    app.run()