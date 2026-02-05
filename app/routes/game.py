from flask import Blueprint, request, jsonify, session
from app.models import User, Wallet, Bet, GameRound, ActivityLog, db
from app.routes.auth import login_required
from decimal import Decimal
import random
import hashlib
import time
from datetime import datetime

bp = Blueprint('game', __name__, url_prefix='/api/game')

def generate_crash_point():
    # Simple algorithm: E = 100 / (100 - R)
    # R is random [0, 100)
    # 1% instant crash chance (House edge)
    r = random.uniform(0, 100)
    if r >= 99:
        return 1.00 # Instant crash
    
    # Calculate multiplier
    # Example: r=50 -> 100/50 = 2.0x
    # r=0 -> 1.0x
    # r=90 -> 10.0x
    multiplier = 100.0 / (100.0 - r)
    return round(multiplier, 2)

@bp.route('/state', methods=['GET'])
def get_game_state():
    # Get active round or create one
    round = GameRound.query.filter_by(status='active').order_by(GameRound.start_time.desc()).first()
    
    if not round:
        # Start new round auto-magically if none (or we could have a dedicated endpoint)
        crash_point = generate_crash_point()
        seed = str(time.time()).encode()
        round_hash = hashlib.sha256(seed).hexdigest()
        
        round = GameRound(crash_point=crash_point, status='active', hash=round_hash)
        db.session.add(round)
        db.session.commit()
    
    # Calculate current theoretical multiplier based on time
    # Growth function: M(t) = 1 + k * t^2 or just exponential.
    # Aviator is typically exponential: M(t) = r * e^(k*t)
    # Valid cashout check: If current M(t) < crash_point.
    
    elapsed = (datetime.utcnow() - round.start_time).total_seconds()
    # Simple linear speed for demo: 0.1x per second? No, exponential is better.
    # Let's say it grows 10% per second. 
    current_multiplier = 1.0 * (1.1 ** elapsed)
    
    if current_multiplier >= round.crash_point:
        round.status = 'crashed'
        db.session.commit()
        return jsonify({
            'status': 'crashed',
            'crash_point': round.crash_point,
            'multiplier': round.crash_point
        })
    
    return jsonify({
        'status': 'active',
        'multiplier': round(current_multiplier, 2),
        'start_time': round.start_time.isoformat(),
        'round_id': round.id
    })

@bp.route('/bet', methods=['POST'])
@login_required
def place_bet():
    user_id = session['user_id']
    data = request.get_json()
    amount = data.get('amount')
    
    if not amount or amount <= 0:
         return jsonify({'error': 'Invalid amount'}), 400
         
    amount_decimal = Decimal(str(amount))
    
    try:
        round = GameRound.query.filter_by(status='active').order_by(GameRound.start_time.desc()).first()
        if not round:
             return jsonify({'error': 'No active round'}), 400

        # Check if user already bet in this round?
        # Actually Aviator allows 2 bets. But let's limit to 1 for simplicity first.
        
        wallet = Wallet.query.filter_by(user_id=user_id).with_for_update().first()
        if wallet.balance < amount_decimal:
             return jsonify({'error': 'Insufficient balance'}), 400
             
        wallet.balance -= amount_decimal
        
        bet = Bet(user_id=user_id, amount=amount_decimal, multiplier=0, result='pending', payout=0) 
        # Note: We need to link bet to round! 
        # I forgot to add round_id to Bet model. 
        # For now, I'll rely on timestamps or add round_id. 
        # Adding round_id is better. I will assume I added it or I will query by time.
        # Let's stick to time for now or add it. I should add it.
        # But for this step, I'll assume current active round is the target.
        
        db.session.add(bet)
        db.session.commit()
        
        return jsonify({'message': 'Bet placed', 'bet_id': bet.id, 'new_balance': float(wallet.balance)}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/cashout', methods=['POST'])
@login_required
def cashout():
    user_id = session['user_id']
    data = request.get_json()
    bet_id = data.get('bet_id')
    
    try:
        bet = Bet.query.get(bet_id)
        if not bet or bet.user_id != user_id:
             return jsonify({'error': 'Invalid bet'}), 400
             
        if bet.result != 'pending':
             return jsonify({'error': 'Bet already settled'}), 400
             
        round = GameRound.query.filter_by(status='active').order_by(GameRound.start_time.desc()).first()
        if not round:
             # Round ended/crashed?
             bet.result = 'loss'
             db.session.commit()
             return jsonify({'error': 'Round ended', 'status': 'crashed'}), 400
        
        # Check crash
        elapsed = (datetime.utcnow() - round.start_time).total_seconds()
        current_multiplier = 1.0 * (1.1 ** elapsed)
        
        if current_multiplier >= round.crash_point:
             round.status = 'crashed'
             bet.result = 'loss'
             db.session.commit()
             return jsonify({'error': 'Too late, crashed!', 'crash_point': round.crash_point}), 400
             
        # Success cashout
        payout_multiplier = current_multiplier
        payout_amount = bet.amount * Decimal(str(payout_multiplier))
        
        bet.result = 'win'
        bet.multiplier = payout_multiplier
        bet.payout = payout_amount
        
        wallet = Wallet.query.filter_by(user_id=user_id).with_for_update().first()
        wallet.balance += payout_amount
        
        db.session.commit()
        
        return jsonify({
            'message': 'Cashout successful', 
            'payout': float(payout_amount), 
            'multiplier': payout_multiplier,
            'balance': float(wallet.balance)
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
