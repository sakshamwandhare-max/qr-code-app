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

# Public publisher ID used by Google AdSense. This is not a secret.
ADSENSE_PUBLISHER_ID = "pub-1786563700495703"
ADSENSE_CLIENT_ID = "ca-pub-1786563700495703"


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
    # Keep AdSense enabled even if the hosting dashboard has no environment variable.
    # The publisher/client ID is public and is intended to appear in page source.
    return {"adsense_client_id": ADSENSE_CLIENT_ID}


@app.get("/")
def home():
    html = render_template("mobile_v3.html")
    phone_css = r'''
<style id="qrcraft-phone-layout">
/* Mobile-first: match the reference proportions without changing QRCraft's theme. */
body.qrcraft-phone{font-size:16px;overflow-x:hidden}
body.qrcraft-phone .nav{padding:14px 15px}
body.qrcraft-phone .brand{font-size:16px}
body.qrcraft-phone .logo{width:36px;height:36px}
body.qrcraft-phone .hero{padding:28px 16px 20px}
body.qrcraft-phone .hero h1{font-size:40px;line-height:1.04;letter-spacing:-2px;margin:16px 0 14px}
body.qrcraft-phone .hero p{font-size:14px;line-height:1.65}
body.qrcraft-phone .workspace{display:block!important;width:100%!important;max-width:520px!important;padding:0 10px!important;margin:8px auto 28px!important}
body.qrcraft-phone .card{display:block!important;width:100%!important;max-width:none!important;border-radius:20px!important;min-width:0!important}
body.qrcraft-phone .toolbar{padding:17px 14px 2px!important}
body.qrcraft-phone .toolbar-head h2{font-size:18px!important}
body.qrcraft-phone .small{font-size:11px!important}
body.qrcraft-phone .type-scroller{display:flex!important;flex-wrap:nowrap!important;overflow-x:auto!important;overflow-y:hidden!important;gap:9px!important;padding:4px 1px 15px!important;touch-action:pan-x;-webkit-overflow-scrolling:touch;scrollbar-width:none}
body.qrcraft-phone .type-scroller::-webkit-scrollbar{display:none}
body.qrcraft-phone .type{flex:0 0 82px!important;width:82px!important;min-width:82px!important;height:74px!important;font-size:11px!important;border-radius:14px!important}
body.qrcraft-phone .type b{font-size:21px!important}
body.qrcraft-phone .form-area{display:block!important;padding:0 14px 21px!important;width:100%!important}
body.qrcraft-phone .field{margin-top:16px!important;width:100%!important}
body.qrcraft-phone .field label{font-size:12px!important;margin-bottom:8px!important}
body.qrcraft-phone .input,body.qrcraft-phone .select{width:100%!important;height:55px!important;font-size:16px!important;padding-left:14px!important;padding-right:14px!important}
body.qrcraft-phone .textarea{width:100%!important;min-height:115px!important;font-size:16px!important;padding:14px!important}
body.qrcraft-phone .two{display:block!important;width:100%!important}
body.qrcraft-phone .two>*{width:100%!important;display:block!important}
body.qrcraft-phone .color-row{display:block!important}
body.qrcraft-phone .color-control{width:100%!important;margin-top:8px}
body.qrcraft-phone .primary{width:100%!important;height:56px!important;margin-top:20px!important;font-size:15px!important}
body.qrcraft-phone .preview-wrap{display:flex!important;flex-direction:column!important;width:100%!important;grid-column:auto!important;grid-row:auto!important;border-top:1px solid rgba(255,255,255,.06)!important;border-left:0!important;min-height:0!important;padding:25px 14px 22px!important}
body.qrcraft-phone .preview-title{font-size:12px!important;margin-bottom:16px!important}
body.qrcraft-phone .empty{width:min(78vw,330px)!important;height:min(78vw,330px)!important;font-size:13px!important}
body.qrcraft-phone #qrCanvas{width:min(78vw,330px)!important;height:min(78vw,330px)!important}
body.qrcraft-phone .qr{padding:15px!important;border-radius:18px!important;max-width:calc(100vw - 70px)!important}
body.qrcraft-phone .qr img{max-width:100%!important;height:auto!important}
body.qrcraft-phone .actions{display:grid!important;grid-template-columns:1fr 1fr!important;width:100%!important;max-width:430px!important;gap:9px!important;margin-top:16px!important}
body.qrcraft-phone .secondary{height:48px!important;font-size:13px!important}
body.qrcraft-phone .info{max-width:520px!important;padding:0 10px!important;margin-bottom:30px!important}
body.qrcraft-phone .info-grid{grid-template-columns:1fr!important;gap:9px!important}
body.qrcraft-phone .info-box{padding:14px!important}
body.qrcraft-phone .info-box b{font-size:12px!important}
body.qrcraft-phone .info-box span{font-size:11px!important;line-height:1.5!important}
body.qrcraft-phone .ad-wrap{max-width:520px!important;padding:0 10px!important}
body.qrcraft-phone footer{font-size:11px!important;padding:20px 14px 34px!important}
@media (max-width:759px){body.qrcraft-phone .workspace *,body.qrcraft-phone .workspace{max-width:100%}}
</style>'''
    phone_js = r'''<script id="qrcraft-phone-detect">
(function(){
  function apply(){
    var touchDevice = navigator.maxTouchPoints > 0 || /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
    document.body.classList.toggle('qrcraft-phone', touchDevice && window.innerWidth <= 1100);
  }
  apply();
  window.addEventListener('resize', apply, {passive:true});
})();
</script>'''
    # Add the ownership meta tag at response time so the actually served page
    # contains it even when an older template is still present.
    adsense_meta = '<meta name="google-adsense-account" content="ca-pub-1786563700495703">'
    html = html.replace("</head>", adsense_meta + phone_css + "</head>")
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
    response = make_response(
        "User-agent: *\nAllow: /\n\nUser-agent: Mediapartners-Google\nAllow: /\n\nUser-agent: Google-Display-Ads-Bot\nAllow: /\n\nSitemap: https://qr-code-app-ywvj.onrender.com/sitemap.xml\n",
        200,
    )
    response.headers["Content-Type"] = "text/plain; charset=utf-8"
    return response


@app.get("/ads.txt")
def ads_txt():
    # Keep this endpoint deliberately plain and public so Google's ads.txt
    # crawler can read it without cookies, JavaScript, or authentication.
    body = f"google.com, {ADSENSE_PUBLISHER_ID}, DIRECT, f08c47fec0942fa0\n"
    response = make_response(body, 200)
    response.headers["Content-Type"] = "text/plain; charset=utf-8"
    response.headers["Cache-Control"] = "public, max-age=300, must-revalidate"
    response.headers["X-Robots-Tag"] = "all"
    return response


@app.get("/sitemap.xml")
def sitemap():
    xml = '''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://qr-code-app-ywvj.onrender.com/</loc></url>
  <url><loc>https://qr-code-app-ywvj.onrender.com/terms</loc></url>
  <url><loc>https://qr-code-app-ywvj.onrender.com/privacy</loc></url>
</urlset>'''
    response = make_response(xml, 200)
    response.headers["Content-Type"] = "application/xml; charset=utf-8"
    return response


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
