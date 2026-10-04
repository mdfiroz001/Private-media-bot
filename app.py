import os
import sqlite3
import secrets
import json          # <-- এই লাইনটি নতুন যোগ করা হয়েছে
from datetime import datetime, timezone
from flask import Flask, request, jsonify


# ============================================================
# APP
# ============================================================

app = Flask(__name__)

PORT = int(os.getenv("PORT", "10000"))


# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================

BOT_TOKEN = os.getenv(
    "BOT_TOKEN",
    ""
).strip()


UPLOAD_API_KEY = os.getenv(
    "UPLOAD_API_KEY",
    ""
).strip()


ADMIN_ID = os.getenv(
    "ADMIN_ID",
    ""
).strip()


BOT_USERNAME = os.getenv(
    "BOT_USERNAME",
    "Private_Media_Uploader_Bot"
).strip()


SITE_NAME = os.getenv(
    "SITE_NAME",
    "PRIVATE MEDIA"
).strip()


CHANNEL_1_NAME = os.getenv(
    "CHANNEL_1_NAME",
    "📢 Channel 1"
).strip()


CHANNEL_1_URL = os.getenv(
    "CHANNEL_1_URL",
    "https://t.me/"
).strip()


CHANNEL_2_NAME = os.getenv(
    "CHANNEL_2_NAME",
    "📢 Channel 2"
).strip()


CHANNEL_2_URL = os.getenv(
    "CHANNEL_2_URL",
    "https://t.me/"
).strip()


ADMIN_USERNAME = os.getenv(
    "ADMIN_USERNAME",
    ""
).strip()


# ============================================================
# DATABASE
# ============================================================

DATABASE_PATH = os.getenv(
    "DATABASE_PATH",
    "/tmp/media.db"
)


def get_db():

    db = sqlite3.connect(
        DATABASE_PATH,
        timeout=30
    )

    db.row_factory = sqlite3.Row

    return db


# ============================================================
# DATABASE INIT
# ============================================================

