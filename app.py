import os
import sqlite3
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'super-secret-key-qrcraft-2026')

# Rate Limiter setup (Server Lag & Bot Protection)
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

# --- Search Console & Security Headers ---
@app.after_request
def apply_security_and_robots(response):
    response.headers['X-Robots-Tag'] = 'all'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    return response

@app.route('/robots.txt')
def robots():
    return "User-agent: *\nAllow: /", 200, {'Content-Type': 'text/plain'}

# --- Main Routes ---
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
        return jsonify({'status': 'error', 'message': 'Email already registered!'}), 400

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

# --- Detailed Legal Pages for AdSense & Razorpay Approval ---
@app.route('/privacy')
def privacy():
    return '''
    <div style="font-family:sans-serif; padding:40px; max-width:800px; margin:auto;">
        <h1>Privacy Policy</h1>
        <p>At QRCraft Pro Studio, accessible from our website, one of our main priorities is the privacy of our visitors. This Privacy Policy document contains types of information that is collected and recorded by QRCraft Pro Studio and how we use it.</p>
        <h3>Information We Collect</h3>
        <p>When you register for an Account, we may ask for your contact information, including items such as name and email address. Passwords are fully hashed and encrypted.</p>
        <h3>Google DoubleClick DART Cookie</h3>
        <p>Google is one of a third-party vendor on our site. It also uses cookies, known as DART cookies, to serve ads to our site visitors based upon their visit to our site and other sites on the internet.</p>
    </div>
    '''

@app.route('/terms')
def terms():
    return '''
    <div style="font-family:sans-serif; padding:40px; max-width:800px; margin:auto;">
        <h1>Terms and Conditions</h1>
        <p>Welcome to QRCraft Pro Studio!</p>
        <p>By accessing this website we assume you accept these terms and conditions. Do not continue to use QRCraft Pro Studio if you do not agree to take all of the terms and conditions stated on this page.</p>
        <h3>License</h3>
        <p>Unless otherwise stated, QRCraft Pro Studio owns the intellectual property rights for all material on QRCraft Pro Studio. You must not generate QR codes for illegal, fraudulent, or harmful activity.</p>
    </div>
    '''

@app.route('/refund')
def refund():
    return '''
    <div style="font-family:sans-serif; padding:40px; max-width:800px; margin:auto;">
        <h1>Cancellation & Refund Policy</h1>
        <p>Thank you for buying credits at QRCraft Pro Studio.</p>
        <p>Credits purchased via Razorpay are processed instantly and credited to your account profile. Due to the digital nature of instant utility credits, purchases are generally non-refundable once added to your account balance.</p>
        <p>If you experience any payment deduct errors without credit top-up, contact us at our support desk.</p>
    </div>
    '''

@app.route('/contact')
def contact():
    return '''
    <div style="font-family:sans-serif; padding:40px; max-width:800px; margin:auto;">
        <h1>Contact Us</h1>
        <p>If you have any questions about our website or services, feel free to reach out to us:</p>
        <p><strong>Email:</strong> support@qrcraftstudio.com</p>
        <p><strong>Response Time:</strong> Within 24-48 working hours.</p>
    </div>
    '''

if __name__ == '__main__':
    app.run(debug=True)
