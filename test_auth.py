import tempfile
import unittest
from pathlib import Path
from werkzeug.security import generate_password_hash
from app import create_app
from journal import add_machine, open_database, record_repair


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / 'test.db'
        self.app = create_app(self.path)
        self.app.config.update(TESTING=True, AUTH_USERNAME='test-user',
                               AUTH_PASSWORD_HASH=generate_password_hash('test-password-123'))
        self.client = self.app.test_client()
        db = open_database(self.path)
        add_machine(db, 'Test machine', 'DEMO-1', 100, 200)
        record_repair(db, 1, 100, 'Test repair', 0)
        db.close()

    def tearDown(self):
        self.folder.cleanup()

    def token(self):
        with self.client.session_transaction() as session:
            return session['csrf']

    def login(self):
        self.client.get('/login')
        return self.client.post('/login', data=dict(csrf=self.token(), username='test-user', password='test-password-123'))

    def test_anonymous_cannot_read_or_write(self):
        for path in ['/', '/machines/1']:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 303)
            self.assertTrue(response.location.endswith('/login'))
        self.assertEqual(self.client.post('/machines/1/delete', data={'confirm_number': 'DEMO-1'}).status_code, 303)
        db = open_database(self.path)
        self.assertEqual(db.execute('SELECT COUNT(*) FROM machines').fetchone()[0], 1)
        db.close()

    def test_login_invalid_password_csrf_and_logout(self):
        self.client.get('/login')
        response = self.client.post('/login', data=dict(csrf=self.token(), username='test-user', password='wrong'))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.login().status_code, 303)
        self.assertIn('Test machine', self.client.get('/').get_data(as_text=True))
        self.assertEqual(self.client.post('/logout').status_code, 400)
        self.client.post('/logout', data=dict(csrf=self.token()))
        self.assertEqual(self.client.get('/').status_code, 303)

    def test_delete_requires_correct_number_then_removes_history(self):
        self.login()
        self.client.post('/machines/1/delete', data=dict(csrf=self.token(), confirm_number='wrong'))
        self.assertEqual(self.client.get('/machines/1').status_code, 200)
        self.client.post('/machines/1/delete', data=dict(csrf=self.token(), confirm_number='DEMO-1'))
        self.assertEqual(self.client.get('/machines/1').status_code, 404)
        db = open_database(self.path)
        self.assertEqual(db.execute('SELECT COUNT(*) FROM repairs').fetchone()[0], 0)
        db.close()

    def test_missing_credentials_blocks_access(self):
        self.app.config['AUTH_PASSWORD_HASH'] = ''
        self.assertEqual(self.client.get('/').status_code, 503)
