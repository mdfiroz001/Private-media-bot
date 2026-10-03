import os
import secrets
import sqlite3
import mimetypes
from pathlib import Path
from datetime import datetime, timezone

import requests
from flask import (
    Flask,
    request,
    jsonify,
    render_template_string,
    send_file,
    abort
)

# ============================================================
# APP CONFIG
# ============================================================

app = Flask(__name__)

PORT = int(os.getenv("PORT", "10000"))

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

UPLOAD_API_KEY = os.getenv(
    "UPLOAD_API_KEY",
    ""
).strip()

SITE_NAME = os.getenv(
    "SITE_NAME",
    "PRIVATE MEDIA"
)

CHANNEL_1_NAME = os.getenv(
    "CHANNEL_1_NAME",
    "📢 Join Channel 1"
)

CHANNEL_1_URL = os.getenv(
    "CHANNEL_1_URL",
    "https://t.me/"
)

CHANNEL_2_NAME = os.getenv(
    "CHANNEL_2_NAME",
    "📢 Join Channel 2"
)

CHANNEL_2_URL = os.getenv(
    "CHANNEL_2_URL",
    "https://t.me/"
)


# ============================================================
# STORAGE
# ============================================================

# /var/data permission সমস্যা এড়ানোর জন্য /tmp ব্যবহার করা হচ্ছে.
# Render restart/redeploy হলে /tmp-এর media মুছে যেতে পারে.

STORAGE_DIR = Path(
    os.getenv(
        "STORAGE_DIR",
        "/tmp/media"
    )
)

STORAGE_DIR.mkdir(
    parents=True,
    exist_ok=True
)


DATABASE_PATH = Path(
    os.getenv(
        "DATABASE_PATH",
        "/tmp/media.db"
    )
)

