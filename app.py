from flask import Flask, render_template, request, send_file, jsonify, abort, make_response, render_template_string
from PIL import Image, UnidentifiedImageError
from io import BytesIO
import base64
import secrets
import time

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

PHOTO_TTL = 2 * 60 * 60
MAX_PHOTOS = 100
photos = {}
upload_log = {}


def cleanup_photos():
    now = time.time()
    expired = [token for token, item in photos.items() if item["expires"] <= now]
    for token in expired:
        photos.pop(token, None)
    if len(photos) > MAX_PHOTOS:
        oldest = sorted(photos.items(), key=lambda pair: pair[1]["created"])[:len(photos) - MAX_PHOTOS]
        for token, _ in oldest:
            photos.pop(token, None)


def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
        "connect-src 'self'; font-src 'self'; object-src 'none'; "
        "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    )
    return response


@app.after_request
def add_security_headers(response):
    return security_headers(response)


@app.template_filter("b64encode")
def b64encode_filter(data):
    return base64.b64encode(data).decode("utf-8")


@app.get("/")
def home():
    return render_template("mobile.html")


@app.get("/terms")
def terms():
    return render_template("terms.html")


@app.get("/privacy")
def privacy():
    return render_template("privacy.html")


@app.post("/api/photo")
def upload_photo():
    cleanup_photos()
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
    now = time.time()
    recent = [stamp for stamp in upload_log.get(ip, []) if stamp > now - 3600]
    if len(recent) >= 20:
        return jsonify({"error": "Too many uploads. Please try again later."}), 429
    recent.append(now)
    upload_log[ip] = recent

    uploaded = request.files.get("photo")
    if not uploaded or not uploaded.filename:
        return jsonify({"error": "Please choose an image."}), 400
    raw = uploaded.read()
    if not raw:
        return jsonify({"error": "The image is empty."}), 400

    try:
        image = Image.open(BytesIO(raw))
        image.verify()
        image = Image.open(BytesIO(raw))
        image.load()
    except (UnidentifiedImageError, OSError, ValueError):
        return jsonify({"error": "Please upload a valid image."}), 400

    if image.width > 4096 or image.height > 4096:
        return jsonify({"error": "Image dimensions are too large. Maximum is 4096×4096."}), 400

    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    photo_bytes = output.getvalue()

    token = secrets.token_urlsafe(18)
    photos[token] = {"data": photo_bytes, "created": now, "expires": now + PHOTO_TTL}
    return jsonify({"url": request.host_url.rstrip("/") + "/photo/" + token, "expires_in": PHOTO_TTL})


@app.get("/photo/<token>")
def serve_photo(token):
    cleanup_photos()
    item = photos.get(token)
    if not item or item["expires"] <= time.time():
        abort(404)
    response = make_response(send_file(BytesIO(item["data"]), mimetype="image/png"))
    response.headers["Cache-Control"] = "public, max-age=3600"
    response.headers["Content-Disposition"] = "inline"
    return response


@app.get("/manifest.webmanifest")
def manifest():
    return send_file("static/manifest.webmanifest", mimetype="application/manifest+json")


@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error": "Upload is too large. Maximum size is 5 MB."}), 413


@app.get("/download")
def download():
    return ("Use the Download button after generating a QR code.", 404)


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
