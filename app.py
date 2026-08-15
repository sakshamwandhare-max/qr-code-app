import os
from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import razorpay

app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ.get('AUTH_SECRET', 'qrcraft-ultra-key-2026')
# SQLite database path fixed for Render
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'qrcraft.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID', 'rzp_test_TOv6hvuqa6llce')
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET', 'dummy_secret')

try:
    razor_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
except Exception:
    razor_client = None

PACKAGES = {
    'p100': {'price': 100, 'credits': 200, 'name': 'Starter Pack (₹100)'},
    'p200': {'price': 200, 'credits': 400, 'name': 'Pro Pack (₹200)'},
    'p1000': {'price': 1000, 'credits': 2000, 'name': 'Ultra Pack (₹1000)'}
}

QR_COST = 35

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    credits = db.Column(db.Integer, default=200)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    name = data.get('name', '').strip()
    password = data.get('password')

    if not email or not password or not name:
        return jsonify({'error': 'Sabhi details bharna zaroori hai.'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Yeh email pehle se registered hai.'}), 400

    hashed_pw = generate_password_hash(password)
    new_user = User(name=name, email=email, password_hash=hashed_pw, credits=200)
    db.session.add(new_user)
    db.session.commit()
    login_user(new_user)
    return jsonify({'success': True, 'name': new_user.name, 'credits': new_user.credits})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password')

    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({'error': 'Galat email ya password.'}), 401

    login_user(user)
    return jsonify({'success': True, 'name': user.name, 'credits': user.credits})

@app.route('/api/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return jsonify({'success': True})

@app.route('/api/user-status', methods=['GET'])
def user_status():
    if current_user.is_authenticated:
        return jsonify({'logged_in': True, 'name': current_user.name, 'credits': current_user.credits})
    return jsonify({'logged_in': False, 'credits': 0})

@app.route('/api/generate-qr', methods=['POST'])
@login_required
def generate_qr():
    user = User.query.get(current_user.id)
    if user.credits < QR_COST:
        return jsonify({'error': 'INSUFFICIENT_CREDITS', 'message': f'Kam se kam {QR_COST} credits chahiye.'}), 402

    data = request.get_json() or {}
    payload = data.get('payload')
    if not payload:
        return jsonify({'error': 'URL missing hai.'}), 400

    user.credits -= QR_COST
    db.session.commit()
    return jsonify({'success': True, 'remaining_credits': user.credits, 'payload': payload})

# Database creation before server start
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
