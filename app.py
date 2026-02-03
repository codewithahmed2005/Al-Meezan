import os
import sqlite3
import smtplib
from email.message import EmailMessage
import csv
import io
from datetime import datetime

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

EMAIL_HOST = os.getenv("EMAIL_HOST")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "0"))
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_TO = os.getenv("EMAIL_TO")

if not all([
    SECRET_KEY,
    ADMIN_USERNAME,
    ADMIN_PASSWORD,
    EMAIL_HOST,
    EMAIL_PORT,
    EMAIL_USER,
    EMAIL_PASSWORD,
    EMAIL_TO
]):
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
            status TEXT DEFAULT 'new',
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

# ---------- ADMIN DASHBOARD ----------
@app.route("/admin")
def admin():
    if not session.get("admin_logged_in"):
        return redirect("/admin/login")

    search = request.args.get("search", "").strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    if search:
        leads = cursor.execute(
            """
            SELECT * FROM leads
            WHERE name LIKE ? OR phone LIKE ? OR message LIKE ?
            ORDER BY created_at DESC
            """,
            (f"%{search}%", f"%{search}%", f"%{search}%")
        ).fetchall()
    else:
        leads = cursor.execute(
            "SELECT * FROM leads ORDER BY created_at DESC"
        ).fetchall()

    conn.close()
    return render_template("admin.html", leads=leads, search=search)

# ---------- MARK CONTACTED ----------
@app.route("/admin/mark/<int:lead_id>")
def mark_contacted(lead_id):
    if not session.get("admin_logged_in"):
        return redirect("/admin/login")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE leads SET status='contacted' WHERE id=?",
        (lead_id,)
    )
    conn.commit()
    conn.close()

    return redirect("/admin")

# ---------- DELETE LEAD ----------
@app.route("/admin/delete/<int:lead_id>")
def delete_lead(lead_id):
    if not session.get("admin_logged_in"):
        return redirect("/admin/login")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM leads WHERE id=?", (lead_id,))
    conn.commit()
    conn.close()

    return redirect("/admin")

# ---------- EMAIL BACKUP CORE ----------
def send_db_backup_email():
    conn = get_db_connection()
    cursor = conn.cursor()
    rows = cursor.execute(
        "SELECT id, name, phone, message, status, created_at FROM leads ORDER BY created_at DESC"
    ).fetchall()
    conn.close()

    if not rows:
        return False

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Name", "Phone", "Message", "Status", "Created At"])

    for row in rows:
        writer.writerow([
            row["id"],
            row["name"],
            row["phone"],
            row["message"],
            row["status"],
            row["created_at"]
        ])

    csv_data = output.getvalue()
    output.close()

    msg = EmailMessage()
    msg["Subject"] = f"Leads Backup - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_TO
    msg.set_content("Attached is the latest leads database backup.")

    msg.add_attachment(
        csv_data,
        subtype="csv",
        filename="leads_backup.csv"
    )

    with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASSWORD)
        server.send_message(msg)

    return True

# ---------- MANUAL BACKUP ROUTE ----------
@app.route("/admin/backup")
def admin_backup():
    if not session.get("admin_logged_in"):
        return redirect("/admin/login")

    success = send_db_backup_email()
    return "Backup email sent successfully." if success else "No data to backup."

# ---------- LOGOUT ----------
@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect("/admin/login")

# ---------- RUN ----------
if __name__ == "__main__":
    app.run()
