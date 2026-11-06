import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from app import create_app, db
from app.models import Bet, GameRound, RoundBet, User, Wallet


NOW = datetime(2026, 1, 1, 12, 0, 0)


class TestConfig:
    TESTING = True
    SECRET_KEY = 'test-secret'
    SQLALCHEMY_DATABASE_URI = 'sqlite://'
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class GameFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app(TestConfig)
        cls.app_context = cls.app.app_context()
        cls.app_context.push()

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        db.engine.dispose()
        cls.app_context.pop()

    def setUp(self):
        db.drop_all()
        db.create_all()

        user = User(
            username='player',
            email='player@example.test',
            password_hash='unused',
        )
        db.session.add(user)
        db.session.flush()
        db.session.add(Wallet(user_id=user.id, balance=Decimal('100.00')))
        db.session.commit()
        self.user_id = user.id
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session['user_id'] = self.user_id

    def tearDown(self):
        db.session.remove()

    def create_round_and_bet(self, crash_point=2.0):
        with patch('app.routes.game._now', return_value=NOW), patch(
            'app.routes.game.generate_crash_point', return_value=crash_point
        ):
            state_response = self.client.get('/api/game/state')
            self.assertEqual(state_response.status_code, 200)
            self.assertEqual(state_response.json['status'], 'waiting')
            bet_response = self.client.post('/api/game/bet', json={'amount': '10.00'})

        self.assertEqual(bet_response.status_code, 200)
        return state_response.json['round_id'], bet_response.json['bet_id']

    def test_bet_is_only_accepted_during_betting_window(self):
        with patch('app.routes.game._now', return_value=NOW), patch(
            'app.routes.game.generate_crash_point', return_value=2.0
        ):
            self.client.get('/api/game/state')
            accepted = self.client.post('/api/game/bet', json={'amount': '10.00'})

        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(float(Wallet.query.filter_by(user_id=self.user_id).first().balance), 90.0)
        self.assertEqual(RoundBet.query.count(), 1)
        self.assertEqual(Bet.query.first().result, 'pending')

        with patch('app.routes.game._now', return_value=NOW):
            duplicate = self.client.post('/api/game/bet', json={'amount': '5.00'})
            invalid_precision = self.client.post('/api/game/bet', json={'amount': '1.001'})

        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(invalid_precision.status_code, 400)
        self.assertEqual(float(Wallet.query.filter_by(user_id=self.user_id).first().balance), 90.0)

        with patch('app.routes.game._now', return_value=NOW + timedelta(seconds=8)):
            active = self.client.get('/api/game/state')
            late_bet = self.client.post('/api/game/bet', json={'amount': '5.00'})

        self.assertEqual(active.json['status'], 'active')
        self.assertEqual(late_bet.status_code, 409)

    def test_dashboard_renders_demo_game_controls(self):
        response = self.client.get('/dashboard')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Demo credits have no cash value', response.data)
        self.assertIn(b'id="btn-cashout"', response.data)
        self.assertIn(b'Flight history', response.data)

    def test_cashout_pays_using_server_multiplier(self):
        _, bet_id = self.create_round_and_bet()

        with patch('app.routes.game._now', return_value=NOW + timedelta(seconds=8)):
            self.assertEqual(self.client.get('/api/game/state').json['status'], 'active')

        with patch('app.routes.game._now', return_value=NOW + timedelta(seconds=9)):
            response = self.client.post('/api/game/cashout', json={'bet_id': bet_id})

        self.assertEqual(response.status_code, 200)
        self.assertAlmostEqual(response.json['multiplier'], 1.1)
        self.assertEqual(response.json['payout'], 11.0)
        self.assertEqual(float(Wallet.query.filter_by(user_id=self.user_id).first().balance), 101.0)

    def test_crash_settles_bet_and_old_bet_cannot_cash_out_in_new_round(self):
        first_round_id, bet_id = self.create_round_and_bet(crash_point=1.21)
        crash_time = NOW + timedelta(seconds=8 + 2.01)

        with patch('app.routes.game._now', return_value=crash_time):
            crashed = self.client.get('/api/game/state')

        self.assertEqual(crashed.json['status'], 'crashed')
        bet = db.session.get(Bet, bet_id)
        self.assertEqual(bet.result, 'loss')
        self.assertEqual(float(Wallet.query.filter_by(user_id=self.user_id).first().balance), 90.0)

        new_round_time = NOW + timedelta(seconds=8 + 2 + 3.1)
        with patch('app.routes.game._now', return_value=new_round_time), patch(
            'app.routes.game.generate_crash_point', return_value=2.0
        ):
            next_round = self.client.get('/api/game/state')

        self.assertEqual(next_round.json['status'], 'waiting')
        self.assertNotEqual(next_round.json['round_id'], first_round_id)

        with patch(
            'app.routes.game._now',
            return_value=new_round_time + timedelta(seconds=8),
        ):
            self.assertEqual(self.client.get('/api/game/state').json['status'], 'active')
            old_cashout = self.client.post('/api/game/cashout', json={'bet_id': bet_id})

        self.assertEqual(old_cashout.status_code, 409)
        self.assertEqual(float(Wallet.query.filter_by(user_id=self.user_id).first().balance), 90.0)

    def test_stale_active_round_crashes_without_multiplier_overflow(self):
        game_round = GameRound(
            crash_point=2.0,
            status='active',
            start_time=NOW - timedelta(days=7),
        )
        db.session.add(game_round)
        db.session.flush()
        bet = Bet(
            user_id=self.user_id,
            amount=Decimal('10.00'),
            multiplier=0,
            result='pending',
            payout=Decimal('0.00'),
        )
        db.session.add(bet)
        db.session.flush()
        db.session.add(RoundBet(bet_id=bet.id, round_id=game_round.id, user_id=self.user_id))
        db.session.commit()

        with patch('app.routes.game._now', return_value=NOW):
            response = self.client.get('/api/game/state')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['status'], 'crashed')
        self.assertEqual(db.session.get(Bet, bet.id).result, 'loss')


if __name__ == '__main__':
    unittest.main()
