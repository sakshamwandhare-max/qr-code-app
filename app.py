from flask import Flask, render_template, request, send_file, jsonify, abort, make_response
from PIL import Image, UnidentifiedImageError
from io import BytesIO
import base64
import os
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
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://pagead2.googlesyndication.com; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; "
        "connect-src 'self' https://pagead2.googlesyndication.com https://googleads.g.doubleclick.net; "
        "frame-src 'self' https://googleads.g.doubleclick.net https://tpc.googlesyndication.com https://www.google.com; "
        "font-src 'self' data:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    )
    return response


@app.after_request
def add_security_headers(response):
    return security_headers(response)


@app.template_filter("b64encode")
def b64encode_filter(data):
    return base64.b64encode(data).decode("utf-8")


@app.context_processor
def inject_site_config():
    return {"adsense_client_id": os.getenv("ADSENSE_CLIENT_ID", "").strip()}


@app.get("/")
def home():
    html = render_template("mobile_v3.html")
    phone_css = r'''
<style id="qrcraft-phone-layout">
/* QRCraft mobile-first override: touch phones always use the stacked layout. */
body.qrcraft-phone{font-size:16px}
body.qrcraft-phone .nav{padding:14px 15px}
body.qrcraft-phone .brand{font-size:16px}
body.qrcraft-phone .logo{width:36px;height:36px}
body.qrcraft-phone .hero{padding:30px 16px 22px}
body.qrcraft-phone .hero h1{font-size:40px;line-height:1.02;letter-spacing:-2px;margin:18px 0 14px}
body.qrcraft-phone .hero p{font-size:14px;line-height:1.65}
body.qrcraft-phone .workspace{width:100%;max-width:520px;padding:0 10px;margin:8px auto 28px}
body.qrcraft-phone .card{display:block!important;border-radius:20px}
body.qrcraft-phone .toolbar{padding:16px 14px 2px!important}
body.qrcraft-phone .toolbar-head h2{font-size:18px}
body.qrcraft-phone .small{font-size:11px}
body.qrcraft-phone .type-scroller{display:flex!important;flex-wrap:nowrap!important;overflow-x:auto!important;overflow-y:hidden!important;gap:9px;padding:3px 1px 15px;touch-action:pan-x;-webkit-overflow-scrolling:touch;scrollbar-width:none}
body.qrcraft-phone .type-scroller::-webkit-scrollbar{display:none}
body.qrcraft-phone .type{flex:0 0 82px!important;width:82px!important;min-width:82px!important;height:74px!important;font-size:11px!important;border-radius:14px}
body.qrcraft-phone .type b{font-size:21px}
body.qrcraft-phone .form-area{display:block!important;padding:0 14px 21px!important}
body.qrcraft-phone .field{margin-top:16px!important}
body.qrcraft-phone .field label{font-size:11px!important;margin-bottom:8px}
body.qrcraft-phone .input,body.qrcraft-phone .select{height:55px!important;font-size:16px!important;padding-left:14px;padding-right:14px}
body.qrcraft-phone .textarea{min-height:115px!important;font-size:16px!important;padding:14px}
body.qrcraft-phone .two{display:grid!important;grid-template-columns:1fr!important;gap:0!important}
body.qrcraft-phone .primary{height:56px!important;margin-top:20px;font-size:15px!important}
body.qrcraft-phone .preview-wrap{display:flex!important;flex-direction:column!important;grid-column:auto!important;grid-row:auto!important;border-top:1px solid rgba(255,255,255,.06)!important;border-left:0!important;min-height:0!important;padding:25px 14px 22px!important}
body.qrcraft-phone .preview-title{font-size:11px;margin-bottom:16px}
body.qrcraft-phone .empty{width:min(78vw,330px)!important;height:min(78vw,330px)!important;font-size:13px}
body.qrcraft-phone #qrCanvas{width:min(78vw,330px)!important;height:min(78vw,330px)!important}
body.qrcraft-phone .qr{padding:15px;border-radius:18px}
body.qrcraft-phone .actions{grid-template-columns:1fr 1fr!important;max-width:430px;gap:9px;margin-top:16px}
body.qrcraft-phone .secondary{height:48px;font-size:13px}
body.qrcraft-phone .info{max-width:520px;padding:0 10px;margin-bottom:30px}
body.qrcraft-phone .info-grid{grid-template-columns:1fr!important;gap:9px}
body.qrcraft-phone .info-box{padding:14px}
body.qrcraft-phone .info-box b{font-size:12px}.info-box span{font-size:10px}
body.qrcraft-phone .ad-wrap{max-width:520px;padding:0 10px}
body.qrcraft-phone footer{font-size:11px;padding-bottom:34px}
</style>'''
    phone_js = r'''<script id="qrcraft-phone-detect">
(function(){
  var touchDevice = navigator.maxTouchPoints > 0 || /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
  if(touchDevice && window.innerWidth <= 1100){document.body.classList.add('qrcraft-phone');}
  window.addEventListener('resize',function(){
    if(touchDevice && window.innerWidth <= 1100) document.body.classList.add('qrcraft-phone');
    else if(window.innerWidth > 1100) document.body.classList.remove('qrcraft-phone');
  });
})();
</script>'''
    html = html.replace("</head>", phone_css + "</head>")
    html = html.replace("<body>", "<body>")
    html = html.replace("</body>", phone_js + "</body>")
    return make_response(html)


@app.get("/terms")
def terms():
    return render_template("terms.html")


@app.get("/privacy")
def privacy():
    return render_template("privacy.html")


@app.get("/sw.js")
def service_worker():
    return send_file("static/sw.js", mimetype="application/javascript", max_age=0)


@app.get("/manifest.webmanifest")
def manifest():
    return send_file("static/manifest.webmanifest", mimetype="application/manifest+json")


@app.get("/robots.txt")
def robots():
    response = make_response("User-agent: *\nAllow: /\nAllow: /ads.txt\n", 200)
    response.headers["Content-Type"] = "text/plain; charset=utf-8"
    return response


@app.get("/ads.txt")
def ads_txt():
    publisher = os.getenv("ADSENSE_CLIENT_ID", "").strip().removeprefix("ca-")
    if not publisher.startswith("pub-"):
        return ("", 404)
    return (f"google.com, {publisher}, DIRECT, f08c47fec0942fa0\n", 200, {"Content-Type": "text/plain; charset=utf-8"})


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


@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error": "Upload is too large. Maximum size is 5 MB."}), 413


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
