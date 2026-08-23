import os
import sqlite3
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'super-secret-key-qrcraft')

# Rate Limiter setup (Server-Side Lag & Spam Protection)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# SQLite DB Setup
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            credits INTEGER DEFAULT 200
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- Security Headers & Search Console/Robots Route ---
@app.after_request
def apply_security_and_robots(response):
    response.headers['X-Robots-Tag'] = 'all'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    return response

@app.route('/robots.txt')
def robots():
    return "User-agent: *\nAllow: /", 200, {'Content-Type': 'text/plain'}

# --- Main App Routes ---
@app.route('/')
def home():
    if 'user' in session:
        return render_template('index.html', user=session['user'], credits=session.get('credits', 200))
    return render_template('index.html', user=None, credits=0)

@app.route('/signup', methods=['POST'])
@limiter.limit("5 per minute")
def signup():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({'status': 'error', 'message': 'Email and Password required'}), 400

    hashed_pw = generate_password_hash(password)
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (email, password, credits) VALUES (?, ?, ?)", (email, hashed_pw, 200))
        conn.commit()
        conn.close()
        
        session['user'] = email
        session['credits'] = 200
        return jsonify({'status': 'success', 'message': 'Account created successfully!'})
    except sqlite3.IntegrityError:
        return jsonify({'status': 'error', 'message': 'Email already exists!'}), 400

@app.route('/login', methods=['POST'])
@limiter.limit("10 per minute")
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT password, credits FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()
    conn.close()

    if user and check_password_hash(user[0], password):
        session['user'] = email
        session['credits'] = user[1]
        return jsonify({'status': 'success', 'message': 'Logged in successfully!'})
    
    return jsonify({'status': 'error', 'message': 'Invalid Email or Password'}), 401

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# --- Legal Pages Routes (Razorpay & AdSense Zero-Fine Compliance) ---
@app.route('/privacy')
def privacy():
    return "<h1>Privacy Policy</h1><p>We value your privacy. Your data is encrypted and never shared with third parties.</p>"

@app.route('/terms')
def terms():
    return "<h1>Terms & Conditions</h1><p>By using QRCraft, you agree not to generate illegal or harmful QR codes.</p>"

@app.route('/refund')
def refund():
    return "<h1>Refund & Cancellation Policy</h1><p>Purchased credits are added instantly and are non-refundable.</p>"

@app.route('/contact')
def contact():
    return "<h1>Contact Us</h1><p>Support Email: support@qrcraft.com</p>"

if __name__ == '__main__':
    app.run(debug=True)
