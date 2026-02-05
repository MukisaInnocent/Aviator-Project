from flask import Blueprint, request, jsonify, session
from app.models import User, Wallet, ActivityLog, db
from werkzeug.security import generate_password_hash, check_password_hash
import functools

bp = Blueprint('auth', __name__, url_prefix='/api/auth')

def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return view(**kwargs)
    return wrapped_view

def admin_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        
        user = User.query.get(session['user_id'])
        if not user or user.role != 'admin':
            return jsonify({'error': 'Admin privileges required'}), 403
            
        return view(**kwargs)
    return wrapped_view

@bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    if not username or not email or not password:
        return jsonify({'error': 'Missing required fields'}), 400

    if User.query.filter((User.username == username) | (User.email == email)).first():
        return jsonify({'error': 'User already exists'}), 400

    try:
        # Create User
        hashed_password = generate_password_hash(password)
        new_user = User(username=username, email=email, password_hash=hashed_password)
        db.session.add(new_user)
        db.session.flush() # Flush to get user ID

        # Create Wallet
        new_wallet = Wallet(user_id=new_user.id)
        db.session.add(new_wallet)
        
        # Log Activity
        log = ActivityLog(user_id=new_user.id, action_type='REGISTER', description='User registered', ip_address=request.remote_addr)
        db.session.add(log)

        db.session.commit()
        return jsonify({'message': 'Registration successful'}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    user = User.query.filter_by(username=username).first()

    if user and check_password_hash(user.password_hash, password):
        if not user.is_active:
             return jsonify({'error': 'Account is disabled'}), 403

        session.clear()
        session['user_id'] = user.id
        session['role'] = user.role
        
        # Log login
        log = ActivityLog(user_id=user.id, action_type='LOGIN', description='User logged in', ip_address=request.remote_addr)
        db.session.add(log)
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
    user = User.query.get(session['user_id'])
    return jsonify({
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'role': user.role,
        'balance': float(user.wallet.balance) if user.wallet else 0.0
    }), 200
