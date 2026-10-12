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
from compare_results import load_report, load_results, mcrl2_notion
from csv_to_aut import parse_csv
from example import PAIRS, PETERSON_PAIRS, WEAK_PAIRS, resolve_input
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
            divergent = run_mcrl2.available_comparisons(Path("ltscompare"), weak=True, divergences=True)
        self.assertEqual({name for name, mode in strong + weak + divergent if mode == "preorder"}, preorders)
        self.assertIn(("sim", "equivalence"), strong)
        self.assertIn(("sim", "preorder"), strong)
        self.assertIn(("failures", "preorder"), strong)
        self.assertIn(("impossible-futures", "preorder"), strong)
        self.assertNotIn(("failures-divergence", "preorder"), weak)
        self.assertIn(("failures-divergence", "preorder"), divergent)
        self.assertIn(("weak-failures", "preorder"), weak)
        self.assertEqual(len(strong), len(set(strong)))
        self.assertEqual(len(weak), len(set(weak)))

    def test_divergence_input_adds_unreachable_sink_and_reserves_delta(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.csv"
            source.write_text("0,0,tau\n0,P,implicit-main\n")
            original = source.read_text()
            run_equivio.validate_divergence_input(source)
            prepared = run_equivio.prepare_divergence_input(source, Path(directory) / "prepared.csv")
            transitions, meta = parse_csv(prepared)
            self.assertEqual(source.read_text(), original)
            self.assertEqual(transitions, [
                {"src": 0, "tar": 0, "action": "tau"},
                {"src": 2, "tar": 1, "action": "tau"},
            ])
            self.assertEqual([entry["state_name"] for entry in meta], ["P"])
            source.write_text("0,1,a\n0,P,main\n")
            self.assertEqual(run_equivio.prepare_divergence_input(source, prepared), source)
            source.write_text("0,1,\u03b4\n0,P,implicit-main\n1,Q,implicit-main\n")
            with self.assertRaisesRegex(ValueError, "delta"):
                run_equivio.validate_divergence_input(source)

    def test_delta_frontiers_do_not_imply_native_relations(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "results.csv"
            with report.open("w", newline="") as result_file:
                writer = csv.writer(result_file)
                writer.writerow(("left", "right", "spectrum", "seconds", "preorders", "status"))
                writer.writerow(("P", "Q", "weak-divergences", "1", "branching-bisimulation", "ok"))
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
                    writer.writerow(("left", "right", "spectrum", "seconds", "preorders", "status"))
                    writer.writerow(("P", "Q", spectrum, "1", "branching-bisimulation", "ok"))
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
            equivalences = [name for name in (run_cadp.WEAK_EQUIVALENCES if weak else run_cadp.EQUIVALENCES)
                            if not name.startswith("dpbranching-bisim")]
            self.assertEqual({name for name, mode in comparisons if mode == "equivalence"}, set(equivalences))
            self.assertEqual(
                {name for name, mode in comparisons if mode == "preorder"},
                {name for name in equivalences if run_cadp.CHECKERS[name][0] == "bisimulator"},
            )
            self.assertEqual(len(comparisons), len(set(comparisons)))

    def test_native_divergence_checks_are_exclusive_to_divergence_mode(self):
        equivalences = ["weak-bisim", "branching-bisim", "dpweak-bisim", "dpbranching-bisim-gv"]
        with patch.object(run_mcrl2, "available_equivalences", return_value=equivalences), \
                patch.object(run_mcrl2, "available_preorders", return_value={"weak-trace", "failures-divergence"}):
            ordinary = set(run_mcrl2.available_comparisons(Path("ltscompare"), weak=True))
            divergent = set(run_mcrl2.available_comparisons(Path("ltscompare"), weak=True, divergences=True))
        self.assertEqual(divergent, {("dpweak-bisim", "equivalence"),
                                     ("dpbranching-bisim-gv", "equivalence"),
                                     ("failures-divergence", "preorder")})
        self.assertFalse(ordinary & divergent)
        self.assertEqual(ordinary | divergent, {(name, "equivalence") for name in equivalences}
                         | {("weak-trace", "preorder"), ("failures-divergence", "preorder")})
        self.assertEqual(run_cadp.available_comparisons(weak=True, divergences=True),
                         [("dpbranching-bisim-bcg-cmp", "equivalence")])
        self.assertNotIn(("dpbranching-bisim-bcg-cmp", "equivalence"),
                         run_cadp.available_comparisons(weak=True))
        with self.assertRaises(ValueError):
            run_mcrl2.available_comparisons(Path("ltscompare"), divergences=True)
        with self.assertRaises(ValueError):
            run_cadp.available_comparisons(divergences=True)

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
                writer.writerow(("left", "right", "equivalence", "mode", "seconds", "equivalent", "status"))
                writer.writerow(("P", "Q", "bisim-bisimulator", "equivalence", "1", "false", "ok"))
                writer.writerow(("P", "Q", "bisim-bisimulator", "preorder", "1", "true", "ok"))
                writer.writerow(("P", "Q", "trace", "equivalence", "1", "false", "ok"))
                writer.writerow(("P", "Q", "trace", "preorder", "1", "true", "ok"))
            self.assertEqual(load_results(report), {("P", "Q"): ({"simulation", "trace"}, "ok")})
            with report.open("w", newline="") as result_file:
                writer = csv.writer(result_file)
                writer.writerow(("left", "right", "equivalence", "seconds", "equivalent", "status"))
                writer.writerow(("P", "Q", "bisim-bisimulator", "1", "true", "ok"))
            with self.assertRaisesRegex(ValueError, "mode"):
                load_results(report)

    def test_spectroscopy_cost_uses_fastest_algorithm_and_counts_false_answers(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "results.csv"
            with report.open("w", newline="") as result_file:
                writer = csv.writer(result_file)
                writer.writerow(("left", "right", "equivalence", "mode", "seconds", "equivalent", "status"))
                writer.writerows([
                    ("P", "Q", "branching-bisim", "equivalence", 4, "false", "ok"),
                    ("P", "Q", "branching-bisim-gv", "equivalence", 2, "false", "ok"),
                    ("P", "Q", "branching-bisim-gjkw", "equivalence", 3, "false", "ok"),
                    ("P", "Q", "weak-trace", "equivalence", 0.1, "false", "ok"),
                    ("P", "Q", "weak-trace", "preorder", 3, "true", "ok"),
                    ("P", "Q", "weak-trace-ac", "preorder", 1, "true", "ok"),
                    ("P", "Q", "weak-bisim", "equivalence", 5, "false", "ok"),
                ])
            results, costs = load_report(report)
            self.assertEqual(results, {("P", "Q"): ({"weak-trace"}, "ok")})
            cost = costs[("P", "Q")]
            self.assertEqual((cost.supported, cost.decided, cost.seconds), (3, 3, 8))
            self.assertTrue(cost.complete)

    def test_equivio_cost_counts_the_whole_spectrum(self):
        with tempfile.TemporaryDirectory() as directory:
            for spectrum, count in (("strong", 13), ("weak", 26), ("weak-divergences", 26)):
                report = Path(directory) / f"{spectrum}.csv"
                with report.open("w", newline="") as result_file:
                    writer = csv.writer(result_file)
                    writer.writerow(("left", "right", "spectrum", "seconds", "preorders", "status"))
                    writer.writerow(("P", "Q", spectrum, 0.7, "trace" if spectrum == "strong" else "weak-trace", "ok"))
                    writer.writerow(("Q", "P", spectrum, 0.9, "", "ok"))
                _, costs = load_report(report)
                self.assertEqual((costs[("P", "Q")].supported, costs[("P", "Q")].decided,
                                  costs[("P", "Q")].seconds), (count, count, 0.7))
                self.assertEqual(costs[("Q", "P")].decided, count)
                self.assertEqual(costs[("Q", "P")].seconds, 0.9)

    def test_conflicting_algorithms_are_reported_not_timed_as_decisions(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "results.csv"
            with report.open("w", newline="") as result_file:
                writer = csv.writer(result_file)
                writer.writerow(("left", "right", "equivalence", "mode", "seconds", "equivalent", "status"))
                writer.writerows([
                    ("P", "Q", "branching-bisim", "equivalence", 3, "true", "ok"),
                    ("P", "Q", "branching-bisim-gv", "equivalence", 2, "false", "ok"),
                    ("P", "Q", "branching-bisim-gj", "equivalence", 1, "true", "ok"),
                    ("P", "Q", "weak-trace", "preorder", 0.5, "true", "ok"),
                ])
            errors = io.StringIO()
            with patch.object(compare_results.sys, "stderr", errors):
                results, costs = load_report(report)
            self.assertIn("Conflicting algorithm results", errors.getvalue())
            self.assertEqual(results, {("P", "Q"): ({"weak-trace"}, "conflict")})
            cost = costs[("P", "Q")]
            self.assertEqual((cost.supported, cost.decided, cost.seconds), (2, 1, 0.5))
            self.assertFalse(cost.complete)
            self.assertIn("incomplete", compare_results.format_cost(cost))

    def test_failed_checks_do_not_become_fastest_decisions(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "results.csv"
            with report.open("w", newline="") as result_file:
                writer = csv.writer(result_file)
                writer.writerow(("left", "right", "equivalence", "mode", "seconds", "equivalent", "status"))
                writer.writerows([
                    ("P", "Q", "branching-bisim", "equivalence", 0.01, "", "error"),
                    ("P", "Q", "branching-bisim-gv", "equivalence", 2, "false", "ok"),
                    ("P", "Q", "weak-trace", "equivalence", 0.1, "false", "ok"),
                    ("P", "Q", "weak-trace", "preorder", 30, "", "timeout"),
                ])
            _, costs = load_report(report)
            cost = costs[("P", "Q")]
            self.assertEqual((cost.supported, cost.decided, cost.seconds), (2, 1, 2))
            self.assertFalse(cost.complete)

    def test_invalid_timings_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "results.csv"
            for seconds in ("nan", "inf", "-1"):
                with report.open("w", newline="") as result_file:
                    writer = csv.writer(result_file)
                    writer.writerow(("left", "right", "equivalence", "mode", "seconds", "equivalent", "status"))
                    writer.writerow(("P", "Q", "trace", "preorder", seconds, "true", "ok"))
                with self.assertRaisesRegex(ValueError, "elapsed time"):
                    load_report(report)

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

    def test_peterson_metadata_pairs_and_divergence_preparation(self):
        source = Path(__file__).resolve().parent / "examples" / "peterson-silent.csv"
        original = source.read_bytes()
        transitions, meta = parse_csv(source)
        self.assertEqual({entry["state_name"]: entry["state_id"] for entry in meta},
                         {"Pe": 19, "Mx": 24, "MxIC": 16})
        self.assertEqual(resolve_input(source, weak=True)[1], list(PETERSON_PAIRS))
        with tempfile.TemporaryDirectory() as directory:
            prepared = run_equivio.prepare_divergence_input(source, Path(directory) / source.name)
            marked_transitions, marked_meta = parse_csv(prepared)
            self.assertEqual(marked_transitions[:-1], transitions)
            self.assertEqual(marked_meta, meta)
            states = {row[field] for row in transitions for field in ("src", "tar")}
            added = marked_transitions[-1]
            self.assertNotIn(added["src"], states)
            self.assertNotIn(added["tar"], states)
            self.assertNotEqual(added["src"], added["tar"])
        self.assertEqual(source.read_bytes(), original)

    def test_suite_defaults_to_all_curated_csvs(self):
        with patch.object(run_suite.sys, "argv", ["run_suite.py"]), \
                patch.object(run_suite, "run_dataset") as run_dataset:
            run_suite.main()
        self.assertEqual(run_dataset.call_count, 3)
        strong, weak, peterson = [call.args for call in run_dataset.call_args_list]
        self.assertEqual((strong[0].name, strong[1], strong[2]), ("ltbts1.csv", list(PAIRS), False))
        self.assertEqual((weak[0].name, weak[1], weak[2]), ("ltbts2.csv", list(WEAK_PAIRS), True))
        self.assertEqual((peterson[0].name, peterson[1], peterson[2]),
                         ("peterson-silent.csv", list(PETERSON_PAIRS), True))
        self.assertTrue(run_dataset.call_args_list[2].kwargs["divergences"])

    def test_weak_suite_includes_peterson(self):
        with patch.object(run_suite.sys, "argv", ["run_suite.py", "--weak"]), \
                patch.object(run_suite, "run_dataset") as run_dataset:
            run_suite.main()
        self.assertEqual([call.args[0].stem for call in run_dataset.call_args_list],
                         ["ltbts2", "peterson-silent"])

    def test_suite_collects_both_weak_spectra(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            source = output_dir / "custom.csv"
            source.write_text("0,0,tau\n0,P,implicit-main\n1,Q,implicit-main\n")
            for tool in (*run_suite.TOOLS, *(f"{tool}-divergences" for tool in run_suite.TOOLS)):
                (output_dir / f"custom-{tool}.csv").write_text("status\nok\n")
            with patch.object(run_suite.subprocess, "run") as run, patch("builtins.print"):
                run_suite.run_dataset(source, [("P", "Q")], True, output_dir, divergences=True)
            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual(len(commands), 12)
            self.assertEqual(Path(commands[3][1]).name, "run_equivio.py")
            for command in commands[:3]:
                self.assertNotIn("--divergences", command)
            for command in commands[3:6]:
                self.assertIn("--divergences", command)
            self.assertEqual([Path(command[1]).name for command in commands[3:6]],
                             ["run_equivio.py", "run_mcrl2.py", "run_cadp.py"])
            for command in commands[6:9]:
                self.assertTrue(all("-divergences.csv" not in path for path in command[-2:]))
            for command in commands[9:12]:
                self.assertTrue(all(path.endswith("-divergences.csv") for path in command[-2:]))
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