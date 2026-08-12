import os
from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import razorpay

app = Flask(__name__)

# Secret Keys & Database Configuration
app.config['SECRET_KEY'] = os.environ.get('AUTH_SECRET', 'my-secret-key-1234')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///qrcraft.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)

# Razorpay Keys (Render Environment Variables se aayenge)
RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID', 'rzp_test_placeholder')
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET', 'secret_placeholder')

try:
    client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
except:
    client = None

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    credits = db.Column(db.Integer, default=500) # 500 Free Credits on Signup

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def home():
    return render_template('index.html')

# Authentication APIs
@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.get_json()
    if User.query.filter_by(email=data['email']).first():
        return jsonify({'error': 'Email pehle se registered hai!'}), 400
    
    hashed_pw = generate_password_hash(data['password'])
    new_user = User(name=data['name'], email=data['email'], password_hash=hashed_pw, credits=500)
    db.session.add(new_user)
    db.session.commit()
    login_user(new_user)
    return jsonify({'success': True, 'name': new_user.name, 'credits': new_user.credits})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    user = User.query.filter_by(email=data['email']).first()
    if user and check_password_hash(user.password_hash, data['password']):
        login_user(user)
        return jsonify({'success': True, 'name': user.name, 'credits': user.credits})
    return jsonify({'error': 'Galat email ya password!'}), 401

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

# Payment API (Razorpay Order Create)
@app.route('/api/create-order', methods=['POST'])
@login_required
def create_order():
    data = request.get_json()
    amount = data.get('amount') # Amount in INR (e.g., 50, 100, 1000)
    
    if not client:
        return jsonify({'error': 'Razorpay keys configure nahi hain!'}), 400
        
    order_data = {
        'amount': amount * 100, # Paise mein convert
        'currency': 'INR',
        'payment_capture': 1
    }
    order = client.order.create(data=order_data)
    return jsonify({'order_id': order['id'], 'key_id': RAZORPAY_KEY_ID, 'amount': order_data['amount']})

# Payment Verify API
@app.route('/api/verify-payment', methods=['POST'])
@login_required
def verify_payment():
    data = request.get_json()
    added_credits = data.get('credits')
    
    # User ke credits update karein
    current_user.credits += added_credits
    db.session.commit()
    
    return jsonify({'success': True, 'new_credits': current_user.credits})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
