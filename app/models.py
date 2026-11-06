from . import db
from datetime import datetime, timezone
from sqlalchemy.types import Numeric


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(10), default='user')  # 'admin' or 'user'
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    # Relationships
    wallet = db.relationship('Wallet', backref='user', uselist=False, lazy=True)
    deposits = db.relationship('Deposit', foreign_keys='Deposit.user_id', backref='user', lazy=True)
    withdrawals = db.relationship('Withdrawal', foreign_keys='Withdrawal.user_id', backref='user', lazy=True)
    bets = db.relationship('Bet', backref='user', lazy=True)
    logs = db.relationship('ActivityLog', backref='user', lazy=True)

class Wallet(db.Model):
    __tablename__ = 'wallets'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    balance = db.Column(Numeric(10, 2), default=0.00, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

class Deposit(db.Model):
    __tablename__ = 'deposits'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(Numeric(10, 2), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    created_at = db.Column(db.DateTime, default=utcnow)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

class Withdrawal(db.Model):
    __tablename__ = 'withdrawals'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(Numeric(10, 2), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    created_at = db.Column(db.DateTime, default=utcnow)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

class Bet(db.Model):
    __tablename__ = 'bets'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(Numeric(10, 2), nullable=False)
    multiplier = db.Column(db.Float, nullable=False)
    result = db.Column(db.String(10), nullable=False)  # pending, win, loss
    payout = db.Column(Numeric(10, 2), default=0.00)
    created_at = db.Column(db.DateTime, default=utcnow)

class GameRound(db.Model):
    __tablename__ = 'game_rounds'
    id = db.Column(db.Integer, primary_key=True)
    crash_point = db.Column(db.Float, nullable=False)
    start_time = db.Column(db.DateTime, default=utcnow, nullable=False)
    status = db.Column(db.String(10), default='waiting', nullable=False)
    hash = db.Column(db.String(64), nullable=True)


class RoundBet(db.Model):
    __tablename__ = 'round_bets'
    __table_args__ = (
        db.UniqueConstraint('round_id', 'user_id', name='uq_round_bet_user'),
    )

    bet_id = db.Column(db.Integer, db.ForeignKey('bets.id'), primary_key=True)
    round_id = db.Column(db.Integer, db.ForeignKey('game_rounds.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)


class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action_type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)
