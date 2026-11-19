"""Однократная настройка общей учётной записи без сохранения открытого пароля."""
import getpass
import json
from pathlib import Path
from werkzeug.security import generate_password_hash


def main():
    username = input("Логин: ").strip()
    if not username or len(username) > 120:
        raise SystemExit("Логин должен содержать от 1 до 120 символов.")
    password = getpass.getpass("Пароль (ввод скрыт): ")
    if len(password) < 12:
        raise SystemExit("Используйте пароль длиной не менее 12 символов.")
    if password != getpass.getpass("Повторите пароль: "):
        raise SystemExit("Пароли не совпадают.")
    folder = Path(__file__).resolve().parent / "instance"
    folder.mkdir(exist_ok=True)
    path = folder / "auth.json"
    if path.exists() and input("Заменить текущую учётную запись? Введите ДА: ") != "ДА":
        raise SystemExit("Отменено.")
    path.write_text(json.dumps(dict(username=username, password_hash=generate_password_hash(password))), encoding="utf-8")
    print("Доступ настроен. Перезапустите приложение. Файл instance/auth.json не публикуйте.")


if __name__ == "__main__":
    main()