DATABASE_PATH.parent.mkdir(
    parents=True,
    exist_ok=True
)


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

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS media (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            token TEXT UNIQUE NOT NULL,

            telegram_file_id TEXT,

            filename TEXT,

            mime_type TEXT,

            media_type TEXT,

            file_path TEXT,

            file_size INTEGER DEFAULT 0,

            views INTEGER DEFAULT 0,

            status TEXT DEFAULT 'active',

            created_at TEXT NOT NULL

        )
        """
    )

    con.commit()

    con.close()


init_database()


# ============================================================
# HELPERS
# ============================================================

def make_token():

    return secrets.token_urlsafe(24)


def api_authorized():

    supplied_key = request.headers.get(
        "X-API-KEY",
        ""
    )

    if not UPLOAD_API_KEY:

        return False

    return secrets.compare_digest(
        supplied_key,
        UPLOAD_API_KEY
    )


def get_media(token):

    con = get_db()

    row = con.execute(
        """
        SELECT *
        FROM media
        WHERE token = ?
        AND status = 'active'
        """,
        (token,)
    ).fetchone()

    con.close()

    return row


def telegram_api(method):

    return (
        "https://api.telegram.org/"
        f"bot{BOT_TOKEN}/{method}"
    )


# ============================================================
# DOWNLOAD FROM TELEGRAM
# ============================================================

def download_from_telegram(
    file_id,
    destination
):

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN is not configured."
        )

    # --------------------------------------------------------
    # Get Telegram file path
    # --------------------------------------------------------

    response = requests.get(
        telegram_api("getFile"),
        params={
            "file_id": file_id
        },
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    if not data.get("ok"):

        raise RuntimeError(
            "Telegram getFile failed."
        )

    file_path = data["result"].get(
        "file_path"
    )

    if not file_path:

        raise RuntimeError(
            "Telegram did not return file_path."
        )

    # --------------------------------------------------------
    # Download URL
    # --------------------------------------------------------

    download_url = (
        "https://api.telegram.org/"
        f"file/bot{BOT_TOKEN}/"
        f"{file_path}"
    )

    # --------------------------------------------------------
    # Download file
    # --------------------------------------------------------

    with requests.get(
        download_url,
        stream=True,
        timeout=120
    ) as response:

        response.raise_for_status()

        with open(
            destination,
            "wb"
        ) as output:

            for chunk in response.iter_content(
                chunk_size=1024 * 1024
            ):

                if chunk:

                    output.write(chunk)

    return destination


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return jsonify({

        "ok": True,

        "service": SITE_NAME,

        "status": "online",

        "message":
            "Private Media Server is running."

    })


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    return jsonify({

        "ok": True,

        "status": "online"

    })


# ============================================================
# CREATE PRIVATE MEDIA
# ============================================================

@app.route(
    "/api/create",
    methods=["POST"]
)
def create_media():

    # --------------------------------------------------------
    # API authentication
    # --------------------------------------------------------

    if not api_authorized():

        return jsonify({

            "ok": False,

            "error":
                "Unauthorized"

        }), 401


    # --------------------------------------------------------
    # Read JSON
    # --------------------------------------------------------

    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify({

            "ok": False,

            "error":
                "JSON body required"

        }), 400


    # --------------------------------------------------------
    # Telegram file ID
    # --------------------------------------------------------

    file_id = str(

        data.get(
            "telegram_file_id",
            ""
        )

    ).strip()


    if not file_id:

        return jsonify({

            "ok": False,

            "error":
                "telegram_file_id is required"

        }), 400


    # --------------------------------------------------------
    # Media type
    # --------------------------------------------------------

    media_type = str(

        data.get(
            "media_type",
            "video"
        )

    ).lower().strip()


    if media_type not in (
        "video",
        "image"
    ):

        return jsonify({

            "ok": False,

            "error":
                "media_type must be video or image"

        }), 400


    # --------------------------------------------------------
    # Filename
    # --------------------------------------------------------

    filename = str(

        data.get(
            "filename",
            "media"
        )

    ).strip()


    # --------------------------------------------------------
    # MIME type
    # --------------------------------------------------------

    mime_type = str(

        data.get(
            "mime_type",
            ""
        )

    ).strip()


    # --------------------------------------------------------
    # Generate private token
    # --------------------------------------------------------

    token = make_token()


    # Prevent path traversal

    original_name = Path(
        filename
    ).name


    if not original_name:

        original_name = "media"


    # --------------------------------------------------------
    # File extension
    # --------------------------------------------------------

    extension = Path(
        original_name
    ).suffix


    if not extension:

        if media_type == "video":

            extension = ".mp4"

        else:

            extension = ".jpg"


    # --------------------------------------------------------
    # Local filename
    # --------------------------------------------------------

    local_filename = (
        token +
        extension
    )


    destination = (
        STORAGE_DIR /
        local_filename
    )


    # --------------------------------------------------------
    # Download from Telegram
    # --------------------------------------------------------

    try:

        download_from_telegram(
            file_id,
            destination
        )

    except Exception as error:

        try:

            destination.unlink(
                missing_ok=True
            )

        except Exception:

            pass


        return jsonify({

            "ok": False,

            "error":
                "Could not download file from Telegram.",

            "details":
                str(error)[:500]

        }), 500


    # --------------------------------------------------------
    # Detect MIME
    # --------------------------------------------------------

    if not mime_type:

        mime_type = (

            mimetypes.guess_type(
                original_name
            )[0]

            or

            (
                "video/mp4"
                if media_type == "video"
                else "image/jpeg"
            )

        )


    # --------------------------------------------------------
    # File size
    # --------------------------------------------------------

    file_size = destination.stat().st_size


    # --------------------------------------------------------
    # Save database
    # --------------------------------------------------------

    con = get_db()

    con.execute(
        """
        INSERT INTO media
        (
            token,
            telegram_file_id,
            filename,
            mime_type,
            media_type,
            file_path,
            file_size,
            created_at
        )

        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            token,
            file_id,
            original_name,
            mime_type,
            media_type,
            str(destination),
            file_size,
            datetime.now(
                timezone.utc
            ).isoformat()
        )
    )

    con.commit()

    con.close()


    # --------------------------------------------------------
    # Create viewer URL
    # --------------------------------------------------------

    base_url = request.host_url.rstrip("/")


    if media_type == "video":

        private_url = (
            f"{base_url}/v/{token}"
        )

    else:

        private_url = (
            f"{base_url}/i/{token}"
        )


    return jsonify({

        "ok": True,

        "token": token,

        "type": media_type,

        "filename": original_name,

        "size": file_size,

        "url": private_url

    })


# ============================================================
# VIEWER HTML
# ============================================================

