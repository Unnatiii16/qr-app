import io
import re
import sqlite3
import qrcode
from flask import Flask, render_template, request, redirect, url_for, abort, send_file
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
DB = "businesses.db"


def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS businesses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                instagram TEXT,
                whatsapp TEXT,
                facebook TEXT,
                email TEXT,
                phone TEXT
            )
        """)


def make_slug(name):
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "business"
    slug, n = base, 2
    with get_db() as conn:
        while conn.execute("SELECT 1 FROM businesses WHERE slug = ?", (slug,)).fetchone():
            slug = f"{base}-{n}"
            n += 1
    return slug


@app.route("/", methods=["GET", "POST"])
def create():
    if request.method == "POST":
        name = request.form["name"].strip()
        instagram = request.form["instagram"].strip().lstrip("@")
        whatsapp = re.sub(r"\D", "", request.form["whatsapp"])
        facebook = request.form["facebook"].strip()
        email = request.form["email"].strip()
        phone = re.sub(r"[^\d+]", "", request.form["phone"])

        slug = make_slug(name)
        with get_db() as conn:
            conn.execute(
                "INSERT INTO businesses (slug, name, instagram, whatsapp, facebook, email, phone) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (slug, name, instagram, whatsapp, facebook, email, phone),
            )
        return redirect(url_for("done", slug=slug))
    return render_template("create.html")


@app.route("/b/<slug>")
def business_page(slug):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM businesses WHERE slug = ?", (slug,)).fetchone()
    if row is None:
        abort(404)

    links = []
    if row["instagram"]:
        links.append({"label": "Instagram", "url": f"https://instagram.com/{row['instagram']}"})
    if row["whatsapp"]:
        links.append({"label": "WhatsApp", "url": f"https://wa.me/{row['whatsapp']}"})
    if row["facebook"]:
        links.append({"label": "Facebook", "url": row["facebook"]})
    if row["email"]:
        links.append({"label": "Email", "url": f"mailto:{row['email']}"})
    if row["phone"]:
        links.append({"label": "Call", "url": f"tel:{row['phone']}"})

    return render_template("business.html", business={"name": row["name"], "links": links})


@app.route("/done/<slug>")
def done(slug):
    with get_db() as conn:
        row = conn.execute("SELECT name FROM businesses WHERE slug = ?", (slug,)).fetchone()
    if row is None:
        abort(404)
    page_url = url_for("business_page", slug=slug, _external=True)
    return render_template("done.html", name=row["name"], slug=slug, page_url=page_url)


@app.route("/qr/<slug>.png")
def qr_code(slug):
    page_url = url_for("business_page", slug=slug, _external=True)
    img = qrcode.make(page_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(
        buf,
        mimetype="image/png",
        as_attachment=bool(request.args.get("download")),
        download_name=f"{slug}-qr.png",
    )


init_db()

if __name__ == "__main__":
    app.run(debug=True)