def init_database():

    db = get_db()

    # --------------------------------------------------------
    # USERS
    # --------------------------------------------------------

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS users (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            telegram_id TEXT UNIQUE NOT NULL,

            username TEXT DEFAULT '',

            first_name TEXT DEFAULT '',

            last_name TEXT DEFAULT '',

            created_at TEXT NOT NULL,

            last_seen TEXT NOT NULL

        )
        """
    )


    # --------------------------------------------------------
    # MEDIA
    # --------------------------------------------------------

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS media (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            token TEXT UNIQUE NOT NULL,

            telegram_file_id TEXT NOT NULL,

            user_id TEXT NOT NULL,

            filename TEXT DEFAULT 'media',

            mime_type TEXT DEFAULT '',

            media_type TEXT DEFAULT 'file',

            file_size INTEGER DEFAULT 0,

            views INTEGER DEFAULT 0,

            status TEXT DEFAULT 'active',

            created_at TEXT NOT NULL

        )
        """
    )


    # --------------------------------------------------------
    # SETTINGS
    # --------------------------------------------------------

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (

            key TEXT PRIMARY KEY,

            value TEXT DEFAULT ''

        )
        """
    )


    # --------------------------------------------------------
    # DEFAULT SETTINGS
    # --------------------------------------------------------

    defaults = {

        "channel_1_name":
            CHANNEL_1_NAME,

        "channel_1_url":
            CHANNEL_1_URL,

        "channel_2_name":
            CHANNEL_2_NAME,

        "channel_2_url":
            CHANNEL_2_URL,

        "admin_username":
            ADMIN_USERNAME,

        "site_name":
            SITE_NAME

    }


    for key, value in defaults.items():

        db.execute(
            """
            INSERT OR IGNORE INTO settings
            (key, value)

            VALUES (?, ?)
            """,
            (key, value)
        )


    db.commit()

    db.close()


init_database()


# ============================================================
# HELPERS
# ============================================================

def now():

    return datetime.now(
        timezone.utc
    ).isoformat()


def make_token():

    return secrets.token_urlsafe(18)


def authorized():

    if not UPLOAD_API_KEY:

        return False

    key = request.headers.get(
        "X-API-KEY",
        ""
    ).strip()

    return secrets.compare_digest(
        key,
        UPLOAD_API_KEY
    )


def is_admin(user_id):

    return (
        str(user_id) ==
        str(ADMIN_ID)
    )


def get_setting(key, fallback=""):

    db = get_db()

    row = db.execute(
        """
        SELECT value

        FROM settings

        WHERE key = ?
        """,
        (key,)
    ).fetchone()

    db.close()

    if row:

        return row["value"]

    return fallback


def set_setting(key, value):

    db = get_db()

    db.execute(
        """
        INSERT INTO settings
        (key, value)

        VALUES (?, ?)

        ON CONFLICT(key)

        DO UPDATE SET
        value=excluded.value
        """,
        (key, value)
    )

    db.commit()

    db.close()


# ============================================================
# REGISTER / UPDATE USER
# ============================================================

@app.route(
    "/api/user",
    methods=["POST"]
)
def register_user():

    if not authorized():

        return jsonify({
            "ok": False,
            "error": "Unauthorized"
        }), 401


    data = request.get_json(
        silent=True
    ) or {}


    telegram_id = str(
        data.get(
            "telegram_id",
            ""
        )
    ).strip()


    if not telegram_id:

        return jsonify({
            "ok": False,
            "error": "telegram_id required"
        }), 400


    username = str(
        data.get(
            "username",
            ""
        )
    )


    first_name = str(
        data.get(
            "first_name",
            ""
        )
    )


    last_name = str(
        data.get(
            "last_name",
            ""
        )
    )


    db = get_db()


    db.execute(
        """
        INSERT INTO users
        (
            telegram_id,
            username,
            first_name,
            last_name,
            created_at,
            last_seen
        )

        VALUES (?, ?, ?, ?, ?, ?)

        ON CONFLICT(telegram_id)

        DO UPDATE SET

            username=excluded.username,

            first_name=excluded.first_name,

            last_name=excluded.last_name,

            last_seen=excluded.last_seen
        """,
        (
            telegram_id,
            username,
            first_name,
            last_name,
            now(),
            now()
        )
    )


    db.commit()

    db.close()


    return jsonify({
        "ok": True
    })


# ============================================================
# CREATE MEDIA
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
    ) or {}


    file_id = str(
        data.get(
            "telegram_file_id",
            ""
        )
    ).strip()


    user_id = str(
        data.get(
            "user_id",
            ""
        )
    ).strip()


    if not file_id:

        return jsonify({
            "ok": False,
            "error":
                "telegram_file_id required"
        }), 400


    if not user_id:

        return jsonify({
            "ok": False,
            "error":
                "user_id required"
        }), 400


    media_type = str(
        data.get(
            "media_type",
            "file"
        )
    ).lower().strip()


    allowed_types = [
        "video",
        "image",
        "file"
    ]


    if media_type not in allowed_types:

        media_type = "file"


    filename = str(
        data.get(
            "filename",
            "media"
        )
    ).strip()


    if not filename:

        filename = "media"


    mime_type = str(
        data.get(
            "mime_type",
            ""
        )
    ).strip()


    file_size = int(
        data.get(
            "file_size",
            0
        ) or 0
    )


    # --------------------------------------------------------
    # SAVE USER
    # --------------------------------------------------------

    db = get_db()


    db.execute(
        """
        INSERT INTO users
        (
            telegram_id,
            created_at,
            last_seen
        )

        VALUES (?, ?, ?)

        ON CONFLICT(telegram_id)

        DO UPDATE SET
        last_seen=excluded.last_seen
        """,
        (
            user_id,
            now(),
            now()
        )
    )


    # --------------------------------------------------------
    # CREATE TOKEN
    # --------------------------------------------------------

    token = make_token()


    # --------------------------------------------------------
    # SAVE MEDIA
    # --------------------------------------------------------

    db.execute(
        """
        INSERT INTO media
        (
            token,
            telegram_file_id,
            user_id,
            filename,
            mime_type,
            media_type,
            file_size,
            created_at
        )

        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            token,
            file_id,
            user_id,
            filename,
            mime_type,
            media_type,
            file_size,
            now()
        )
    )


    db.commit()

    db.close()


    # --------------------------------------------------------
    # TELEGRAM DEEP LINK
    # --------------------------------------------------------

    telegram_url = (
        "https://t.me/"
        + BOT_USERNAME
        + "?start="
        + token
    )


    return jsonify({

        "ok": True,

        "token": token,

        "telegram_file_id":
            file_id,

        "media_type":
            media_type,

        "filename":
            filename,

        "telegram_url":
            telegram_url,

        "url":
            telegram_url

    })


