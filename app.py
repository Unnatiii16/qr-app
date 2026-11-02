import io
import os
import re
import psycopg
import qrcode
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from flask import Flask, render_template, request, redirect, url_for, abort, send_file
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

load_dotenv()
DATABASE_URL = os.environ["DATABASE_URL"]


# key, label, group, kind, base url, placeholder
# kind: user = username added to base url, url = full link, wa = whatsapp number, email, tel
_RAW = [
    ("instagram", "Instagram", "Popular", "user", "https://instagram.com/", "username"),
    ("whatsapp", "WhatsApp", "Popular", "wa", "", "919876543210"),
    ("facebook", "Facebook", "Popular", "url", "", "facebook.com/mycafe"),
    ("email", "Email", "Popular", "email", "", "hello@mycafe.com"),
    ("phone", "Call", "Popular", "tel", "", "+919876543210"),
    ("website", "Website", "Popular", "url", "", "mycafe.com"),
    ("maps", "Google Maps", "Popular", "url", "", "paste your Google Maps link"),
    ("x", "X (Twitter)", "Social media", "user", "https://x.com/", "username"),
    ("linkedin", "LinkedIn", "Social media", "url", "", "linkedin.com/company/mycafe"),
    ("youtube", "YouTube", "Social media", "url", "", "youtube.com/@mycafe"),
    ("telegram", "Telegram", "Social media", "user", "https://t.me/", "username"),
    ("snapchat", "Snapchat", "Social media", "user", "https://snapchat.com/add/", "username"),
    ("tiktok", "TikTok", "Social media", "user", "https://tiktok.com/@", "username"),
    ("threads", "Threads", "Social media", "user", "https://threads.com/@", "username"),
    ("pinterest", "Pinterest", "Social media", "user", "https://pinterest.com/", "username"),
    ("bluesky", "Bluesky", "Social media", "user", "https://bsky.app/profile/", "mycafe.bsky.social"),
    ("reddit", "Reddit", "Social media", "url", "", "reddit.com/r/mycafe"),
    ("discord", "Discord", "Social media", "url", "", "discord.gg/invitecode"),
    ("twitch", "Twitch", "Social media", "user", "https://twitch.tv/", "username"),
    ("tumblr", "Tumblr", "Social media", "url", "", "mycafe.tumblr.com"),
    ("quora", "Quora", "Social media", "url", "", "quora.com/profile/mycafe"),
    ("github", "GitHub", "Creative and work", "user", "https://github.com/", "username"),
    ("behance", "Behance", "Creative and work", "user", "https://behance.net/", "username"),
    ("dribbble", "Dribbble", "Creative and work", "user", "https://dribbble.com/", "username"),
    ("medium", "Medium", "Creative and work", "user", "https://medium.com/@", "username"),
    ("spotify", "Spotify", "Creative and work", "url", "", "open.spotify.com/..."),
    ("soundcloud", "SoundCloud", "Creative and work", "user", "https://soundcloud.com/", "username"),
    ("zomato", "Zomato", "Food and reviews", "url", "", "zomato.com/..."),
    ("swiggy", "Swiggy", "Food and reviews", "url", "", "swiggy.com/..."),
    ("justdial", "Justdial", "Food and reviews", "url", "", "justdial.com/..."),
    ("reviews", "Google Reviews", "Food and reviews", "url", "", "paste your Google review link"),
]
PLATFORMS = [
    dict(key=k, label=l, group=g, kind=kd, base=b, ph=ph) for k, l, g, kd, b, ph in _RAW
]
GROUPS = {}
for _p in PLATFORMS:
    GROUPS.setdefault(_p["group"], []).append(_p)


def build_link(p, value):
    value = value.strip()
    if not value:
        return None
    kind = p["kind"]
    if kind == "email":
        return f"mailto:{value}"
    if kind == "tel":
        digits = re.sub(r"[^\d+]", "", value)
        return f"tel:{digits}" if len(re.sub(r"\D", "", digits)) >= 7 else None
    if kind == "wa":
        digits = re.sub(r"\D", "", value)
        if len(digits) == 10:
            digits = "91" + digits
        return f"https://wa.me/{digits}" if 11 <= len(digits) <= 15 else None
    if value.lower().startswith(("http://", "https://")):
        return value
    if kind == "user":
        return p["base"] + value.lstrip("@")
    return "https://" + value


def query(sql, params=(), fetch=None):
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        cur = conn.execute(sql, params)
        if fetch == "one":
            return cur.fetchone()
        if fetch == "all":
            return cur.fetchall()


def init_db():
    query("""
        CREATE TABLE IF NOT EXISTS businesses (
            id SERIAL PRIMARY KEY,
            slug TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL
        )
    """)
    query("ALTER TABLE businesses ADD COLUMN IF NOT EXISTS links JSONB NOT NULL DEFAULT '[]'::jsonb")


def make_slug(name):
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "business"
    slug, n = base, 2
    while query("SELECT 1 FROM businesses WHERE slug = %s", (slug,), "one"):
        slug = f"{base}-{n}"
        n += 1
    return slug


@app.route("/", methods=["GET", "POST"])
def create():
    if request.method == "POST":
        name = request.form["name"].strip()
        links = []
        for p in PLATFORMS:
            url = build_link(p, request.form.get(p["key"], ""))
            if url:
                links.append({"label": p["label"], "url": url})

        slug = make_slug(name)
        query(
            "INSERT INTO businesses (slug, name, links) VALUES (%s, %s, %s)",
            (slug, name, Jsonb(links)),
        )
        return redirect(url_for("done", slug=slug))
    return render_template("create.html", groups=GROUPS)


@app.route("/b/<slug>")
def business_page(slug):
    row = query("SELECT * FROM businesses WHERE slug = %s", (slug,), "one")
    if row is None:
        abort(404)
    return render_template(
        "business.html", business={"name": row["name"], "links": row["links"] or []}
    )


@app.route("/done/<slug>")
def done(slug):
    row = query("SELECT name FROM businesses WHERE slug = %s", (slug,), "one")
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