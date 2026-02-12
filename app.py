import os
import sqlite3
import threading
import csv
import io
import base64
import requests
from datetime import datetime

from flask import (
    Flask, request, jsonify,
    render_template, session,
    redirect, send_file
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

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO")
BACKUP_KEY = os.getenv("BACKUP_KEY")

if not all([
    SECRET_KEY,
    ADMIN_USERNAME,
    ADMIN_PASSWORD,
    SENDGRID_API_KEY,
    EMAIL_FROM,
    EMAIL_TO,
    BACKUP_KEY
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
    conn.execute("""
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
    data = request.get_json(force=True)

    name = data.get("name")
    phone = data.get("phone")
    message = data.get("message")

    if not name or not phone or not message:
        return jsonify({"status": "error"}), 400

    conn = get_db_connection()
    conn.execute(
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

    conn = get_db_connection()
    leads = conn.execute(
        "SELECT * FROM leads ORDER BY created_at DESC"
    ).fetchall()
    conn.close()

    return render_template("admin.html", leads=leads)


# ---------- MARK CONTACTED ----------
@app.route("/admin/mark/<int:lead_id>")
def mark_contacted(lead_id):
    if not session.get("admin_logged_in"):
        return redirect("/admin/login")

    conn = get_db_connection()
    conn.execute(
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
    conn.execute(
        "DELETE FROM leads WHERE id=?",
        (lead_id,)
    )
    conn.commit()
    conn.close()

    return redirect("/admin")


# ---------- DIRECT CSV DOWNLOAD ----------
@app.route("/admin/download")
def download_leads():
    if not session.get("admin_logged_in"):
        return redirect("/admin/login")

    conn = get_db_connection()
    rows = conn.execute(
        "SELECT * FROM leads ORDER BY created_at DESC"
    ).fetchall()
    conn.close()

    if not rows:
        return "No data available"

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Name", "Phone", "Message", "Status", "Created At"])

    for r in rows:
        writer.writerow([
            r["id"],
            r["name"],
            r["phone"],
            r["message"],
            r["status"],
            r["created_at"]
        ])

    memory_file = io.BytesIO()
    memory_file.write(output.getvalue().encode())
    memory_file.seek(0)

    filename = f"leads_backup_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.csv"

    return send_file(
        memory_file,
        as_attachment=True,
        download_name=filename,
        mimetype="text/csv"
    )


# ---------- SENDGRID BACKUP ----------
def send_db_backup_email():
    try:
        conn = get_db_connection()
        rows = conn.execute(
            "SELECT * FROM leads ORDER BY created_at DESC"
        ).fetchall()
        conn.close()

        if not rows:
            print("No leads found. Backup skipped.")
            return

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Name", "Phone", "Message", "Status", "Created At"])

        for r in rows:
            writer.writerow([
                r["id"],
                r["name"],
                r["phone"],
                r["message"],
                r["status"],
                r["created_at"]
            ])

        encoded_csv = base64.b64encode(
            output.getvalue().encode()
        ).decode()

        payload = {
            "personalizations": [{
                "to": [{"email": EMAIL_TO}],
                "subject": "AL-MEEZAN Leads Backup"
            }],
            "from": {"email": EMAIL_FROM},
            "content": [{
                "type": "text/plain",
                "value": "Leads backup attached."
            }],
            "attachments": [{
                "content": encoded_csv,
                "type": "text/csv",
                "filename": "leads_backup.csv"
            }]
        }

        headers = {
            "Authorization": f"Bearer {SENDGRID_API_KEY}",
            "Content-Type": "application/json"
        }

        response = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            json=payload,
            headers=headers,
            timeout=15
        )

        print("SendGrid Status:", response.status_code)

        if response.status_code != 202:
            print("SendGrid Error:", response.text)

    except Exception as e:
        print("Backup Error:", str(e))


# ---------- BACKUP ROUTE ----------
@app.route("/admin/backup")
def admin_backup():
    if request.args.get("key") != BACKUP_KEY:
        return "Unauthorized", 403

    threading.Thread(
        target=send_db_backup_email,
        daemon=True
    ).start()

    return "Backup triggered"


# ---------- LOGOUT ----------
@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect("/admin/login")


# ---------- RUN ----------
if __name__ == "__main__":
    app.run()