# ============================================================
# GET MEDIA
# ============================================================

@app.route(
    "/api/media/<token>"
)
def get_media(token):

    if not authorized():

        return jsonify({
            "ok": False,
            "error": "Unauthorized"
        }), 401


    db = get_db()


    row = db.execute(
        """
        SELECT *

        FROM media

        WHERE token = ?

        AND status = 'active'
        """,
        (token,)
    ).fetchone()


    db.close()


    if not row:

        return jsonify({
            "ok": False,
            "error":
                "Media not found"
        }), 404


    return jsonify({

        "ok": True,

        "id":
            row["id"],

        "token":
            row["token"],

        "telegram_file_id":
            row["telegram_file_id"],

        "user_id":
            row["user_id"],

        "filename":
            row["filename"],

        "mime_type":
            row["mime_type"],

        "media_type":
            row["media_type"],

        "views":
            row["views"]

    })


# ============================================================
# INCREASE VIEW
# ============================================================

@app.route(
    "/api/view/<token>",
    methods=["POST"]
)
def increase_view(token):

    if not authorized():

        return jsonify({
            "ok": False,
            "error": "Unauthorized"
        }), 401


    db = get_db()


    result = db.execute(
        """
        UPDATE media

        SET views = views + 1

        WHERE token = ?

        AND status = 'active'
        """,
        (token,)
    )


    db.commit()

    db.close()


    if result.rowcount == 0:

        return jsonify({
            "ok": False,
            "error":
                "Media not found"
        }), 404


    return jsonify({
        "ok": True
    })


# ============================================================
# MY MEDIA
# ============================================================

@app.route(
    "/api/my-media/<user_id>"
)
def my_media(user_id):

    if not authorized():

        return jsonify({
            "ok": False,
            "error": "Unauthorized"
        }), 401


    db = get_db()


    rows = db.execute(
        """
        SELECT *

        FROM media

        WHERE user_id = ?

        AND status = 'active'

        ORDER BY id DESC
        """,
        (str(user_id),)
    ).fetchall()


    db.close()


    items = []


    for row in rows:

        telegram_url = (
            "https://t.me/"
            + BOT_USERNAME
            + "?start="
            + row["token"]
        )


        items.append({

            "id":
                row["id"],

            "token":
                row["token"],

            "filename":
                row["filename"],

            "media_type":
                row["media_type"],

            "views":
                row["views"],

            "created_at":
                row["created_at"],

            "telegram_url":
                telegram_url

        })


    return jsonify({

        "ok": True,

        "count":
            len(items),

        "media":
            items

    })


# ============================================================
# ADMIN STATISTICS
# ============================================================

@app.route(
    "/api/admin/stats"
)
def admin_stats():

    if not authorized():

        return jsonify({
            "ok": False,
            "error": "Unauthorized"
        }), 401


    db = get_db()


    users = db.execute(
        """
        SELECT COUNT(*)
        FROM users
        """
    ).fetchone()[0]


    videos = db.execute(
        """
        SELECT COUNT(*)
        FROM media

        WHERE media_type='video'

        AND status='active'
        """
    ).fetchone()[0]


    images = db.execute(
        """
        SELECT COUNT(*)
        FROM media

        WHERE media_type='image'

        AND status='active'
        """
    ).fetchone()[0]


    files = db.execute(
        """
        SELECT COUNT(*)
        FROM media

        WHERE media_type='file'

        AND status='active'
        """
    ).fetchone()[0]


    links = db.execute(
        """
        SELECT COUNT(*)
        FROM media

        WHERE status='active'
        """
    ).fetchone()[0]


    views = db.execute(
        """
        SELECT COALESCE(
            SUM(views),
            0
        )

        FROM media

        WHERE status='active'
        """
    ).fetchone()[0]


    db.close()


    return jsonify({

        "ok": True,

        "users":
            users,

        "videos":
            videos,

        "images":
            images,

        "files":
            files,

        "links":
            links,

        "views":
            views

    })


