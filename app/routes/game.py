from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
import math
import secrets

from flask import Blueprint, current_app, jsonify, request, session
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.models import Bet, GameRound, RoundBet, Wallet, db, utcnow
from app.routes.auth import login_required
from app.utils import AMOUNT_ERROR, CENT, json_body, parse_amount

bp = Blueprint('game', __name__, url_prefix='/api/game')

BETTING_SECONDS = 8
CRASH_DISPLAY_SECONDS = 3
GROWTH_RATE = 1.1
GAME_CLOCK_LOCK_KEY = 0x41564941  # arbitrary constant for pg_advisory_xact_lock


def _now():
    return utcnow()


def generate_crash_point():
    roll = secrets.randbelow(10_000) / 100
    if roll >= 99:
        return 1.0
    return round(100 / (100 - roll), 2)


def _new_round(now):
    return GameRound(
        crash_point=generate_crash_point(),
        status='waiting',
        start_time=now + timedelta(seconds=BETTING_SECONDS),
    )


def _crash_time(game_round):
    if game_round.crash_point <= 1:
        duration = 0
    else:
        duration = math.log(game_round.crash_point, GROWTH_RATE)
    return game_round.start_time + timedelta(seconds=duration)


def _current_multiplier(game_round, now):
    elapsed = max(0, (now - game_round.start_time).total_seconds())
    return GROWTH_RATE ** elapsed


def _settle_losses(game_round):
    bets = (
        Bet.query.join(RoundBet, RoundBet.bet_id == Bet.id)
        .filter(RoundBet.round_id == game_round.id, Bet.result == 'pending')
        .with_for_update()
        .all()
    )
    for bet in bets:
        bet.result = 'loss'
        bet.multiplier = game_round.crash_point
        bet.payout = Decimal('0.00')


def _user_bet(game_round, user_id):
    if not user_id:
        return None

    bet = (
        Bet.query.join(RoundBet, RoundBet.bet_id == Bet.id)
        .filter(RoundBet.round_id == game_round.id, Bet.user_id == user_id)
        .order_by(Bet.id.desc())
        .first()
    )
    if not bet:
        return None

    return {
        'id': bet.id,
        'amount': float(bet.amount),
        'result': bet.result,
        'multiplier': bet.multiplier,
        'payout': float(bet.payout or 0),
    }


def _round_state(game_round, now):
    state = {
        'round_id': game_round.id,
        'status': game_round.status,
        'start_time': f'{game_round.start_time.isoformat()}Z',
        'server_time': f'{now.isoformat()}Z',
    }

    if game_round.status == 'waiting':
        state['starts_in'] = max(0, math.ceil((game_round.start_time - now).total_seconds()))
        state['multiplier'] = 1.0
    elif game_round.status == 'active':
        state['multiplier'] = round(_current_multiplier(game_round, now), 2)
    else:
        crash_time = _crash_time(game_round)
        state['multiplier'] = game_round.crash_point
        state['crash_point'] = game_round.crash_point
        state['next_round_in'] = max(
            0,
            math.ceil((crash_time + timedelta(seconds=CRASH_DISPLAY_SECONDS) - now).total_seconds()),
        )

    user_bet = _user_bet(game_round, session.get('user_id'))
    if user_bet:
        state['my_bet'] = user_bet
    return state


def _needs_transition(game_round, now):
    if game_round is None:
        return True
    if game_round.status == 'crashed':
        return now >= _crash_time(game_round) + timedelta(seconds=CRASH_DISPLAY_SECONDS)
    if game_round.status == 'waiting':
        return now >= game_round.start_time
    if game_round.status == 'active':
        return now >= _crash_time(game_round)
    return False


def _lock_game_clock():
    """Serialize round transitions across concurrent requests.

    Locking the latest row is not enough: two requests can both see a crashed
    round and both insert a new one. A transaction-scoped advisory lock makes
    the whole check-and-advance step run one request at a time on PostgreSQL.
    SQLite (used in tests) already serializes writers.
    """
    if db.engine.dialect.name == 'postgresql':
        db.session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': GAME_CLOCK_LOCK_KEY})


def _advance_round(now):
    """Move the latest round forward; caller must hold the game clock lock."""
    game_round = GameRound.query.order_by(GameRound.id.desc()).with_for_update().first()

    if game_round is None or (
        game_round.status == 'crashed'
        and now >= _crash_time(game_round) + timedelta(seconds=CRASH_DISPLAY_SECONDS)
    ):
        game_round = _new_round(now)
        db.session.add(game_round)
        db.session.flush()

    if game_round.status == 'waiting' and now >= game_round.start_time:
        game_round.status = 'active'

    if game_round.status == 'active' and now >= _crash_time(game_round):
        game_round.status = 'crashed'
        _settle_losses(game_round)

    return game_round


