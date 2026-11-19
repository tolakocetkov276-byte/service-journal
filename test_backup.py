import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from app import create_app
from journal import open_database, add_machine


class BackupTests(unittest.TestCase):
    def test_only_separate_token_downloads_valid_database(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            database = root / 'source.db'
            connection = open_database(database)
            add_machine(connection, 'Backup test', 'B-01', 10, 100)
            connection.close()
            token = 'a' * 64
            auth = root / 'backup-auth.json'
            auth.write_text(json.dumps({'token_sha256': hashlib.sha256(token.encode()).hexdigest()}))
            app = create_app(database)
            app.config.update(TESTING=True, BACKUP_AUTH_FILE=str(auth))
            client = app.test_client()
            self.assertEqual(client.get('/backup/database').status_code, 401)
            self.assertEqual(client.get('/backup/database', headers={'Authorization': 'Bearer wrong'}).status_code, 401)
            response = client.get('/backup/database', headers={'Authorization': 'Bearer ' + token})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers['Cache-Control'], 'no-store, private')
            restored = root / 'restored.db'
            restored.write_bytes(response.data)
            with closing(sqlite3.connect(restored)) as db:
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(db.execute('SELECT name FROM machines').fetchone()[0], 'Backup test')
