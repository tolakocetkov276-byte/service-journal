import sqlite3
import unittest
from unittest.mock import patch

from journal import add_machine, open_database, record_repair, search_machines, service_status, show_upcoming_service
from journal import repair_total, show_repair_history


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.db = open_database(":memory:")
        add_machine(self.db, "Учебный погрузчик", "DEMO-01", 1200, 1500)

    def tearDown(self):
        self.db.close()

    def test_service_status(self):
        self.assertEqual(service_status(1200, 1500), "До ТО: 300 м/ч")
        self.assertEqual(service_status(1449, 1500), "До ТО: 51 м/ч")
        self.assertEqual(service_status(1450, 1500), "Скоро ТО! Осталось 50 м/ч")
        self.assertEqual(service_status(1500, 1500), "ТО требуется сейчас")
        self.assertEqual(service_status(1520, 1500), "ТО просрочено на 20 м/ч")

    def test_duplicate_inventory_number_is_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            add_machine(self.db, "Другая машина", "DEMO-01", 0, 250)

    def test_repair_updates_hours_but_keeps_service_plan(self):
        record_repair(self.db, 1, 1210, "Замена фильтра", 150000)
        machine = self.db.execute("SELECT * FROM machines WHERE id = 1").fetchone()
        self.assertEqual((machine["hours"], machine["next_service"]), (1210, 1500))
        repair = self.db.execute("SELECT * FROM repairs").fetchone()
        self.assertEqual(repair["cost_kopecks"], 150000)
        self.assertEqual(repair_total(self.db, 1), 150000)

    def test_invalid_repair_does_not_change_data(self):
        for machine_id, hours in [(1, 1100), (99, 1300)]:
            with self.assertRaises(ValueError):
                record_repair(self.db, machine_id, hours, "Ремонт", 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM repairs").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT hours FROM machines").fetchone()[0], 1200)

    def test_search_machines_finds_machine(self):
        with patch("builtins.input", return_value="DEMO"):
            with patch("builtins.print") as mock_print:
                search_machines(self.db)

        first_message = mock_print.call_args_list[0].args[0]
        self.assertIn("Учебный погрузчик", first_message)

    def test_search_machines_reports_no_results(self):
        with patch("builtins.input", return_value="НЕСУЩЕСТВУЕТ"):
            with patch("builtins.print") as mock_print:
                search_machines(self.db)

        mock_print.assert_called_once_with("Техника не найдена.")

    def test_upcoming_service_is_sorted_by_urgency(self):
        add_machine(self.db, "Позже", "LATE", 100, 140)
        add_machine(self.db, "Срочно", "SOON", 100, 110)
        add_machine(self.db, "Просрочено", "OVERDUE", 120, 100)

        with patch("builtins.print") as mock_print:
            show_upcoming_service(self.db)

        messages = [call.args[0] for call in mock_print.call_args_list]
        self.assertIn("Просрочено", messages[0])
        self.assertIn("Срочно", messages[1])
        self.assertIn("Позже", messages[2])

    def test_repair_total_is_zero_without_repairs(self):
        self.assertEqual(repair_total(self.db, 1), 0)

    def test_show_repair_history_prints_repair_and_total(self):
        record_repair(self.db, 1, 1210, "Замена фильтра", 150000)

        with patch("builtins.print") as mock_print:
            show_repair_history(self.db, 1)

        messages = [call.args[0] for call in mock_print.call_args_list]
        output = "\n".join(messages)

        self.assertIn("История: Учебный погрузчик", output)
        self.assertIn("Замена фильтра", output)
        self.assertIn("Всего затрат на ремонты: 1500.00 ₽", output)


if __name__ == "__main__":
    unittest.main()