@bp.route('/state', methods=['GET'])
def get_game_state():
    now = _now()
    # Fast path: a plain read with no row locks, so polling clients don't block each other.
    game_round = GameRound.query.order_by(GameRound.id.desc()).first()

    if _needs_transition(game_round, now):
        try:
            _lock_game_clock()
            game_round = _advance_round(now)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception('Unable to advance game round')
            return jsonify({'error': 'Game state unavailable right now'}), 503

    return jsonify(_round_state(game_round, now))


@bp.route('/history', methods=['GET'])
def get_history():
    rounds = (
        GameRound.query.filter_by(status='crashed')
        .order_by(GameRound.id.desc())
        .limit(10)
        .all()
    )
    return jsonify([
        {'round_id': game_round.id, 'crash_point': game_round.crash_point}
        for game_round in rounds
    ])


@bp.route('/bet', methods=['POST'])
@login_required
def place_bet():
    data = json_body(request)
    if data is None:
        return jsonify({'error': 'A JSON request body is required'}), 400

    amount = parse_amount(data.get('amount'))
    if amount is None:
        return jsonify({'error': AMOUNT_ERROR}), 400

    user_id = session['user_id']
    now = _now()

    try:
        game_round = GameRound.query.order_by(GameRound.id.desc()).with_for_update().first()
        if not game_round or game_round.status != 'waiting' or now >= game_round.start_time:
            return jsonify({'error': 'Bets are accepted only during the betting window'}), 409

        wallet = Wallet.query.filter_by(user_id=user_id).with_for_update().first()
        if not wallet:
            return jsonify({'error': 'Demo credit wallet not found'}), 404
        if wallet.balance < amount:
            return jsonify({'error': 'Insufficient demo credits'}), 400

        wallet.balance -= amount
        bet = Bet(
            user_id=user_id,
            amount=amount,
            multiplier=0,
            result='pending',
            payout=Decimal('0.00'),
        )
        db.session.add(bet)
        db.session.flush()
        db.session.add(RoundBet(bet_id=bet.id, round_id=game_round.id, user_id=user_id))
        db.session.commit()

        return jsonify({
            'message': 'Demo bet placed',
            'bet_id': bet.id,
            'round_id': game_round.id,
            'balance': float(wallet.balance),
        })
    except IntegrityError:
        db.session.rollback()
        return jsonify({'error': 'You already placed a bet in this round'}), 409
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception('Unable to place demo bet')
        return jsonify({'error': 'Unable to place bet right now'}), 500


@bp.route('/cashout', methods=['POST'])
@login_required
def cashout():
    data = json_body(request)
    if data is None:
        return jsonify({'error': 'A JSON request body is required'}), 400

    try:
        bet_id = int(data.get('bet_id'))
    except (TypeError, ValueError):
        return jsonify({'error': 'A valid bet ID is required'}), 400

    user_id = session['user_id']
    round_bet = (
        RoundBet.query.join(Bet, Bet.id == RoundBet.bet_id)
        .filter(RoundBet.bet_id == bet_id, Bet.user_id == user_id)
        .first()
    )
    if not round_bet:
        return jsonify({'error': 'Bet not found for this account'}), 404

    try:
        game_round = GameRound.query.filter_by(id=round_bet.round_id).with_for_update().first()
        bet = Bet.query.filter_by(id=bet_id, user_id=user_id).with_for_update().first()
        if not game_round or not bet:
            return jsonify({'error': 'Bet round no longer exists'}), 404
        if bet.result != 'pending':
            return jsonify({'error': 'This bet has already been settled'}), 409
        if game_round.status != 'active':
            return jsonify({'error': 'The round is not in flight'}), 409

        now = _now()
        if now >= _crash_time(game_round):
            game_round.status = 'crashed'
            _settle_losses(game_round)
            db.session.commit()
            return jsonify({'error': 'The round crashed before cashout', 'status': 'crashed'}), 409

        multiplier = _current_multiplier(game_round, now)
        wallet = Wallet.query.filter_by(user_id=user_id).with_for_update().first()
        if not wallet:
            return jsonify({'error': 'Demo credit wallet not found'}), 404

        payout = (bet.amount * Decimal(str(multiplier))).quantize(CENT, rounding=ROUND_HALF_UP)
        bet.result = 'win'
        bet.multiplier = multiplier
        bet.payout = payout
        wallet.balance += payout
        db.session.commit()

        return jsonify({
            'message': 'Cashout successful',
            'payout': float(payout),
            'multiplier': multiplier,
            'balance': float(wallet.balance),
        })
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception('Unable to cash out demo bet')
        return jsonify({'error': 'Unable to cash out right now'}), 500
