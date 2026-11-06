from flask import Blueprint, current_app, request, jsonify, session
from sqlalchemy.exc import SQLAlchemyError

from app.models import User, Wallet, Deposit, Withdrawal, ActivityLog, db
from app.routes.auth import admin_required
from app.utils import json_body

bp = Blueprint('admin', __name__, url_prefix='/api/admin')

LOG_LIMIT = 200
PAST = {'approve': 'approved', 'reject': 'rejected'}


def _action_from_request():
    data = json_body(request) or {}
    action = data.get('action')
    return action if action in ('approve', 'reject') else None


@bp.route('/users', methods=['GET'])
@admin_required
def get_users():
    users = User.query.order_by(User.id).all()
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
    user = db.get_or_404(User, user_id)
    if user.role == 'admin':
        return jsonify({'error': 'Cannot suspend admin'}), 400

    user.is_active = not user.is_active
    state = 'activated' if user.is_active else 'suspended'
    db.session.add(ActivityLog(
        user_id=session['user_id'],
        action_type='USER_TOGGLE',
        description=f'User {user.id} {state}',
        ip_address=request.remote_addr,
    ))
    db.session.commit()
    return jsonify({'message': f'User {state}'}), 200


@bp.route('/logs', methods=['GET'])
@admin_required
def get_logs():
    logs = (
        db.session.query(ActivityLog, User.username)
        .outerjoin(User, User.id == ActivityLog.user_id)
        .order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
        .limit(LOG_LIMIT)
        .all()
    )
    return jsonify([{
        'id': log.id,
        'date': log.created_at.isoformat() if log.created_at else None,
        'username': username or '-',
        'type': log.action_type,
        'description': log.description or '',
        'ip': log.ip_address or '',
    } for log, username in logs]), 200


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
    action = _action_from_request()
    if not action:
        return jsonify({'error': 'Invalid action'}), 400

    try:
        deposit = Deposit.query.filter_by(id=id).with_for_update().first()
        if not deposit:
            return jsonify({'error': 'Deposit not found'}), 404
        if deposit.status != 'pending':
            return jsonify({'error': 'Deposit already processed'}), 400

        if action == 'approve':
            wallet = Wallet.query.filter_by(user_id=deposit.user_id).with_for_update().first()
            if not wallet:
                wallet = Wallet(user_id=deposit.user_id, balance=0)
                db.session.add(wallet)
            wallet.balance += deposit.amount
            deposit.status = 'approved'
            log_desc = f'Deposit {id} approved. Amount: {deposit.amount}'
        else:
            deposit.status = 'rejected'
            log_desc = f'Deposit {id} rejected. Amount: {deposit.amount}'
        deposit.approved_by = session['user_id']

        db.session.add(ActivityLog(user_id=session['user_id'], action_type='DEPOSIT_PROCESS', description=log_desc, ip_address=request.remote_addr))
        db.session.commit()
        return jsonify({'message': f'Deposit {PAST[action]} successfully'}), 200
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception('Unable to process deposit %s', id)
        return jsonify({'error': 'Unable to process deposit right now'}), 500


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
    action = _action_from_request()
    if not action:
        return jsonify({'error': 'Invalid action'}), 400

    try:
        withdrawal = Withdrawal.query.filter_by(id=id).with_for_update().first()
        if not withdrawal:
            return jsonify({'error': 'Withdrawal not found'}), 404
        if withdrawal.status != 'pending':
            return jsonify({'error': 'Withdrawal already processed'}), 400

        if action == 'approve':
            # Check balance again under a row lock.
            wallet = Wallet.query.filter_by(user_id=withdrawal.user_id).with_for_update().first()
            if not wallet or wallet.balance < withdrawal.amount:
                db.session.rollback()
                return jsonify({'error': 'User has insufficient balance for approval'}), 400

            wallet.balance -= withdrawal.amount
            withdrawal.status = 'approved'
            log_desc = f'Withdrawal {id} approved. Amount: {withdrawal.amount}'
        else:
            withdrawal.status = 'rejected'
            log_desc = f'Withdrawal {id} rejected. Amount: {withdrawal.amount}'
        withdrawal.approved_by = session['user_id']

        db.session.add(ActivityLog(user_id=session['user_id'], action_type='WITHDRAWAL_PROCESS', description=log_desc, ip_address=request.remote_addr))
        db.session.commit()
        return jsonify({'message': f'Withdrawal {PAST[action]} successfully'}), 200
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception('Unable to process withdrawal %s', id)
        return jsonify({'error': 'Unable to process withdrawal right now'}), 500
