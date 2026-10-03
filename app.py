import os
import secrets
import sqlite3
from datetime import datetime, timezone

from flask import Flask, request, jsonify

app = Flask(__name__)

PORT = int(os.getenv("PORT", "10000"))

BOT_USERNAME = os.getenv(
    "BOT_USERNAME",
    "Private_Media_Uploader_Bot"
).strip().lstrip("@")

UPLOAD_API_KEY = os.getenv(
    "UPLOAD_API_KEY",
    ""
).strip()

DATABASE_PATH = os.getenv(
    "DATABASE_PATH",
    "/tmp/media.db"
).strip()


# ============================================================
# DATABASE
# ============================================================

def get_db():
    con = sqlite3.connect(
        DATABASE_PATH,
        timeout=30
    )

    con.row_factory = sqlite3.Row

    return con


def init_database():

    con = get_db()

    con.execute("""
        CREATE TABLE IF NOT EXISTS media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT UNIQUE NOT NULL,
            telegram_file_id TEXT NOT NULL,
            filename TEXT DEFAULT 'media',
            mime_type TEXT DEFAULT '',
            media_type TEXT NOT NULL,
            views INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            created_at TEXT NOT NULL
        )
    """)

    con.commit()
    con.close()


init_database()


# ============================================================
# HELPERS
# ============================================================

def make_token():

    return secrets.token_urlsafe(16)


def authorized():

    key = request.headers.get(
        "X-API-KEY",
        ""
    )

    if not UPLOAD_API_KEY:
        return False

    return secrets.compare_digest(
        key,
        UPLOAD_API_KEY
    )


def get_media(token):

    con = get_db()

    row = con.execute("""
        SELECT *
        FROM media
        WHERE token = ?
        AND status = 'active'
    """, (token,)).fetchone()

    con.close()

    return row


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return jsonify({
        "ok": True,
        "service": "PRIVATE MEDIA UPLOADER",
        "status": "online"
    })


# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():

    return jsonify({
        "ok": True,
        "status": "online"
    })


# ============================================================
# CREATE PRIVATE LINK
# ============================================================

@app.route(
    "/api/create",
    methods=["POST"]
)
def create_media():

    if not authorized():

        return jsonify({
            "ok": False,
            "error": "Unauthorized"
        }), 401


    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify({
            "ok": False,
            "error": "JSON body required"
        }), 400


    file_id = str(
        data.get(
            "telegram_file_id",
            ""
        )
    ).strip()


    if not file_id:

        return jsonify({
            "ok": False,
            "error": "telegram_file_id is required"
        }), 400


    media_type = str(
        data.get(
            "media_type",
            ""
        )
    ).lower().strip()


    if media_type not in (
        "video",
        "image"
    ):

        return jsonify({
            "ok": False,
            "error": "media_type must be video or image"
        }), 400


    filename = str(
        data.get(
            "filename",
            "media"
        )
    ).strip()


    mime_type = str(
        data.get(
            "mime_type",
            ""
        )
    ).strip()


    token = make_token()


    con = get_db()

    con.execute("""
        INSERT INTO media
        (
            token,
            telegram_file_id,
            filename,
            mime_type,
            media_type,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        token,
        file_id,
        filename,
        mime_type,
        media_type,
        datetime.now(
            timezone.utc
        ).isoformat()
    ))

    con.commit()
    con.close()


    telegram_url = (
        "https://t.me/"
        + BOT_USERNAME
        + "?start="
        + token
    )


    return jsonify({

        "ok": True,

        "token": token,

        "media_type": media_type,

        "filename": filename,

        "telegram_url": telegram_url

    })


# ============================================================
# GET MEDIA INFORMATION
# ============================================================

@app.route(
    "/api/media/<token>",
    methods=["GET"]
)
def media_info(token):

    if not authorized():

        return jsonify({
            "ok": False,
            "error": "Unauthorized"
        }), 401


    row = get_media(token)


    if not row:

        return jsonify({
            "ok": False,
            "error": "Media not found"
        }), 404


    con = get_db()

    con.execute("""
        UPDATE media
        SET views = views + 1
        WHERE token = ?
    """, (token,))

    con.commit()
    con.close()


    return jsonify({

        "ok": True,

        "token": row["token"],

        "telegram_file_id":
            row["telegram_file_id"],

        "filename":
            row["filename"],

        "mime_type":
            row["mime_type"],

        "media_type":
            row["media_type"],

        "views":
            row["views"] + 1

    })


# ============================================================
# STATISTICS
# ============================================================

@app.route(
    "/api/stats",
    methods=["GET"]
)
def stats():

    if not authorized():

        return jsonify({
            "ok": False,
            "error": "Unauthorized"
        }), 401


    con = get_db()


    total = con.execute(
        "SELECT COUNT(*) FROM media "
        "WHERE status='active'"
    ).fetchone()[0]


    videos = con.execute(
        "SELECT COUNT(*) FROM media "
        "WHERE status='active' "
        "AND media_type='video'"
    ).fetchone()[0]


    images = con.execute(
        "SELECT COUNT(*) FROM media "
        "WHERE status='active' "
        "AND media_type='image'"
    ).fetchone()[0]


    views = con.execute(
        "SELECT COALESCE(SUM(views),0) "
        "FROM media "
        "WHERE status='active'"
    ).fetchone()[0]


    con.close()


    return jsonify({

        "ok": True,

        "total": total,

        "videos": videos,

        "images": images,

        "views": views

    })


# ============================================================
# DELETE
# ============================================================

@app.route(
    "/api/delete/<token>",
    methods=["POST"]
)
def delete_media(token):

    if not authorized():

        return jsonify({
            "ok": False,
            "error": "Unauthorized"
        }), 401


    con = get_db()


    row = con.execute("""
        SELECT *
        FROM media
        WHERE token = ?
    """, (token,)).fetchone()


    if not row:

        con.close()

        return jsonify({
            "ok": False,
            "error": "Media not found"
        }), 404


    con.execute("""
        UPDATE media
        SET status='deleted'
        WHERE token=?
    """, (token,))


    con.commit()
    con.close()


    return jsonify({

        "ok": True,

        "message":
            "Private link disabled."

    })


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=PORT
    )
