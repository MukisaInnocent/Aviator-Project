from flask import Blueprint, request, jsonify, session
from app.models import User, Wallet, Deposit, Withdrawal, ActivityLog, db
from app.routes.auth import admin_required
from decimal import Decimal

bp = Blueprint('admin', __name__, url_prefix='/api/admin')

@bp.route('/users', methods=['GET'])
@admin_required
def get_users():
    users = User.query.all()
    user_list = [{
        'id': u.id,
        'username': u.username,
        'email': u.email,
        'role': u.role,
        'is_active': u.is_active,
        'balance': float(u.wallet.balance) if u.wallet else 0.0,
        'created_at': u.created_at.isoformat()
    } for u in users]
    return jsonify(user_list), 200

@bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@admin_required
def toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.role == 'admin':
        return jsonify({'error': 'Cannot suspend admin'}), 400
    
    user.is_active = not user.is_active
    db.session.commit()
    return jsonify({'message': f'User {"activated" if user.is_active else "suspended"}'}), 200

@bp.route('/deposits', methods=['GET'])
@admin_required
def get_deposits():
    deposits = Deposit.query.order_by(Deposit.created_at.desc()).all()
    d_list = [{
        'id': d.id,
        'user_id': d.user_id,
        'username': d.user.username,
        'amount': float(d.amount),
        'status': d.status,
        'created_at': d.created_at.isoformat()
    } for d in deposits]
    return jsonify(d_list), 200

@bp.route('/deposits/<int:id>/process', methods=['POST'])
@admin_required
def process_deposit(id):
    data = request.get_json()
    action = data.get('action') # 'approve' or 'reject'
    
    if action not in ['approve', 'reject']:
        return jsonify({'error': 'Invalid action'}), 400

    try:
        deposit = Deposit.query.get_or_404(id)
        if deposit.status != 'pending':
            return jsonify({'error': 'Deposit already processed'}), 400

        if action == 'approve':
            deposit.status = 'approved'
            deposit.approved_by = session['user_id']
            # Update User Balance
            wallet = Wallet.query.filter_by(user_id=deposit.user_id).with_for_update().first()
            wallet.balance += deposit.amount
            
            log_desc = f'Deposit {id} approved. Amount: {deposit.amount}'
        else:
            deposit.status = 'rejected'
            deposit.approved_by = session['user_id']
            log_desc = f'Deposit {id} rejected. Amount: {deposit.amount}'

        log = ActivityLog(user_id=session['user_id'], action_type='DEPOSIT_PROCESS', description=log_desc, ip_address=request.remote_addr)
        db.session.add(log)
        db.session.commit()
        return jsonify({'message': f'Deposit {action}ed successfully'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/withdrawals', methods=['GET'])
@admin_required
def get_withdrawals():
    withdrawals = Withdrawal.query.order_by(Withdrawal.created_at.desc()).all()
    w_list = [{
        'id': w.id,
        'user_id': w.user_id,
        'username': w.user.username,
        'amount': float(w.amount),
        'status': w.status,
        'created_at': w.created_at.isoformat()
    } for w in withdrawals]
    return jsonify(w_list), 200

@bp.route('/withdrawals/<int:id>/process', methods=['POST'])
@admin_required
def process_withdrawal(id):
    data = request.get_json()
    action = data.get('action') # 'approve' or 'reject'

    if action not in ['approve', 'reject']:
        return jsonify({'error': 'Invalid action'}), 400

    try:
        withdrawal = Withdrawal.query.get_or_404(id)
        if withdrawal.status != 'pending':
             return jsonify({'error': 'Withdrawal already processed'}), 400

        if action == 'approve':
            # Check balance again!
            wallet = Wallet.query.filter_by(user_id=withdrawal.user_id).with_for_update().first()
            if wallet.balance < withdrawal.amount:
                 return jsonify({'error': 'User has insufficient balance for approval'}), 400 # Or reject automatically?
            
            wallet.balance -= withdrawal.amount
            withdrawal.status = 'approved'
            withdrawal.approved_by = session['user_id']
            log_desc = f'Withdrawal {id} approved. Amount: {withdrawal.amount}'
        else:
            withdrawal.status = 'rejected'
            withdrawal.approved_by = session['user_id']
            log_desc = f'Withdrawal {id} rejected. Amount: {withdrawal.amount}'

        log = ActivityLog(user_id=session['user_id'], action_type='WITHDRAWAL_PROCESS', description=log_desc, ip_address=request.remote_addr)
        db.session.add(log)
        db.session.commit()
        return jsonify({'message': f'Withdrawal {action}ed successfully'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
