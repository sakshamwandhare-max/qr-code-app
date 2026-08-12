import os
import hmac
import hashlib
from flask import Flask, request, jsonify, render_template, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User, Transaction, CreditLedger
import razorpay

app = Flask(__name__)

# Environment Configuration
app.config['SECRET_KEY'] = os.environ.get('AUTH_SECRET', 'super-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///qrcraft.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Cookie Security
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = True  # Production mein True rakhein (HTTPS)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Razorpay Client Setup
RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID', 'rzp_test_xxxx')
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET', 'yyyyy_secret')
RAZORPAY_WEBHOOK_SECRET = os.environ.get('RAZORPAY_WEBHOOK_SECRET', 'webhook_secret')

razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# Package Definitions (HARDCODED SERVER-SIDE TO PREVENT TAMPERING)
PACKAGES = {
    'starter': {'credits': 100, 'price': 50, 'name': 'Starter Top-Up'},
    'popular': {'credits': 250, 'price': 100, 'name': 'Value Pack'},
    'pro': {'credits': 2500, 'price': 1000, 'name': 'Pro Volume'}
}

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# --- AUTHENTICATION ROUTES ---

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    name = data.get('name', '').strip()
    password = data.get('password')

    if not email or not password or not name:
        return jsonify({'error': 'All fields are required.'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email is already registered.'}), 400

    # Create User with 500 Welcome Credits
    new_user = User(name=name, email=email, credits=500)
    new_user.set_password(password)
    
    db.session.add(new_user)
    db.session.commit()

    # Create Initial Ledger Entry
    ledger = CreditLedger(
        user_id=new_user.id,
        amount=500,
        reason='+500 Welcome Bonus',
        balance_after=500
    )
    db.session.add(ledger)
    db.session.commit()

    login_user(new_user)
    return jsonify({'message': 'Registration successful', 'credits': new_user.credits})


@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    password = data.get('password')

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({'error': 'Invalid email or password.'}), 401

    login_user(user, remember=data.get('remember', False))
    return jsonify({'message': 'Login successful', 'credits': user.credits, 'name': user.name})


@app.route('/api/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return jsonify({'message': 'Logged out successfully'})


# --- SECURE QR GENERATION API ---

@app.route('/api/generate-qr', methods=['POST'])
@login_required
def generate_qr():
    # Atomic Lock & Credit Verification
    user = User.query.with_for_update().get(current_user.id)

    if user.credits < 1:
        return jsonify({'error': 'INSUFFICIENT_CREDITS', 'message': 'You need at least 1 credit to generate a QR code.'}), 402

    data = request.get_json()
    qr_data = data.get('data')

    if not qr_data:
        return jsonify({'error': 'Payload data is required.'}), 400

    # 1. Deduct Credit
    user.credits -= 1
    
    # 2. Add Ledger Entry
    ledger = CreditLedger(
        user_id=user.id,
        amount=-1,
        reason='QR Code Generation',
        balance_after=user.credits
    )
    
    db.session.add(ledger)
    db.session.commit()

    # 3. Here call your existing QR Image Generator function logic
    # qr_image_url = create_qr_code(qr_data, data.get('theme'))

    return jsonify({
        'success': True,
        'remaining_credits': user.credits,
        'message': 'QR code generated successfully!'
    })


# --- PAYMENT GATEWAY INTEGRATION ---

@app.route('/api/payment/create-order', methods=['POST'])
@login_required
def create_order():
    data = request.get_json()
    package_key = data.get('package_key')

    if package_key not in PACKAGES:
        return jsonify({'error': 'Invalid package selection.'}), 400

    pkg = PACKAGES[package_key]
    amount_in_paise = pkg['price'] * 100

    # Create Order on Razorpay
    order_data = {
        'amount': amount_in_paise,
        'currency': 'INR',
        'payment_capture': 1
    }
    
    try:
        razorpay_order = razorpay_client.order.create(data=order_data)
        
        # Save Transaction as CREATED
        txn = Transaction(
            user_id=current_user.id,
            order_id=razorpay_order['id'],
            package_name=pkg['name'],
            amount=pkg['price'],
            credits=pkg['credits'],
            status='CREATED'
        )
        db.session.add(txn)
        db.session.commit()

        return jsonify({
            'order_id': razorpay_order['id'],
            'key_id': RAZORPAY_KEY_ID,
            'amount': amount_in_paise,
            'currency': 'INR',
            'package_name': pkg['name']
        })

    except Exception as e:
        return jsonify({'error': 'Could not initiate payment. Try again.'}), 500


@app.route('/api/payment/verify', methods=['POST'])
@login_required
def verify_payment():
    data = request.get_json()
    
    razorpay_order_id = data.get('razorpay_order_id')
    razorpay_payment_id = data.get('razorpay_payment_id')
    razorpay_signature = data.get('razorpay_signature')

    # Signature Verification
    params_dict = {
        'razorpay_order_id': razorpay_order_id,
        'razorpay_payment_id': razorpay_payment_id,
        'razorpay_signature': razorpay_signature
    }

    try:
        razorpay_client.utility.verify_payment_signature(params_dict)
    except razorpay.errors.SignatureVerificationError:
        return jsonify({'error': 'Payment verification failed. Invalid signature.'}), 400

    # Idempotent Transaction Processing
    txn = Transaction.query.filter_by(order_id=razorpay_order_id).first()
    if not txn:
        return jsonify({'error': 'Transaction record not found.'}), 404

    if txn.status == 'SUCCESS':
        return jsonify({'message': 'Payment already processed.', 'credits': current_user.credits})

    # Update Transaction Status
    txn.payment_id = razorpay_payment_id
    txn.status = 'SUCCESS'

    # Add Credits to User Account
    user = User.query.with_for_update().get(txn.user_id)
    user.credits += txn.credits

    # Record Credit Ledger
    ledger = CreditLedger(
        user_id=user.id,
        amount=txn.credits,
        reason=f'Purchase: {txn.package_name}',
        balance_after=user.credits
    )

    db.session.add(ledger)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Payment verified and credits added!',
        'new_credits': user.credits
    })


# --- WEBHOOK HANDLER FOR AUTOMATIC BACKUP VERIFICATION ---

@app.route('/api/webhook/razorpay', methods=['POST'])
def razorpay_webhook():
    webhook_body = request.get_data(as_text=True)
    webhook_signature = request.headers.get('X-Razorpay-Signature')

    try:
        razorpay_client.utility.verify_webhook_signature(
            webhook_body, webhook_signature, RAZORPAY_WEBHOOK_SECRET
        )
    except razorpay.errors.SignatureVerificationError:
        return jsonify({'status': 'invalid signature'}), 400

    data = request.get_json()
    event = data.get('event')

    if event == 'payment.captured':
        payment_entity = data['payload']['payment']['entity']
        order_id = payment_entity['order_id']
        payment_id = payment_entity['id']

        txn = Transaction.query.filter_by(order_id=order_id).first()
        if txn and txn.status != 'SUCCESS':
            txn.status = 'SUCCESS'
            txn.payment_id = payment_id

            user = User.query.with_for_update().get(txn.user_id)
            user.credits += txn.credits

            ledger = CreditLedger(
                user_id=user.id,
                amount=txn.credits,
                reason=f'Webhook Capture: {txn.package_name}',
                balance_after=user.credits
            )
            db.session.add(ledger)
            db.session.commit()

    return jsonify({'status': 'ok'}), 200


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