VIEWER_HTML = """

<!DOCTYPE html>

<html lang="bn">

<head>

<meta charset="UTF-8">

<meta name="viewport"
content="width=device-width,
initial-scale=1,
maximum-scale=1">

<title>{{ site_name }}</title>

<meta name="robots"
content="noindex,nofollow,noarchive">

<style>

*{

    box-sizing:border-box;

    -webkit-tap-highlight-color:transparent;

}


html,
body{

    margin:0;

    padding:0;

    min-height:100%;

}


body{

    background:

    radial-gradient(
        circle at top,
        #292d6b 0%,
        #111429 38%,
        #05060b 100%
    );

    color:#fff;

    font-family:
        Arial,
        "Noto Sans Bengali",
        sans-serif;

}


.container{

    width:100%;

    max-width:720px;

    margin:auto;

    padding:15px;

}


.header{

    display:flex;

    align-items:center;

    padding:
        12px
        4px
        18px;

}


.brand{

    font-size:20px;

    font-weight:800;

}


.private{

    margin-top:4px;

    font-size:11px;

    color:#9fa6c2;

    letter-spacing:.7px;

}


.player-card{

    overflow:hidden;

    border-radius:20px;

    background:#000;

    border:
        1px solid
        rgba(255,255,255,.10);

    box-shadow:
        0 25px 70px
        rgba(0,0,0,.55);

}


video{

    display:block;

    width:100%;

    height:auto;

    max-height:75vh;

    background:#000;

}


.image{

    display:block;

    width:100%;

    max-height:80vh;

    object-fit:contain;

    background:#000;

}


.card{

    margin-top:16px;

    padding:18px;

    border-radius:19px;

    background:
        rgba(255,255,255,.065);

    border:
        1px solid
        rgba(255,255,255,.10);

    backdrop-filter:blur(15px);

}


.card-title{

    font-size:16px;

    font-weight:800;

    margin-bottom:12px;

}


.channel{

    display:block;

    text-align:center;

    text-decoration:none;

    color:#fff;

    font-weight:700;

    padding:15px;

    margin-top:10px;

    border-radius:14px;

    background:

        linear-gradient(
            135deg,
            #5266ff,
            #7548ff
        );

}


.rules{

    color:#c6cada;

    line-height:1.6;

}


.rules li{

    margin-bottom:8px;

}


.footer{

    text-align:center;

    color:#6e748e;

    font-size:12px;

    padding:
        22px
        0
        10px;

}

</style>

</head>


<body>


<div class="container">


<div class="header">

<div>

<div class="brand">

{{ site_name }}

</div>

<div class="private">

🔒 PRIVATE CONTENT

</div>

</div>

</div>


<!-- MEDIA -->

<div class="player-card">


{% if media_type == "video" %}

<video

    controls

    controlsList="nodownload"

    disablePictureInPicture

    playsinline

    preload="metadata"

    oncontextmenu="return false">

    <source

        src="/stream/{{ token }}"

        type="{{ mime_type }}">

    Your browser does not support video.

</video>


{% else %}


<img

    class="image"

    src="/stream/{{ token }}"

    alt="Private Image"

    oncontextmenu="return false">


{% endif %}


</div>


<!-- CHANNEL BUTTONS -->

<div class="card">


<div class="card-title">

📢 Join Our Channels

</div>


<a

    class="channel"

    href="{{ channel1_url }}"

    target="_blank"

    rel="noopener noreferrer">

    {{ channel1_name }}

</a>


<a

    class="channel"

    href="{{ channel2_url }}"

    target="_blank"

    rel="noopener noreferrer">

    {{ channel2_name }}

</a>


</div>


<!-- RULES -->

<div class="card rules">


<div class="card-title">

📜 Rules

</div>


<ul>

<li>
ভিডিও/ছবি download করে পুনরায় upload করা নিষিদ্ধ।
</li>

<li>
Private link অনুমতি ছাড়া share করা নিষিদ্ধ।
</li>

<li>
Content শুধুমাত্র online viewing-এর জন্য।
</li>

<li>
Unauthorized distribution নিষিদ্ধ।
</li>

</ul>


</div>


<div class="footer">

🔐 Private Media System

</div>


</div>


<script>

/* Disable right click */

document.addEventListener(
    "contextmenu",
    function(event){

        event.preventDefault();

    }
);


/* Disable common keyboard shortcuts */

document.addEventListener(
    "keydown",
    function(event){

        if(

            event.ctrlKey

            &&

            (
                event.key.toLowerCase()
                === "s"

                ||

                event.key.toLowerCase()
                === "u"
            )

        ){

            event.preventDefault();

        }


        if(event.key === "F12"){

            event.preventDefault();

        }

    }
);

</script>


</body>

</html>

"""


# ============================================================
# VIDEO VIEWER
# ============================================================

