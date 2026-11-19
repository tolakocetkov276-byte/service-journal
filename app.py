"""Локальный веб-интерфейс. Запуск: python app.py."""
import os
import secrets
import sqlite3
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from journal import DB_PATH, SERVICE_WARNING_THRESHOLD, add_machine, open_database, record_repair, repair_total, service_status


def create_app(database=None, shared=False):
    app = Flask(__name__)
    app.config.update(SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
                      DATABASE=str(database or os.environ.get("JOURNAL_DATABASE") or DB_PATH),
                      MAX_CONTENT_LENGTH=64 * 1024,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      PUBLIC_SHARED=shared)

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
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(24)
        if request.method == "POST" and not secrets.compare_digest(
                request.form.get("csrf", ""), session["csrf"]):
            abort(400, "Форма устарела. Обновите страницу и повторите действие.")

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
            raise ValueError("Моточасы и стоимость должны быть целыми числами от 0 до 2 миллиардов.")

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
        return render_template("detail.html", machine=machine, repairs=repairs, total_cost=repair_total(db(), machine_id))

    @app.post("/machines/<int:machine_id>/repairs")
    def repair(machine_id):
        if db().execute("SELECT id FROM machines WHERE id = ?", (machine_id,)).fetchone() is None:
            abort(404)
        try:
            record_repair(db(), machine_id, number("hours"), text("description", 4000), number("cost") * 100)
            flash("Ремонт записан. План ТО не изменён.", "success")
        except ValueError as error:
            flash(str(error), "error")
        return redirect(url_for("detail", machine_id=machine_id), code=303)

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5055, debug=False)
