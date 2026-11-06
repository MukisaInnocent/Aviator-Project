import functools
import re

from flask import Blueprint, current_app, request, jsonify, session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import generate_password_hash, check_password_hash

from app.models import User, Wallet, ActivityLog, db
from app.utils import json_body

bp = Blueprint('auth', __name__, url_prefix='/api/auth')

USERNAME_RE = re.compile(r'^[A-Za-z0-9_.-]{3,50}$')
EMAIL_RE = re.compile(r'^[^@\s<>"\']+@[^@\s<>"\']+\.[^@\s<>"\']+$')
MIN_PASSWORD_LENGTH = 8


def current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    return db.session.get(User, user_id)


def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        user = current_user()
        if not user or not user.is_active:
            session.clear()
            return jsonify({'error': 'Authentication required'}), 401
        return view(**kwargs)
    return wrapped_view


def admin_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        user = current_user()
        if not user or not user.is_active:
            session.clear()
            return jsonify({'error': 'Authentication required'}), 401
        if user.role != 'admin':
            return jsonify({'error': 'Admin privileges required'}), 403
        return view(**kwargs)
    return wrapped_view


@bp.route('/register', methods=['POST'])
def register():
    data = json_body(request)
    if data is None:
        return jsonify({'error': 'A JSON request body is required'}), 400

    username = str(data.get('username') or '').strip()
    email = str(data.get('email') or '').strip().lower()
    password = str(data.get('password') or '')

    if not username or not email or not password:
        return jsonify({'error': 'Missing required fields'}), 400
    if not USERNAME_RE.match(username):
        return jsonify({'error': 'Username must be 3-50 characters: letters, numbers, _ . -'}), 400
    if len(email) > 120 or not EMAIL_RE.match(email):
        return jsonify({'error': 'Enter a valid email address'}), 400
    if len(password) < MIN_PASSWORD_LENGTH:
        return jsonify({'error': f'Password must be at least {MIN_PASSWORD_LENGTH} characters'}), 400

    if User.query.filter((User.username == username) | (User.email == email)).first():
        return jsonify({'error': 'User already exists'}), 400

    try:
        new_user = User(username=username, email=email, password_hash=generate_password_hash(password))
        db.session.add(new_user)
        db.session.flush()  # Flush to get user ID

        db.session.add(Wallet(user_id=new_user.id))
        db.session.add(ActivityLog(user_id=new_user.id, action_type='REGISTER', description='User registered', ip_address=request.remote_addr))

        db.session.commit()
        return jsonify({'message': 'Registration successful'}), 201
    except IntegrityError:
        db.session.rollback()
        return jsonify({'error': 'User already exists'}), 400
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception('Unable to register user')
        return jsonify({'error': 'Unable to register right now'}), 500


@bp.route('/login', methods=['POST'])
def login():
    data = json_body(request)
    if data is None:
        return jsonify({'error': 'A JSON request body is required'}), 400

    username = str(data.get('username') or '').strip()
    password = str(data.get('password') or '')

    user = User.query.filter_by(username=username).first() if username else None

    if user and check_password_hash(user.password_hash, password):
        if not user.is_active:
            return jsonify({'error': 'Account is disabled'}), 403

        session.clear()
        session['user_id'] = user.id
        session['role'] = user.role

        db.session.add(ActivityLog(user_id=user.id, action_type='LOGIN', description='User logged in', ip_address=request.remote_addr))
        db.session.commit()

        return jsonify({
            'message': 'Login successful',
            'user': {
                'id': user.id,
                'username': user.username,
                'role': user.role
            }
        }), 200

    return jsonify({'error': 'Invalid credentials'}), 401


@bp.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Logged out successfully'}), 200


@bp.route('/me', methods=['GET'])
@login_required
def me():
    user = current_user()
    return jsonify({
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'role': user.role,
        'balance': float(user.wallet.balance) if user.wallet else 0.0
    }), 200
