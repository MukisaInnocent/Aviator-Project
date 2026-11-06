from flask import Blueprint, current_app, request, jsonify, session
from sqlalchemy.exc import SQLAlchemyError

from app.models import Wallet, Deposit, Withdrawal, ActivityLog, db
from app.routes.auth import login_required
from app.utils import AMOUNT_ERROR, json_body, parse_amount

bp = Blueprint('wallet', __name__, url_prefix='/api/wallet')


@bp.route('/balance', methods=['GET'])
@login_required
def get_balance():
    user_id = session['user_id']
    wallet = Wallet.query.filter_by(user_id=user_id).first()
    if not wallet:
        return jsonify({'balance': 0.0}), 200
    return jsonify({'balance': float(wallet.balance)}), 200


@bp.route('/deposit', methods=['POST'])
@login_required
def request_deposit():
    user_id = session['user_id']
    data = json_body(request)
    if data is None:
        return jsonify({'error': 'A JSON request body is required'}), 400

    amount = parse_amount(data.get('amount'))
    if amount is None:
        return jsonify({'error': AMOUNT_ERROR}), 400

    try:
        deposit = Deposit(user_id=user_id, amount=amount, status='pending')
        db.session.add(deposit)

        log = ActivityLog(user_id=user_id, action_type='DEPOSIT_REQUEST', description=f'Requested deposit of {amount}', ip_address=request.remote_addr)
        db.session.add(log)

        db.session.commit()
        return jsonify({'message': 'Deposit request submitted successfully'}), 201
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception('Unable to create deposit request')
        return jsonify({'error': 'Unable to submit request right now'}), 500


@bp.route('/withdraw', methods=['POST'])
@login_required
def request_withdrawal():
    user_id = session['user_id']
    data = json_body(request)
    if data is None:
        return jsonify({'error': 'A JSON request body is required'}), 400

    amount = parse_amount(data.get('amount'))
    if amount is None:
        return jsonify({'error': AMOUNT_ERROR}), 400

    try:
        wallet = Wallet.query.filter_by(user_id=user_id).first()
        if not wallet or wallet.balance < amount:
            return jsonify({'error': 'Insufficient balance'}), 400

        # Create withdrawal request - Balance is NOT deducted yet per requirements;
        # the admin approval re-checks the balance under a row lock.
        withdrawal = Withdrawal(user_id=user_id, amount=amount, status='pending')
        db.session.add(withdrawal)

        log = ActivityLog(user_id=user_id, action_type='WITHDRAWAL_REQUEST', description=f'Requested withdrawal of {amount}', ip_address=request.remote_addr)
        db.session.add(log)

        db.session.commit()
        return jsonify({'message': 'Withdrawal request submitted successfully'}), 201
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception('Unable to create withdrawal request')
        return jsonify({'error': 'Unable to submit request right now'}), 500


@bp.route('/transactions', methods=['GET'])
@login_required
def get_transactions():
    user_id = session['user_id']

    deposits = Deposit.query.filter_by(user_id=user_id).order_by(Deposit.created_at.desc()).all()
    withdrawals = Withdrawal.query.filter_by(user_id=user_id).order_by(Withdrawal.created_at.desc()).all()

    d_list = [{'type': 'deposit', 'amount': float(d.amount), 'status': d.status, 'date': d.created_at.isoformat()} for d in deposits]
    w_list = [{'type': 'withdrawal', 'amount': float(w.amount), 'status': w.status, 'date': w.created_at.isoformat()} for w in withdrawals]

    transactions = sorted(d_list + w_list, key=lambda x: x['date'], reverse=True)

    return jsonify(transactions), 200
