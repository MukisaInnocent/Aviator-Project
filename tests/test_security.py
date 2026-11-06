import unittest
from decimal import Decimal

from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models import ActivityLog, Deposit, User, Wallet


class TestConfig:
    TESTING = True
    SECRET_KEY = 'test-secret'
    SQLALCHEMY_DATABASE_URI = 'sqlite://'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    CORS_ORIGINS = []


class SecurityTests(unittest.TestCase):
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
        self.user_id = self._make_user('player', role='user', balance='50.00')
        self.admin_id = self._make_user('boss', role='admin')
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()

    def _make_user(self, name, role='user', balance='0.00'):
        user = User(
            username=name,
            email=f'{name}@example.test',
            password_hash=generate_password_hash('password123'),
            role=role,
        )
        db.session.add(user)
        db.session.flush()
        db.session.add(Wallet(user_id=user.id, balance=Decimal(balance)))
        db.session.commit()
        return user.id

    def login_as(self, user_id):
        with self.client.session_transaction() as session:
            session['user_id'] = user_id

    # --- registration / XSS ---------------------------------------------

    def test_register_rejects_html_username(self):
        response = self.client.post('/api/auth/register', json={
            'username': '<img src=x onerror=alert(1)>',
            'email': 'x@example.test',
            'password': 'password123',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(User.query.filter_by(email='x@example.test').first())

    def test_register_and_login_round_trip(self):
        created = self.client.post('/api/auth/register', json={
            'username': 'new_user', 'email': 'New@Example.test', 'password': 'password123',
        })
        self.assertEqual(created.status_code, 201)
        short = self.client.post('/api/auth/register', json={
            'username': 'other', 'email': 'o@example.test', 'password': 'short',
        })
        self.assertEqual(short.status_code, 400)

        login = self.client.post('/api/auth/login', json={'username': 'new_user', 'password': 'password123'})
        self.assertEqual(login.status_code, 200)
        self.assertEqual(self.client.get('/api/auth/me').json['email'], 'new@example.test')

    def test_admin_pages_escape_usernames(self):
        with open('app/templates/admin.html', encoding='utf-8') as fh:
            html = fh.read()
        self.assertNotIn('<td>${d.username}</td>', html)
        self.assertIn('escapeHtml(u.username)', html)

    # --- CSRF guard -----------------------------------------------------

    def test_cross_origin_post_is_blocked(self):
        self.login_as(self.user_id)
        response = self.client.post(
            '/api/wallet/deposit', json={'amount': '5'},
            headers={'Origin': 'https://evil.example'},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Deposit.query.count(), 0)

    def test_same_origin_post_is_allowed(self):
        self.login_as(self.user_id)
        response = self.client.post(
            '/api/wallet/deposit', json={'amount': '5'},
            headers={'Origin': 'http://localhost'},
        )
        self.assertEqual(response.status_code, 201)

    def test_form_encoded_post_is_rejected(self):
        self.login_as(self.user_id)
        response = self.client.post('/api/wallet/deposit', data={'amount': '5'})
        self.assertEqual(response.status_code, 415)

    # --- wallet validation ----------------------------------------------

    def test_wallet_rejects_bad_amounts_without_500(self):
        self.login_as(self.user_id)
        for bad in ['abc', '', '-1', '0', '1.001', 'NaN', 'Infinity', True, None, '1e12']:
            for endpoint in ('/api/wallet/deposit', '/api/wallet/withdraw'):
                response = self.client.post(endpoint, json={'amount': bad})
                self.assertEqual(response.status_code, 400, f'{endpoint} {bad!r}')
        self.assertEqual(self.client.post('/api/wallet/withdraw', json={'amount': '60'}).status_code, 400)
        self.assertEqual(self.client.post('/api/wallet/withdraw', json={'amount': '20.50'}).status_code, 201)

    # --- admin ----------------------------------------------------------

    def test_admin_page_requires_admin_role(self):
        self.login_as(self.user_id)
        self.assertEqual(self.client.get('/admin').status_code, 403)
        self.login_as(self.admin_id)
        self.assertEqual(self.client.get('/admin').status_code, 200)

    def test_admin_logs_endpoint(self):
        db.session.add(ActivityLog(user_id=self.user_id, action_type='LOGIN', description='hi', ip_address='1.2.3.4'))
        db.session.add(ActivityLog(user_id=None, action_type='SYSTEM', description=None))
        db.session.commit()

        self.login_as(self.user_id)
        self.assertEqual(self.client.get('/api/admin/logs').status_code, 403)

        self.login_as(self.admin_id)
        response = self.client.get('/api/admin/logs')
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row['username'] for row in response.json}, {'player', '-'})

    def test_deposit_approve_and_reject(self):
        self.login_as(self.user_id)
        self.client.post('/api/wallet/deposit', json={'amount': '10'})
        self.client.post('/api/wallet/deposit', json={'amount': '7'})
        first, second = [d.id for d in Deposit.query.order_by(Deposit.id)]

        self.login_as(self.admin_id)
        approved = self.client.post(f'/api/admin/deposits/{first}/process', json={'action': 'approve'})
        rejected = self.client.post(f'/api/admin/deposits/{second}/process', json={'action': 'reject'})
        missing = self.client.post('/api/admin/deposits/999/process', json={'action': 'approve'})
        bad = self.client.post(f'/api/admin/deposits/{second}/process', json={'action': 'steal'})

        self.assertEqual(approved.json['message'], 'Deposit approved successfully')
        self.assertEqual(rejected.json['message'], 'Deposit rejected successfully')
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(Wallet.query.filter_by(user_id=self.user_id).first().balance, Decimal('60.00'))

    def test_suspended_user_session_is_revoked(self):
        self.login_as(self.user_id)
        self.assertEqual(self.client.get('/api/auth/me').status_code, 200)

        user = db.session.get(User, self.user_id)
        user.is_active = False
        db.session.commit()

        self.assertEqual(self.client.get('/api/auth/me').status_code, 401)


if __name__ == '__main__':
    unittest.main()
