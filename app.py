import base64
import hmac
import io
import os
import re
import secrets
from datetime import datetime
from urllib.parse import urlparse

import qrcode
import razorpay
from flask import Flask, jsonify, render_template, request, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

from models import CreditLedger, Transaction, User, db

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

SECRET_KEY = os.environ.get("AUTH_SECRET")
if not SECRET_KEY or len(SECRET_KEY) < 32:
    raise RuntimeError("AUTH_SECRET must be set and at least 32 characters long")

app.config.update(
    SECRET_KEY=SECRET_KEY,
    SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL", "sqlite:///qrcraft.db").replace("postgres://", "postgresql://", 1),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "1") == "1",
    SESSION_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=64 * 1024,
)
db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = "index"
limiter = Limiter(key_func=get_remote_address, default_limits=["300 per hour", "30 per minute"], storage_uri=os.environ.get("RATELIMIT_STORAGE_URI", "memory://"))
limiter.init_app(app)

RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET")
razor_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)) if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET else None

PACKAGES = {
    "p100": {"price": 100, "credits": 200, "name": "Starter Pack"},
    "p200": {"price": 200, "credits": 400, "name": "Pro Pack"},
    "p1000": {"price": 1000, "credits": 2000, "name": "Ultra Pack"},
}
QR_COST = 35
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def csrf_ok():
    supplied = request.headers.get("X-CSRFToken", "")
    expected = session.get("csrf_token")
    return bool(supplied and expected and hmac.compare_digest(supplied, expected))


def require_csrf():
    if not csrf_ok():
        return jsonify({"error": "Security check failed. Refresh the page and try again."}), 403
    return None


def safe_url(value, max_len=2048):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > max_len:
        return False
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' https://checkout.razorpay.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; connect-src 'self' https://*.razorpay.com; frame-src https://*.razorpay.com; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self';"
    if request.is_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.before_request
def bootstrap_csrf():
    session.setdefault("csrf_token", secrets.token_urlsafe(32))


@app.route("/")
def index():
    return render_template("index.html", csrf_token=session["csrf_token"])


@app.route("/api/signup", methods=["POST"])
@limiter.limit("5 per minute")
def signup():
    guard = require_csrf()
    if guard:
        return guard
    data = request.get_json(silent=True) or {}
    name, email, password = str(data.get("name", "")).strip(), str(data.get("email", "")).strip().lower(), data.get("password", "")
    if not 2 <= len(name) <= 80 or not EMAIL_RE.fullmatch(email):
        return jsonify({"error": "Please enter valid account details."}), 400
    if not isinstance(password, str) or not 10 <= len(password) <= 128:
        return jsonify({"error": "Password must be 10–128 characters."}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "An account with this email already exists."}), 409
    user = User(name=name, email=email, password_hash=generate_password_hash(password), credits=500)
    db.session.add(user)
    db.session.flush()
    db.session.add(CreditLedger(user_id=user.id, amount=500, reason="Welcome Bonus", balance_after=500))
    db.session.commit()
    login_user(user, remember=False)
    return jsonify({"success": True, "name": user.name, "credits": user.credits})


@app.route("/api/login", methods=["POST"])
@limiter.limit("8 per minute")
def login():
    guard = require_csrf()
    if guard:
        return guard
    data = request.get_json(silent=True) or {}
    email, password = str(data.get("email", "")).strip().lower(), data.get("password", "")
    user = User.query.filter_by(email=email).first()
    if not user or not user.is_active or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid email or password."}), 401
    user.last_login = datetime.utcnow()
    db.session.commit()
    login_user(user, remember=False)
    return jsonify({"success": True, "name": user.name, "credits": user.credits})


@app.route("/api/logout", methods=["POST"])
@login_required
@limiter.limit("20 per minute")
def logout():
    guard = require_csrf()
    if guard:
        return guard
    logout_user()
    return jsonify({"success": True})


@app.route("/api/user-status")
def user_status():
    if current_user.is_authenticated:
        return jsonify({"logged_in": True, "name": current_user.name, "credits": current_user.credits})
    return jsonify({"logged_in": False, "credits": 0})