# ============================================================
# ADMIN USERS
# ============================================================

@app.route(
    "/api/admin/users"
)
def admin_users():

    if not authorized():

        return jsonify({
            "ok": False,
            "error": "Unauthorized"
        }), 401


    db = get_db()


    rows = db.execute(
        """
        SELECT

            u.*,

            (
                SELECT COUNT(*)

                FROM media m

                WHERE m.user_id =
                u.telegram_id

                AND m.status='active'

            ) AS media_count

        FROM users u

        ORDER BY u.id DESC
        """
    ).fetchall()


    db.close()


    users = []


    for row in rows:

        users.append({

            "id":
                row["id"],

            "telegram_id":
                row["telegram_id"],

            "username":
                row["username"],

            "first_name":
                row["first_name"],

            "last_name":
                row["last_name"],

            "media_count":
                row["media_count"],

            "created_at":
                row["created_at"],

            "last_seen":
                row["last_seen"]

        })


    return jsonify({

        "ok": True,

        "count":
            len(users),

        "users":
            users

    })


# ============================================================
# ADMIN ALL MEDIA
# ============================================================

@app.route(
    "/api/admin/media"
)
def admin_media():

    if not authorized():

        return jsonify({
            "ok": False,
            "error": "Unauthorized"
        }), 401


    db = get_db()


    rows = db.execute(
        """
        SELECT *

        FROM media

        ORDER BY id DESC
        """
    ).fetchall()


    db.close()


    items = []


    for row in rows:

        telegram_url = (
            "https://t.me/"
            + BOT_USERNAME
            + "?start="
            + row["token"]
        )


        items.append({

            "id":
                row["id"],

            "token":
                row["token"],

            "user_id":
                row["user_id"],

            "filename":
                row["filename"],

            "media_type":
                row["media_type"],

            "views":
                row["views"],

            "status":
                row["status"],

            "created_at":
                row["created_at"],

            "telegram_url":
                telegram_url

        })


    return jsonify({

        "ok": True,

        "count":
            len(items),

        "media":
            items

    })


# ============================================================
# DELETE MEDIA
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


    db = get_db()


    row = db.execute(
        """
        SELECT *

        FROM media

        WHERE token = ?
        """,
        (token,)
    ).fetchone()


    if not row:

        db.close()

        return jsonify({
            "ok": False,
            "error":
                "Media not found"
        }), 404


    db.execute(
        """
        UPDATE media

        SET status='deleted'

        WHERE token=?
        """,
        (token,)
    )


    db.commit()

    db.close()


    return jsonify({

        "ok": True,

        "message":
            "Media link disabled."

    })


# ============================================================
# CHANNEL SETTINGS
# ============================================================

@app.route(
    "/api/settings"
)
def settings():

    if not authorized():

        return jsonify({
            "ok": False,
            "error": "Unauthorized"
        }), 401


    return jsonify({

        "ok": True,

        "channel_1_name":
            get_setting(
                "channel_1_name"
            ),

        "channel_1_url":
            get_setting(
                "channel_1_url"
            ),

        "channel_2_name":
            get_setting(
                "channel_2_name"
            ),

        "channel_2_url":
            get_setting(
                "channel_2_url"
            ),

        "admin_username":
            get_setting(
                "admin_username"
            ),

        "site_name":
            get_setting(
                "site_name"
            )

    })


# ============================================================
# UPDATE SETTINGS
# ============================================================

@app.route(
    "/api/settings",
    methods=["POST"]
)
def update_settings():

    if not authorized():

        return jsonify({
            "ok": False,
            "error": "Unauthorized"
        }), 401


    data = request.get_json(
        silent=True
    ) or {}


    allowed = [

        "channel_1_name",

        "channel_1_url",

        "channel_2_name",

        "channel_2_url",

        "admin_username",

        "site_name"

    ]


    for key in allowed:

        if key in data:

            set_setting(
                key,
                str(data[key])
            )


    return jsonify({
        "ok": True
    })


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return jsonify({

        "ok": True,

        "service":
            SITE_NAME,

        "status":
            "online",

        "bot":
            BOT_USERNAME

    })


# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():

    return jsonify({

        "ok": True,

        "status":
            "online"

    })


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    app.run(

        host="0.0.0.0",

        port=PORT

    )
