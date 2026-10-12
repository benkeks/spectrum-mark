import csv
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import run_cadp
import run_equivio
import run_mcrl2
import run_suite
import compare_results
from compare_results import load_results, mcrl2_notion
from example import PAIRS, WEAK_PAIRS, resolve_input
from spectrum import WEAK_COMPARISON_SPECTRUM


class RunnerTests(unittest.TestCase):
    def test_equivio_divergence_command(self):
        process = Mock(returncode=0)
        process.communicate.return_value = ("weak-bisimulation\n", None)
        with patch.object(run_equivio.subprocess, "Popen", return_value=process) as popen:
            result = run_equivio.compare(Path("equivio.jar"), Path("input.csv"), "P", "Q",
                                         weak=True, divergences=True)
        command = popen.call_args.args[0]
        self.assertIn("--divergences", command)
        self.assertNotIn("--strong-game", command)
        self.assertEqual(result[1:], ("weak-bisimulation", "ok"))
        with self.assertRaisesRegex(ValueError, "weak"):
            run_equivio.compare(Path("equivio.jar"), Path("input.csv"), "P", "Q", divergences=True)

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

    def test_divergence_input_requires_deadlock_and_fresh_delta(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.csv"
            source.write_text("0,0,tau\n0,P,implicit-main\n")
            with self.assertRaisesRegex(ValueError, "deadlock"):
                run_equivio.validate_divergence_input(source)
            source.write_text("0,0,tau\n0,P,implicit-main\n1,Q,implicit-main\n")
            run_equivio.validate_divergence_input(source)
            source.write_text("0,1,\u03b4\n0,P,implicit-main\n1,Q,implicit-main\n")
            with self.assertRaisesRegex(ValueError, "delta"):
                run_equivio.validate_divergence_input(source)

    def test_delta_frontiers_do_not_imply_native_relations(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "results.csv"
            with report.open("w", newline="") as result_file:
                writer = csv.writer(result_file)
                writer.writerow(("left", "right", "spectrum", "preorders", "status"))
                writer.writerow(("P", "Q", "weak-divergences", "branching-bisimulation", "ok"))
            self.assertEqual(load_results(report), {("P", "Q"): ({"delta-branching-bisimulation"}, "ok")})
        spectrum = WEAK_COMPARISON_SPECTRUM
        self.assertTrue(spectrum.dominates("delta-branching-bisimulation", "delta-weak-trace"))
        self.assertFalse(spectrum.dominates("delta-branching-bisimulation", "weak-trace"))
        self.assertFalse(spectrum.dominates("branching-bisimulation", "delta-weak-trace"))
        self.assertEqual(spectrum.unmatched({"delta-branching-bisimulation"},
                                           {"divergence-preserving-branching-bisimulation"}),
                         {"delta-branching-bisimulation"})

    def test_comparison_does_not_rank_different_spectrum_families(self):
        with tempfile.TemporaryDirectory() as directory:
            reports = []
            for spectrum in ("weak", "weak-divergences"):
                report = Path(directory) / f"{spectrum}.csv"
                with report.open("w", newline="") as result_file:
                    writer = csv.writer(result_file)
                    writer.writerow(("left", "right", "spectrum", "preorders", "status"))
                    writer.writerow(("P", "Q", spectrum, "branching-bisimulation", "ok"))
                reports.append(report)
            output = io.StringIO()
            with patch.object(compare_results.sys, "argv", ["compare_results.py", *map(str, reports)]), \
                    patch.object(compare_results.sys, "stdout", output):
                compare_results.main()
            self.assertIn("not comparable (different spectrum families)", output.getvalue())
            self.assertNotIn("INCONSISTENCY", output.getvalue())

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

    def test_mixed_report_requires_explicit_mode(self):
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
            with self.assertRaisesRegex(ValueError, "mode"):
                load_results(report)

    def test_custom_csv_pairs(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "custom.csv"
            source.write_text("0,1,a\n0,P,implicit-main\n1,Q,implicit-main\n2,R,implicit-main\n")
            self.assertEqual(resolve_input(source), (source, [("P", "Q"), ("P", "R"), ("Q", "R")]))
            self.assertEqual(resolve_input(source, [("Q", "R")])[1], [("Q", "R")])
            with self.assertRaisesRegex(ValueError, "Invalid comparison pair"):
                resolve_input(source, [("P", "missing")])
            with self.assertRaisesRegex(ValueError, "Duplicate comparison pair"):
                resolve_input(source, [("P", "Q"), ("Q", "P")])

    def test_suite_defaults_to_both_curated_csvs(self):
        with patch.object(run_suite.sys, "argv", ["run_suite.py"]), \
                patch.object(run_suite, "run_dataset") as run_dataset:
            run_suite.main()
        self.assertEqual(run_dataset.call_count, 2)
        strong, weak = [call.args for call in run_dataset.call_args_list]
        self.assertEqual((strong[0].name, strong[1], strong[2]), ("ltbts1.csv", list(PAIRS), False))
        self.assertEqual((weak[0].name, weak[1], weak[2]), ("ltbts2.csv", list(WEAK_PAIRS), True))

    def test_suite_collects_both_weak_spectra(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            source = output_dir / "custom.csv"
            source.write_text("0,0,tau\n0,P,implicit-main\n1,Q,implicit-main\n")
            for tool in (*run_suite.TOOLS, "equivio-divergences"):
                (output_dir / f"custom-{tool}.csv").write_text("status\nok\n")
            with patch.object(run_suite.subprocess, "run") as run, patch("builtins.print"):
                run_suite.run_dataset(source, [("P", "Q")], True, output_dir, divergences=True)
            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual(len(commands), 10)
            self.assertEqual(Path(commands[3][1]).name, "run_equivio.py")
            self.assertIn("--divergences", commands[3])
            self.assertNotIn("--divergences", commands[0])
            self.assertEqual(len(list(output_dir.glob("*-vs-*.txt"))), 6)

    def test_suite_runs_tools_then_all_comparisons(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            source = output_dir / "custom.csv"
            for tool in run_suite.TOOLS:
                (output_dir / f"custom-{tool}.csv").write_text("status\nok\n")
            with patch.object(run_suite.subprocess, "run") as run, patch("builtins.print"):
                run_suite.run_dataset(source, [("P", "Q")], True, output_dir, Path("/cadp/bin.x64"))
            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual(len(commands), 6)
            self.assertEqual(
                [Path(command[1]).name for command in commands[:3]],
                ["run_equivio.py", "run_mcrl2.py", "run_cadp.py"],
            )
            for command in commands[:3]:
                self.assertIn("--weak", command)
                self.assertEqual(command[command.index("--csv") + 1], str(source))
                self.assertEqual(command[command.index("--pair") + 1:][:2], ["P", "Q"])
            self.assertIn("--cadp-bin", commands[2])
            for command in commands[3:]:
                self.assertEqual(Path(command[1]).name, "compare_results.py")
                self.assertIn("--weak", command)
            self.assertEqual(len(list(output_dir.glob("*-vs-*.txt"))), 3)


if __name__ == "__main__":
    unittest.main()