@app.route("/api/generate-qr", methods=["POST"])
@login_required
@limiter.limit("30 per minute")
def generate_qr():
    guard = require_csrf()
    if guard:
        return guard
    data = request.get_json(silent=True) or {}
    payload = str(data.get("payload", "")).strip()
    if not safe_url(payload):
        return jsonify({"error": "Only valid http:// or https:// URLs are allowed."}), 400
    user = db.session.get(User, current_user.id)
    if not user or not user.is_active:
        return jsonify({"error": "Account unavailable."}), 401
    if user.credits < QR_COST:
        return jsonify({"error": "INSUFFICIENT_CREDITS", "message": f"You need {QR_COST} credits."}), 402
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=12, border=4)
    qr.add_data(payload)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    qr_data = "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")
    user.credits -= QR_COST
    db.session.add(CreditLedger(user_id=user.id, amount=-QR_COST, reason="QR Generation", balance_after=user.credits))
    db.session.commit()
    return jsonify({"success": True, "remaining_credits": user.credits, "qr_data": qr_data})


@app.route("/api/create-order", methods=["POST"])
@login_required
@limiter.limit("5 per minute")
def create_order():
    guard = require_csrf()
    if guard:
        return guard
    if not razor_client:
        return jsonify({"error": "Payments are temporarily unavailable."}), 503
    data = request.get_json(silent=True) or {}
    pkg = PACKAGES.get(data.get("package_key"))
    if not pkg:
        return jsonify({"error": "Invalid package."}), 400
    try:
        order = razor_client.order.create({"amount": pkg["price"] * 100, "currency": "INR", "receipt": secrets.token_hex(12), "notes": {"package_key": data["package_key"], "user_id": str(current_user.id)}})
        db.session.add(Transaction(user_id=current_user.id, order_id=order["id"], package_name=pkg["name"], amount=pkg["price"], credits=pkg["credits"], status="CREATED"))
        db.session.commit()
        return jsonify({"order_id": order["id"], "key_id": RAZORPAY_KEY_ID, "amount": pkg["price"] * 100, "package_name": pkg["name"], "credits": pkg["credits"]})
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Could not create payment order."}), 502


@app.route("/api/verify-payment", methods=["POST"])
@login_required
@limiter.limit("10 per minute")
def verify_payment():
    guard = require_csrf()
    if guard:
        return guard
    if not razor_client:
        return jsonify({"error": "Payments are temporarily unavailable."}), 503
    data = request.get_json(silent=True) or {}
    order_id, payment_id, signature = str(data.get("razorpay_order_id", "")), str(data.get("razorpay_payment_id", "")), str(data.get("razorpay_signature", ""))
    if not order_id or not payment_id or not signature:
        return jsonify({"error": "Incomplete payment response."}), 400
    transaction = Transaction.query.filter_by(order_id=order_id, user_id=current_user.id).first()
    if not transaction:
        return jsonify({"error": "Payment order not found."}), 404
    if transaction.status == "SUCCESS":
        return jsonify({"success": True, "new_credits": current_user.credits})
    try:
        razor_client.utility.verify_payment_signature({"razorpay_order_id": order_id, "razorpay_payment_id": payment_id, "razorpay_signature": signature})
    except Exception:
        transaction.status = "FAILED"
        db.session.commit()
        return jsonify({"error": "Payment signature verification failed."}), 400
    transaction.payment_id = payment_id
    transaction.status = "SUCCESS"
    user = db.session.get(User, current_user.id)
    user.credits += transaction.credits
    db.session.add(CreditLedger(user_id=user.id, amount=transaction.credits, reason=f"Purchase: {transaction.package_name}", balance_after=user.credits))
    db.session.commit()
    return jsonify({"success": True, "new_credits": user.credits})


@app.route("/about")
def about():
    return render_template("info.html", title="About QRCraft", heading="QR codes made simple", body="QRCraft is a focused QR creation tool for generating clean, scannable QR codes from secure web URLs.")


@app.route("/guide")
def guide():
    return render_template("info.html", title="QR Code Guide", heading="How QR codes work", body="A QR code stores data in a machine-readable pattern. QRCraft converts a valid HTTPS or HTTP destination into a PNG QR image that you can download and share.")


@app.route("/privacy")
def privacy():
    return render_template("info.html", title="Privacy Policy", heading="Privacy Policy", body="QRCraft uses account information to provide authentication and credit balances. Payment processing is handled by Razorpay; QRCraft does not store card, UPI, or banking credentials.")


@app.route("/terms")
def terms():
    return render_template("info.html", title="Terms of Service", heading="Terms of Service", body="Use QRCraft only for lawful content and destinations. Credits are consumed when a QR image is successfully generated, and paid credits are added only after verified payment confirmation.")


@app.route("/contact")
def contact():
    return render_template("info.html", title="Contact QRCraft", heading="Contact", body="For support, account or payment questions, use the contact address published by the site owner. Never send passwords, OTPs, card numbers or payment PINs by email.")


with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=False)
