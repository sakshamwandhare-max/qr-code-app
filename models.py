from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    credits = db.Column(db.Integer, default=500, nullable=False) # 500 Free Credits
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, default=datetime.utcnow)

    transactions = db.relationship('Transaction', backref='user', lazy=True)
    ledger_entries = db.relationship('CreditLedger', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Transaction(db.Model):
    __tablename__ = 'transactions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    order_id = db.Column(db.String(100), unique=True, nullable=False) # Razorpay Order ID
    payment_id = db.Column(db.String(100), unique=True, nullable=True) # Razorpay Payment ID
    package_name = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Integer, nullable=False) # in INR
    credits = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='CREATED', nullable=False) # CREATED, SUCCESS, FAILED
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CreditLedger(db.Model):
    __tablename__ = 'credit_ledger'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(db.Integer, nullable=False) # +250 or -1
    reason = db.Column(db.String(255), nullable=False) # "Welcome Bonus", "QR Generation", "Purchase"
    balance_after = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
