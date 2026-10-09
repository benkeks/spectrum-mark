import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import run_cadp
import run_mcrl2
from compare_results import load_results, mcrl2_notion


class RunnerTests(unittest.TestCase):
    def test_mcrl2_selects_all_relations_in_both_modes(self):
        preorders = {
            "sim", "ready-sim", "trace", "trace-ac", "failures", "impossible-futures",
            "weak-trace", "weak-trace-ac", "weak-failures", "failures-divergence", "coupled-sim",
        }
        with patch.object(run_mcrl2, "available_equivalences", return_value=["sim", "trace"]), \
                patch.object(run_mcrl2, "available_preorders", return_value=preorders):
            strong = run_mcrl2.available_comparisons(Path("ltscompare"))
            weak = run_mcrl2.available_comparisons(Path("ltscompare"), weak=True)
        self.assertEqual({name for name, mode in strong + weak if mode == "preorder"}, preorders)
        self.assertIn(("sim", "equivalence"), strong)
        self.assertIn(("sim", "preorder"), strong)
        self.assertIn(("failures", "preorder"), strong)
        self.assertIn(("impossible-futures", "preorder"), strong)
        self.assertIn(("failures-divergence", "preorder"), weak)
        self.assertIn(("weak-failures", "preorder"), weak)
        self.assertEqual(len(strong), len(set(strong)))
        self.assertEqual(len(weak), len(set(weak)))

    def test_cadp_selects_all_bisimulator_preorders(self):
        for weak in (False, True):
            comparisons = run_cadp.available_comparisons(weak)
            equivalences = run_cadp.WEAK_EQUIVALENCES if weak else run_cadp.EQUIVALENCES
            self.assertEqual({name for name, mode in comparisons if mode == "equivalence"}, set(equivalences))
            self.assertEqual(
                {name for name, mode in comparisons if mode == "preorder"},
                {name for name in equivalences if run_cadp.CHECKERS[name][0] == "bisimulator"},
            )
            self.assertEqual(len(comparisons), len(set(comparisons)))

    def test_cadp_command_direction(self):
        process = Mock(returncode=0)
        process.communicate.return_value = ("TRUE\n", "")
        for mode, option in (("equivalence", "-equal"), ("preorder", "-smaller")):
            with patch.object(run_cadp.subprocess, "Popen", return_value=process) as popen:
                result = run_cadp.compare(
                    Path("/cadp/bin.x64"), Path("left.bcg"), Path("right.bcg"),
                    "bisim-bisimulator", {}, Path("/tmp"), mode,
                )
            command = popen.call_args.args[0]
            self.assertEqual(command[-3:], ["-strong", option, "right.bcg"])
            self.assertEqual(command[1], "left.bcg")
            self.assertEqual(result[1:], ("true", "ok"))
        with self.assertRaises(ValueError):
            run_cadp.compare(Path("/cadp/bin.x64"), Path("left.bcg"), Path("right.bcg"),
                             "bisim-bcg-cmp", {}, Path("/tmp"), "preorder")

    def test_relation_mappings(self):
        expected = {
            "trace-ac": "trace", "weak-trace-ac": "weak-trace",
            "failures": "failure", "weak-failures": "stable-failure",
            "failures-divergence": "failures-divergence",
            "impossible-futures": "impossible-future",
            "bisim-bisimulator": "simulation",
            "weak-bisim-bisimulator": "weak-simulation",
            "branching-bisim-bisimulator": "cadp-branching-simulation",
            "cadp-taustar": "cadp-taustar-simulation",
            "cadp-safety": "cadp-taustar-simulation",
        }
        for name, notion in expected.items():
            with self.subTest(name=name):
                self.assertEqual(mcrl2_notion(name, "preorder"), notion)
        self.assertEqual(mcrl2_notion("bisim-bisimulator"), "bisimulation")
        self.assertEqual(mcrl2_notion("weak-bisim-bisimulator"), "weak-bisimulation")

    def test_mixed_report_and_legacy_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "results.csv"
            with report.open("w", newline="") as result_file:
                writer = csv.writer(result_file)
                writer.writerow(("left", "right", "equivalence", "mode", "equivalent", "status"))
                writer.writerow(("P", "Q", "bisim-bisimulator", "equivalence", "false", "ok"))
                writer.writerow(("P", "Q", "bisim-bisimulator", "preorder", "true", "ok"))
                writer.writerow(("P", "Q", "trace", "equivalence", "false", "ok"))
                writer.writerow(("P", "Q", "trace", "preorder", "true", "ok"))
            self.assertEqual(load_results(report), {("P", "Q"): ({"simulation", "trace"}, "ok")})
            with report.open("w", newline="") as result_file:
                writer = csv.writer(result_file)
                writer.writerow(("left", "right", "equivalence", "equivalent", "status"))
                writer.writerow(("P", "Q", "bisim-bisimulator", "true", "ok"))
            self.assertEqual(load_results(report), {("P", "Q"): ({"bisimulation"}, "ok")})


if __name__ == "__main__":
    unittest.main()