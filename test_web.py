import tempfile
import unittest
from pathlib import Path
from app import create_app


class WebTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.app = create_app(Path(self.folder.name) / 'test.db')
        self.app.config['TESTING'] = True
        self.app.config['AUTH_REQUIRED'] = False
        self.client = self.app.test_client()
        self.client.get('/')
        with self.client.session_transaction() as session:
            self.token = session['csrf']

    def tearDown(self):
        self.folder.cleanup()

    def post(self, path, **data):
        return self.client.post(path, data=dict(csrf=self.token, **data), follow_redirects=True)

    def add(self):
        return self.post('/machines', name='Учебный погрузчик', number='DEMO', hours='1470', next_service='1500')

    def test_full_flow_and_persistence(self):
        self.assertIn('Учебный погрузчик', self.add().get_data(as_text=True))
        response = self.post('/machines/1/repairs', hours='1480', description='Замена фильтра')
        self.assertIn('Замена фильтра', response.get_data(as_text=True))
        self.assertNotIn('Всего расходов', response.get_data(as_text=True))
        self.assertNotIn('name="cost"', response.get_data(as_text=True))
        self.assertNotIn('₽', response.get_data(as_text=True))
        response = self.client.get('/?q=учебный&view=upcoming')
        self.assertIn('Учебный погрузчик', response.get_data(as_text=True))
        self.assertEqual(self.client.get('/machines/999').status_code, 404)

    def test_invalid_hours_and_duplicate_preserve_data(self):
        self.add()
        self.assertIn('уже существует', self.add().get_data(as_text=True))
        response = self.post('/machines/1', hours='100', next_service='1600')
        self.assertIn('не может уменьшаться', response.get_data(as_text=True))
        self.assertIn('1470', response.get_data(as_text=True))

    def test_csrf_and_numeric_validation(self):
        self.assertEqual(self.client.post('/machines', data={}).status_code, 400)
        result = self.post('/machines', name='Test', number='X', hours='bad', next_service='1500')
        self.assertIn('должны быть целыми', result.get_data(as_text=True))

    def test_html_is_escaped(self):
        response = self.post('/machines', name='<script>alert(1)</script>', number='X', hours='0', next_service='50')
        self.assertNotIn('<script>alert(1)</script>', response.get_data(as_text=True))
        self.assertIn('&lt;script&gt;', response.get_data(as_text=True))

    def test_shared_banner_and_common_data(self):
        self.app.config['PUBLIC_SHARED'] = True
        self.add()
        visitor = self.app.test_client()
        page = visitor.get('/').get_data(as_text=True)
        self.assertIn('Общий журнал без регистрации', page)
        self.assertIn('Учебный погрузчик', page)

    def test_text_limits_are_checked_on_server(self):
        response = self.post('/machines', name='X' * 161, number='TEST', hours='0', next_service='500')
        self.assertIn('160 символов', response.get_data(as_text=True))
