import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch


class PublicSetupTests(unittest.TestCase):
    def test_public_database_and_secret_are_separate_and_persistent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = Path(__file__).with_name('wsgi.py')
            shutil.copyfile(source, root / 'wsgi.py')
            local = root / 'journal.db'
            local.write_bytes(b'local-data-must-not-change')
            spec = importlib.util.spec_from_file_location('public_setup_test', root / 'wsgi.py')
            module = importlib.util.module_from_spec(spec)
            with patch.dict('os.environ', {'SECRET_KEY': '', 'JOURNAL_DATABASE': str(local)}):
                spec.loader.exec_module(module)
                first = module.application
                second = module.create_public_app()
            self.assertEqual(first.config['SECRET_KEY'], second.config['SECRET_KEY'])
            self.assertEqual(first.config['DATABASE'], str(root / 'instance' / 'public.db'))
            first.config['AUTH_REQUIRED'] = False
            self.assertEqual(first.test_client().get('/').status_code, 200)
            self.assertTrue((root / 'instance' / 'public.db').exists())
            self.assertEqual(local.read_bytes(), b'local-data-must-not-change')
