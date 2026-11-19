"""Локальный веб-интерфейс. Запуск: python app.py."""
import os
import secrets
import sqlite3
import json
from pathlib import Path
from datetime import timedelta
from werkzeug.security import check_password_hash
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from journal import DB_PATH, SERVICE_WARNING_THRESHOLD, add_machine, open_database, record_repair, service_status


def create_app(database=None, shared=False):
    app = Flask(__name__)
    app.config.update(SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
                      DATABASE=str(database or os.environ.get("JOURNAL_DATABASE") or DB_PATH),
                      MAX_CONTENT_LENGTH=64 * 1024,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      PUBLIC_SHARED=False, AUTH_REQUIRED=True,
                      AUTH_USERNAME=os.environ.get("JOURNAL_USERNAME", ""),
                      AUTH_PASSWORD_HASH=os.environ.get("JOURNAL_PASSWORD_HASH", ""),
                      PERMANENT_SESSION_LIFETIME=timedelta(hours=8))
    auth_file = Path(app.instance_path) / "auth.json"
    if auth_file.exists():
        credentials = json.loads(auth_file.read_text(encoding="utf-8"))
        app.config["AUTH_USERNAME"] = app.config["AUTH_USERNAME"] or credentials["username"]
        app.config["AUTH_PASSWORD_HASH"] = app.config["AUTH_PASSWORD_HASH"] or credentials["password_hash"]

    def db():
        if "db" not in g:
            g.db = open_database(app.config["DATABASE"])
        return g.db

    @app.teardown_appcontext
    def close_database(error):
        connection = g.pop("db", None)
        if connection is not None:
            connection.close()

    @app.before_request
    def protect_forms():
        if request.endpoint == "static":
            return
        if app.config["AUTH_REQUIRED"]:
            if not app.config["AUTH_USERNAME"] or not app.config["AUTH_PASSWORD_HASH"]:
                return render_template("setup.html"), 503
            if request.endpoint != "login" and not session.get("authenticated"):
                return redirect(url_for("login"), code=303)
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(24)
        if request.method == "POST" and not secrets.compare_digest(
                request.form.get("csrf", ""), session["csrf"]):
            abort(400, "Форма устарела. Обновите страницу и повторите действие.")

    @app.after_request
    def private_pages(response):
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if session.get("authenticated"):
            return redirect(url_for("index"))
        error = None
        if request.method == "POST":
            username = request.form.get("username", "")
            password = request.form.get("password", "")
            password_ok = check_password_hash(app.config["AUTH_PASSWORD_HASH"], password)
            if secrets.compare_digest(username.encode(), app.config["AUTH_USERNAME"].encode()) and password_ok:
                session.clear()
                session["authenticated"] = True
                session["csrf"] = secrets.token_hex(24)
                session.permanent = True
                return redirect(url_for("index"), code=303)
            error = "Неверный логин или пароль."
        return render_template("login.html", error=error), 401 if error else 200

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"), code=303)

    @app.context_processor
    def helpers():
        return dict(service_status=service_status)

    def number(field):
        try:
            value = int(request.form[field])
            if value < 0 or value > 2_000_000_000:
                raise ValueError
            return value
        except (ValueError, KeyError):
            raise ValueError("Моточасы должны быть целыми числами от 0 до 2 миллиардов.")

    def text(field, limit):
        value = request.form.get(field, "").strip()
        if not value or len(value) > limit:
            raise ValueError(f"Заполните поле; допустимо от 1 до {limit} символов.")
        return value

    @app.route("/")
    def index():
        query = request.args.get("q", "").strip()
        upcoming = request.args.get("view") == "upcoming"
        all_machines = db().execute("SELECT * FROM machines ORDER BY id DESC").fetchall()
        machines = [m for m in all_machines if not query or
                    query.casefold() in m["name"].casefold() or query.casefold() in m["number"].casefold()]
        if upcoming:
            machines = sorted([m for m in machines if m["next_service"] - m["hours"] <= SERVICE_WARNING_THRESHOLD],
                              key=lambda m: m["next_service"] - m["hours"])
        return render_template("index.html", machines=machines, query=query, upcoming=upcoming,
                               total=len(all_machines), due=sum(m["next_service"] <= m["hours"] for m in all_machines),
                               soon=sum(0 < m["next_service"] - m["hours"] <= SERVICE_WARNING_THRESHOLD for m in all_machines))

    @app.post("/machines")
    def add():
        try:
            add_machine(db(), text("name", 160), text("number", 80),
                        number("hours"), number("next_service"))
            flash("Техника добавлена.", "success")
        except sqlite3.IntegrityError:
            flash("Такой инвентарный номер уже существует.", "error")
        except ValueError as error:
            flash(str(error), "error")
        return redirect(url_for("index"), code=303)

    @app.route("/machines/<int:machine_id>", methods=["GET", "POST"])
    def detail(machine_id):
        machine = db().execute("SELECT * FROM machines WHERE id = ?", (machine_id,)).fetchone()
        if machine is None:
            abort(404)
        if request.method == "POST":
            try:
                hours = number("hours")
                if hours < machine["hours"]:
                    raise ValueError("Наработка не может уменьшаться.")
                next_service = number("next_service")
                with db():
                    db().execute("UPDATE machines SET hours = ?, next_service = ? WHERE id = ?",
                                 (hours, next_service, machine_id))
                flash("Моточасы и план ТО обновлены.", "success")
            except ValueError as error:
                flash(str(error), "error")
            return redirect(url_for("detail", machine_id=machine_id), code=303)
        repairs = db().execute("SELECT * FROM repairs WHERE machine_id = ? ORDER BY id DESC", (machine_id,)).fetchall()
        return render_template("detail.html", machine=machine, repairs=repairs)

    @app.post("/machines/<int:machine_id>/repairs")
    def repair(machine_id):
        if db().execute("SELECT id FROM machines WHERE id = ?", (machine_id,)).fetchone() is None:
            abort(404)
        try:
            record_repair(db(), machine_id, number("hours"), text("description", 4000), 0)
            flash("Ремонт записан. План ТО не изменён.", "success")
        except ValueError as error:
            flash(str(error), "error")
        return redirect(url_for("detail", machine_id=machine_id), code=303)

    @app.post("/machines/<int:machine_id>/delete")
    def delete_machine(machine_id):
        machine = db().execute("SELECT * FROM machines WHERE id = ?", (machine_id,)).fetchone()
        if machine is None:
            abort(404)
        if request.form.get("confirm_number", "").strip() != machine["number"]:
            flash("Номер не совпадает. Техника не удалена.", "error")
            return redirect(url_for("detail", machine_id=machine_id), code=303)
        with db():
            db().execute("DELETE FROM repairs WHERE machine_id = ?", (machine_id,))
            db().execute("DELETE FROM machines WHERE id = ?", (machine_id,))
        flash("Техника и история её ремонтов удалены.", "success")
        return redirect(url_for("index"), code=303)

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5055, debug=False)
