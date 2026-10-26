import unittest
from datetime import datetime

import model
import ops_dayroutes
import ops_intel
import ops_orders


class IntelTests(unittest.TestCase):
    def test_zombie_needs_two_windows(self):
        self.assertTrue(ops_intel.is_zombie(10, [1, 1]))
        self.assertFalse(ops_intel.is_zombie(10, [9, 1]))

    def test_root_cause_groups_the_energy_node(self):
        failures = [{"id": f"E{i}", "energy_node": "N-07", "network_node": "R-01", "supplier": "A", "firmware": "fw"} for i in range(5)]
        population = {("energy_node", "N-07"): 8, ("network_node", "R-01"): 20, ("supplier", "A"): 20, ("firmware", "fw"): 20}
        found = ops_intel.cluster_cause(failures, population)
        self.assertEqual(found["key"], "N-07")
        self.assertGreaterEqual(found["confidence"], 60)

    def test_wait_cost(self):
        self.assertEqual(ops_intel.wait_cost(40, 2, 1.4), 112)

    def test_offline_routes_cover_open_orders(self):
        moment = datetime(2026, 10, 26, 18, 0, tzinfo=model.TZ)
        data = model.build_demo(moment)
        ops_orders.reconcile(data, moment)
        ops_dayroutes.ensure_scenario(data, moment)
        plan = ops_dayroutes.optimize(data, moment, allow_network=False)["plan"]
        self.assertGreaterEqual(plan["stop_count"], 1)
        self.assertGreaterEqual(len(plan["crews"]), 2)
        self.assertTrue(all(item.get("approximate") for item in plan["crews"] if item.get("stops")))

    def test_mother_demo_keeps_the_collision(self):
        moment = datetime(2026, 10, 26, 18, 0, tzinfo=model.TZ)
        data = model.build_demo(moment)
        hero = next(item for item in data["incidents"] if "Sampaio Vidal" in item["title"] and item["status"] == "aberto")
        ops_intel.ensure(data, moment)
        message = ops_intel.demo_step(data, 1, moment)["message"]
        self.assertIn("N-07", message)
        self.assertEqual(hero["status"], "aberto")
        self.assertIsNone(hero.get("assigned_agent_id"))


if __name__ == "__main__":
    unittest.main()
