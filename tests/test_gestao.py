import unittest
from datetime import datetime

import ops_compliance
import ops_finance
import ops_ledger
import ops_memory
import ops_presence
import ops_staffing
import ops_windows


class FinanceTests(unittest.TestCase):
    def test_loss_formula(self):
        self.assertEqual(ops_finance.loss(2, 10), 20.0)

    def test_sampaio_costs_more_than_a_side_street(self):
        radar = {"type": "radar", "region": "Sampaio Vidal"}
        other = {"type": "radar", "region": "Fragata"}
        self.assertGreater(ops_finance.hour_cost(radar), ops_finance.hour_cost(other))

    def test_projection_follows_a_rising_series(self):
        self.assertGreater(ops_finance.project_year([10, 20, 30, 40]), 0)


class ComplianceTests(unittest.TestCase):
    def test_expired_and_seven_day_window(self):
        today = datetime(2026, 10, 26).date()
        expired = {"type": "radar", "validade_afericao": "2026-10-01"}
        soon = {"type": "balanca", "validade_afericao": "2026-11-01"}
        self.assertEqual(ops_compliance.bucket(expired, today), "vencida")
        self.assertEqual(ops_compliance.bucket(soon, today), "7")
        self.assertFalse(ops_compliance.annotate({"type": "camera"}, today))


class PresenceTests(unittest.TestCase):
    def test_far_checkin_is_suspect(self):
        order = {"kind": "corretiva", "started_at": "2026-10-26T10:00:00-03:00"}
        equipment = {"lat": -22.2174, "lng": -49.9652}
        moment = datetime.fromisoformat("2026-10-26T10:40:00-03:00")
        near = ops_presence.review(order, equipment, {
            "checkin_lat": -22.2174, "checkin_lng": -49.9652, "foto_antes": "a", "foto_depois": "b",
        }, {"raio_presenca_m": 150, "tempo_minimo_min": {"corretiva": 20}}, moment)
        far = ops_presence.review(order, equipment, {
            "checkin_lat": -22.30, "checkin_lng": -49.80, "foto_antes": "a", "foto_depois": "b",
        }, {"raio_presenca_m": 150, "tempo_minimo_min": {"corretiva": 20}}, moment)
        self.assertEqual(near["conclusao"], "valida")
        self.assertEqual(far["conclusao"], "suspeita")
        self.assertTrue(any("fora do raio" in item for item in far["motivos"]))


class StaffingTests(unittest.TestCase):
    def test_more_teams_do_not_worsen_the_wait_sla(self):
        small = ops_staffing.simulate_day(2.0, 40, 1, seed=3)
        large = ops_staffing.simulate_day(2.0, 40, 8, seed=3)
        self.assertGreaterEqual(large["sla_pct"], small["sla_pct"])

    def test_recommendation_is_inside_the_range(self):
        found = ops_staffing.curve({"orders": []}, datetime(2026, 10, 26, 10, 0))
        self.assertTrue(found["recommendation"] is None or 1 <= found["recommendation"] <= 15)
        self.assertIn("95%", found["sentence"])


class MemoryTests(unittest.TestCase):
    def test_same_model_ranks_first(self):
        data = {
            "equipment": [
                {"id": "EQ-1", "type": "radar", "model": "SP-9", "serial": "RAD-1"},
                {"id": "EQ-2", "type": "camera", "model": "CAM-2", "serial": "CAM-1"},
            ],
            "orders": [
                {"id": "OS-1", "equipment_id": "EQ-1", "description": "falha de energia", "dica_do_tecnico": "Levar fonte reserva."},
                {"id": "OS-2", "equipment_id": "EQ-2", "description": "lente suja", "dica_do_tecnico": "Limpar a lente."},
            ],
        }
        tips = ops_memory.search(data, "energia", "radar", 3)
        self.assertEqual(tips[0]["tip"], "Levar fonte reserva.")


class WindowTests(unittest.TestCase):
    def test_peak_is_not_a_free_window(self):
        moment = datetime(2026, 10, 26, 8, 10)
        result = ops_windows.suggest({"equipment": [{"id": "EQ-1", "region": "Centro", "status": "operacional"}], "orders": []}, {"id": "EQ-9", "region": "Centro"}, moment)
        self.assertFalse(result["ok"])
        self.assertNotIn("08:", result["suggestion"])


class LedgerTests(unittest.TestCase):
    def test_tamper_breaks_the_chain(self):
        data = {}
        moment = datetime(2026, 10, 26, 12, 0)
        ops_ledger.append(data, moment, "Ana", "abriu OS", "OS-1", {"status": "aberta"})
        ops_ledger.append(data, moment, "Ana", "concluiu OS", "OS-1", {"status": "concluida"})
        self.assertTrue(ops_ledger.verify(data["ledger"])["ok"])
        data["ledger"][0]["payload"] = {"status": "cancelada"}
        verdict = ops_ledger.verify(data["ledger"])
        self.assertFalse(verdict["ok"])
        self.assertEqual(verdict["index"], 0)


if __name__ == "__main__":
    unittest.main()