@app.route("/v/<token>")
def video_viewer(token):

    row = get_media(token)


    if not row:

        return render_template_string(

            """

            <html>

            <head>

            <meta name="viewport"
            content="width=device-width,initial-scale=1">

            <title>Not Found</title>

            </head>

            <body style="
            background:#080912;
            color:white;
            font-family:Arial;
            text-align:center;
            padding-top:80px;
            ">

            <h2>
            🔒 Private Video Not Found
            </h2>

            <p>
            This media link is invalid or expired.
            </p>

            </body>

            </html>

            """

        ), 404


    if row["media_type"] != "video":

        return (
            "Invalid media type",
            400
        )


    # Increase view count

    con = get_db()

    con.execute(

        """

        UPDATE media

        SET views = views + 1

        WHERE token = ?

        """,

        (token,)

    )

    con.commit()

    con.close()


    return render_template_string(

        VIEWER_HTML,

        site_name=SITE_NAME,

        media_type="video",

        token=token,

        mime_type=row["mime_type"],

        channel1_name=CHANNEL_1_NAME,

        channel1_url=CHANNEL_1_URL,

        channel2_name=CHANNEL_2_NAME,

        channel2_url=CHANNEL_2_URL

    )


# ============================================================
# IMAGE VIEWER
# ============================================================

@app.route("/i/<token>")
def image_viewer(token):

    row = get_media(token)


    if not row:

        return render_template_string(

            """

            <html>

            <head>

            <meta name="viewport"
            content="width=device-width,initial-scale=1">

            <title>Not Found</title>

            </head>

            <body style="
            background:#080912;
            color:white;
            font-family:Arial;
            text-align:center;
            padding-top:80px;
            ">

            <h2>
            🔒 Private Image Not Found
            </h2>

            <p>
            This media link is invalid or expired.
            </p>

            </body>

            </html>

            """

        ), 404


    if row["media_type"] != "image":

        return (
            "Invalid media type",
            400
        )


    # Increase view count

    con = get_db()

    con.execute(

        """

        UPDATE media

        SET views = views + 1

        WHERE token = ?

        """,

        (token,)

    )

    con.commit()

    con.close()


    return render_template_string(

        VIEWER_HTML,

        site_name=SITE_NAME,

        media_type="image",

        token=token,

        mime_type=row["mime_type"],

        channel1_name=CHANNEL_1_NAME,

        channel1_url=CHANNEL_1_URL,

        channel2_name=CHANNEL_2_NAME,

        channel2_url=CHANNEL_2_URL

    )


# ============================================================
# STREAM MEDIA
# ============================================================

@app.route("/stream/<token>")
def stream_media(token):

    row = get_media(token)


    if not row:

        abort(404)


    file_path = Path(
        row["file_path"]
    )


    if not file_path.exists():

        abort(404)


    response = send_file(

        file_path,

        mimetype=row["mime_type"],

        as_attachment=False,

        conditional=True

    )


    response.headers[
        "Content-Disposition"
    ] = "inline"


    response.headers[
        "X-Content-Type-Options"
    ] = "nosniff"


    response.headers[
        "Cache-Control"
    ] = "private, no-store"


    response.headers[
        "X-Frame-Options"
    ] = "SAMEORIGIN"


    response.headers[
        "Referrer-Policy"
    ] = "no-referrer"


    return response


# ============================================================
# ADMIN STATS
# ============================================================

@app.route("/api/stats")
def stats():

    if not api_authorized():

        return jsonify({

            "ok": False,

            "error":
                "Unauthorized"

        }), 401


    con = get_db()


    total = con.execute(

        "SELECT COUNT(*) FROM media"

    ).fetchone()[0]


    videos = con.execute(

        """

        SELECT COUNT(*)

        FROM media

        WHERE media_type='video'

        """

    ).fetchone()[0]


    images = con.execute(

        """

        SELECT COUNT(*)

        FROM media

        WHERE media_type='image'

        """

    ).fetchone()[0]


    views = con.execute(

        """

        SELECT COALESCE(
            SUM(views),
            0
        )

        FROM media

        """

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
# DELETE MEDIA
# ============================================================

@app.route(
    "/api/delete/<token>",
    methods=["POST"]
)
def delete_media(token):

    if not api_authorized():

        return jsonify({

            "ok": False,

            "error":
                "Unauthorized"

        }), 401


    con = get_db()


    row = con.execute(

        """

        SELECT *

        FROM media

        WHERE token = ?

        """,

        (token,)

    ).fetchone()


    if not row:

        con.close()

        return jsonify({

            "ok": False,

            "error":
                "Not found"

        }), 404


    con.execute(

        """

        UPDATE media

        SET status='deleted'

        WHERE token=?

        """,

        (token,)

    )


    con.commit()

    con.close()


    # Delete physical file

    try:

        Path(
            row["file_path"]
        ).unlink(
            missing_ok=True
        )

    except Exception:

        pass


    return jsonify({

        "ok": True,

        "message":
            "Media deleted successfully."

    })


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    app.run(

        host="0.0.0.0",

        port=PORT

    )
