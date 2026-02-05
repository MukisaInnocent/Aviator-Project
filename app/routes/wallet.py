from flask import Blueprint, request, jsonify, session
from app.models import User, Wallet, Deposit, Withdrawal, ActivityLog, db
from app.routes.auth import login_required
from decimal import Decimal

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
    data = request.get_json()
    amount = data.get('amount')

    if not amount or amount <= 0:
        return jsonify({'error': 'Invalid amount'}), 400

    try:
        deposit = Deposit(user_id=user_id, amount=Decimal(str(amount)), status='pending')
        db.session.add(deposit)
        
        log = ActivityLog(user_id=user_id, action_type='DEPOSIT_REQUEST', description=f'Requested deposit of {amount}', ip_address=request.remote_addr)
        db.session.add(log)
        
        db.session.commit()
        return jsonify({'message': 'Deposit request submitted successfully'}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/withdraw', methods=['POST'])
@login_required
def request_withdrawal():
    user_id = session['user_id']
    data = request.get_json()
    amount = data.get('amount')

    if not amount or amount <= 0:
        return jsonify({'error': 'Invalid amount'}), 400
    
    amount_decimal = Decimal(str(amount))

    try:
        wallet = Wallet.query.filter_by(user_id=user_id).first()
        if not wallet or wallet.balance < amount_decimal:
            return jsonify({'error': 'Insufficient balance'}), 400

        # Create withdrawal request - Balance is NOT deducted yet per requirements
        withdrawal = Withdrawal(user_id=user_id, amount=amount_decimal, status='pending')
        db.session.add(withdrawal)
        
        log = ActivityLog(user_id=user_id, action_type='WITHDRAWAL_REQUEST', description=f'Requested withdrawal of {amount}', ip_address=request.remote_addr)
        db.session.add(log)
        
        db.session.commit()
        return jsonify({'message': 'Withdrawal request submitted successfully'}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/transactions', methods=['GET'])
@login_required
def get_transactions():
    user_id = session['user_id']
    
    deposits = Deposit.query.filter_by(user_id=user_id).order_by(Deposit.created_at.desc()).all()
    withdrawals = Withdrawal.query.filter_by(user_id=user_id).order_by(Withdrawal.created_at.desc()).all()
    
    # Simple serialization
    d_list = [{'type': 'deposit', 'amount': float(d.amount), 'status': d.status, 'date': d.created_at.isoformat()} for d in deposits]
    w_list = [{'type': 'withdrawal', 'amount': float(w.amount), 'status': w.status, 'date': w.created_at.isoformat()} for w in withdrawals]
    
    transactions = sorted(d_list + w_list, key=lambda x: x['date'], reverse=True)
    
    return jsonify(transactions), 200
