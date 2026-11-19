"""Журнал техники: первая версия на Python и SQLite, без сторонних библиотек."""

import sqlite3
from datetime import date
from pathlib import Path


DB_PATH = Path(__file__).with_name("journal.db")
SERVICE_WARNING_THRESHOLD = 50


def open_database(path=DB_PATH):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS machines (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            number TEXT NOT NULL UNIQUE,
            hours INTEGER NOT NULL CHECK(hours >= 0),
            next_service INTEGER NOT NULL CHECK(next_service >= 0)
        );
        CREATE TABLE IF NOT EXISTS repairs (
            id INTEGER PRIMARY KEY,
            machine_id INTEGER NOT NULL REFERENCES machines(id),
            repair_date TEXT NOT NULL,
            hours INTEGER NOT NULL CHECK(hours >= 0),
            description TEXT NOT NULL,
            cost_kopecks INTEGER NOT NULL CHECK(cost_kopecks >= 0)
        );
    """)
    return connection


def add_machine(db, name, number, hours, next_service):
    if not name.strip() or not number.strip() or hours < 0 or next_service < 0:
        raise ValueError("Заполните название, номер и неотрицательные моточасы.")
    with db:
        db.execute(
            "INSERT INTO machines(name, number, hours, next_service) VALUES (?, ?, ?, ?)",
            (name.strip(), number.strip(), hours, next_service),
        )


def record_repair(db, machine_id, hours, description, cost_kopecks):
    machine = db.execute("SELECT * FROM machines WHERE id = ?", (machine_id,)).fetchone()
    if machine is None:
        raise ValueError("Техника с таким ID не найдена.")
    if hours < machine["hours"]:
        raise ValueError("Новая наработка не может быть меньше текущей.")
    if not description.strip() or cost_kopecks < 0:
        raise ValueError("Укажите выполненные работы и неотрицательную стоимость.")
    # Обе записи сохраняются вместе: либо ремонт и наработка, либо ничего.
    with db:
        db.execute(
            "INSERT INTO repairs(machine_id, repair_date, hours, description, cost_kopecks) "
            "VALUES (?, ?, ?, ?, ?)",
            (machine_id, date.today().isoformat(), hours, description.strip(), cost_kopecks),
        )
        db.execute("UPDATE machines SET hours = ? WHERE id = ?", (hours, machine_id))


def service_status(hours, next_service):
    remaining = next_service - hours

    if remaining < 0:
        return f"ТО просрочено на {-remaining} м/ч"
    elif remaining == 0:
        return "ТО требуется сейчас"
    elif remaining <= SERVICE_WARNING_THRESHOLD:
        return f"Скоро ТО! Осталось {remaining} м/ч"

    return f"До ТО: {remaining} м/ч"


def ask_text(prompt):
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("Поле не должно быть пустым.")


def ask_number(prompt):
    while True:
        try:
            value = int(input(prompt))
            if value >= 0:
                return value
        except ValueError:
            pass
        print("Введите целое число от нуля.")


def show_machine(machine):
    print(f"\nID {machine['id']} | {machine['name']} | № {machine['number']}")
    print(f"Наработка: {machine['hours']} м/ч | "
          f"{service_status(machine['hours'], machine['next_service'])}")


def show_machines(db):
    machines = db.execute("SELECT * FROM machines ORDER BY id").fetchall()
    if not machines:
        print("Техники пока нет. Добавьте первую машину через пункт 2.")
    for machine in machines:
        show_machine(machine)


def show_upcoming_service(db):
    machines = db.execute(
        "SELECT * FROM machines WHERE next_service - hours <= ? "
        "ORDER BY next_service - hours",
        (SERVICE_WARNING_THRESHOLD,)
    ).fetchall()

    if not machines:
        print("Ближайших ТО нет.")
        return

    for machine in machines:
        status = service_status(machine["hours"], machine["next_service"])
        print(f"{machine['name']} | № {machine['number']} | {status}")

def search_machines(db):
    query = ask_text("Введите модель или инвентарный номер: ")

    machines = db.execute(
        "SELECT * FROM machines "
        "WHERE instr(lower(name), lower(?)) > 0 "
        "OR instr(lower(number), lower(?)) > 0 "
        "ORDER BY id",
        (query, query),
    ).fetchall()
    if not machines:
        print("Техника не найдена.")
        return

    for machine in machines:
        show_machine(machine)


def repair_total(db, machine_id):
    row = db.execute(
        "SELECT COALESCE(SUM(cost_kopecks), 0) AS total "
        "FROM repairs WHERE machine_id = ?",
        (machine_id,),
    ).fetchone()
    return row["total"]

def show_repair_history(db, machine_id):
    machine = db.execute(
        "SELECT name FROM machines WHERE id = ?",
        (machine_id,),
    ).fetchone()

    if machine is None:
        raise ValueError("Техника с таким ID не найдена.")
    repairs = db.execute(
        "SELECT * FROM repairs WHERE machine_id = ? ORDER BY id DESC",
        (machine_id,),
    ).fetchall()

    print(f"История: {machine['name']}")
    if not repairs:
        print("Ремонтов пока нет.")

    for repair in repairs:
        print(f"{repair['repair_date']} | {repair['hours']} м/ч | "
              f"{repair['description']} | {repair['cost_kopecks'] / 100:.2f} ₽")

    total_kopecks = repair_total(db, machine_id)
    print(f"Всего затрат на ремонты: {total_kopecks / 100:.2f} ₽")


def main():
    db = open_database()
    print("ЖУРНАЛ ОБСЛУЖИВАНИЯ ТЕХНИКИ")
    print("Данные сохраняются в journal.db рядом с программой.")
    try:
        while True:
            print("\n1 — Вся техника\n2 — Добавить технику\n3 — Записать ремонт")
            print("4 — История ремонтов\n5 — Обновить моточасы и план ТО")
            print("6 — Техника, которой скоро нужно ТО")
            print("7 — Найти технику")
            print("0 — Выход")
            choice = input("Выберите действие: ").strip()
            try:
                if choice == "0":
                    break
                if choice == "1":
                    show_machines(db)
                elif choice == "2":
                    add_machine(db, ask_text("Модель: "), ask_text("Инвентарный номер: "),
                                ask_number("Текущие моточасы: "),
                                ask_number("На какой наработке следующее ТО: "))
                    print("Техника добавлена.")
                elif choice == "3":
                    show_machines(db)
                    record_repair(db, ask_number("ID техники: "),
                                  ask_number("Наработка на момент ремонта: "),
                                  ask_text("Работы и запчасти: "),
                                  ask_number("Стоимость в целых рублях: ") * 100)
                    print("Ремонт сохранён. План ТО автоматически не меняется.")
                elif choice == "4":
                    machine_id = ask_number("ID техники: ")
                    show_repair_history(db, machine_id)
                elif choice == "5":
                    show_machines(db)
                    machine_id = ask_number("ID техники: ")
                    machine = db.execute("SELECT * FROM machines WHERE id = ?",
                                         (machine_id,)).fetchone()
                    if machine is None:
                        raise ValueError("Техника с таким ID не найдена.")
                    hours = ask_number("Текущие моточасы: ")
                    if hours < machine["hours"]:
                        raise ValueError("Наработка не может уменьшаться.")
                    next_service = ask_number("На какой наработке следующее ТО: ")
                    with db:
                        db.execute("UPDATE machines SET hours = ?, next_service = ? WHERE id = ?",
                                   (hours, next_service, machine_id))
                    print("Данные обновлены.")
                elif choice == "6":
                    show_upcoming_service(db)
                elif choice == "7":
                    search_machines(db)
                else:
                    print("Выберите пункт из меню.")
            except sqlite3.IntegrityError:
                print("Не удалось сохранить: такой инвентарный номер уже существует "
                      "или данные не соответствуют ограничениям базы.")
            except ValueError as error:
                print(error)
    except (KeyboardInterrupt, EOFError):
        print("\nРабота завершена.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
