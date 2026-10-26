import unittest

from optimizer import (
    assign_crews,
    detour_min,
    evaluate,
    greedy_cover,
    haversine_km,
    insertion_cost,
    nearest_neighbor,
    two_opt,
)


class OptimizerTests(unittest.TestCase):
    def test_haversine_marilia_assis(self):
        km = haversine_km(-22.2142, -49.9458, -22.6617, -50.4120)
        self.assertGreater(km, 50)
        self.assertLess(km, 90)

    def test_two_opt_shortens_crossing(self):
        dur = [
            [0, 1, 9, 2],
            [1, 0, 9, 1],
            [9, 9, 0, 1],
            [2, 1, 1, 0],
        ]
        naive = [1, 2, 3]
        improved = two_opt(naive, dur, 0, 0, service=0)
        self.assertLess(
            sum_path(improved, dur),
            sum_path(naive, dur),
        )

    def test_sla_marks_late_stop(self):
        dur = [[0, 30], [30, 0]]
        found = evaluate([1], dur, dur, 0, 0, {1: 10}, service=0)
        self.assertIn(1, found["late"])

    def test_insertion_picks_the_small_detour(self):
        dur = [
            [0, 10, 40, 12],
            [10, 0, 40, 8],
            [40, 40, 0, 30],
            [12, 8, 30, 0],
        ]
        near = insertion_cost([], 3, dur, 0, 0, service=0)
        far = insertion_cost([], 2, dur, 0, 0, service=0)
        self.assertIsNotNone(near)
        self.assertLess(near[1], far[1])

    def test_critical_goes_to_the_skilled_crew(self):
        crews = [
            {"id": "A", "matrix": 0, "skills": ["geral"]},
            {"id": "B", "matrix": 1, "skills": ["geral", "radar"]},
        ]
        stops = [{"matrix": 2, "skill": "radar", "priority": "critica", "due_min": 30}]
        dur = [
            [0, 5, 50],
            [5, 0, 8],
            [50, 8, 0],
        ]
        plan = assign_crews(crews, stops, dur, dur)
        owned = {crew["id"]: crew["order"] for crew in plan["crews"]}
        self.assertEqual(owned["B"], [2])
        self.assertEqual(owned["A"], [])

    def test_detour_under_eight_minutes(self):
        route = [(-22.21, -49.95), (-22.22, -49.96)]
        extra = (-22.214, -49.954)
        self.assertLess(detour_min(route, extra), 8)

    def test_greedy_cover_picks_the_larger_set(self):
        found = greedy_cover(["a", "b", "c"], {"viatura": {"a", "b"}, "moto": {"c"}})
        self.assertEqual(found["chosen"], "viatura")
        self.assertEqual(found["pct"], 67)


def sum_path(order, dur):
    current = 0
    total = 0
    for stop in order:
        total += dur[current][stop]
        current = stop
    return total + dur[current][0]


if __name__ == "__main__":
    unittest.main()
