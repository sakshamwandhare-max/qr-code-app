import os
from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import razorpay

app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ.get('AUTH_SECRET', 'qrcraft-ultra-key-2026')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///qrcraft.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)

RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID', 'rzp_test_TOv6hvuqa6llce')
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET', 'secret_placeholder')

try:
    razor_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
except Exception:
    razor_client = None

# Custom Credit Rates
PACKAGES = {
    'p100': {'price': 100, 'credits': 200, 'name': 'Starter Pack (₹100)'},
    'p200': {'price': 200, 'credits': 400, 'name': 'Pro Pack (₹200)'},
    'p1000': {'price': 1000, 'credits': 2000, 'name': 'Ultra Pack (₹
