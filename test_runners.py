import csv
import io
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

import run_cadp
import run_equivio
import run_mcrl2
import run_suite
import compare_results
from compare_results import load_report, load_results, mcrl2_notion
from csv_to_aut import parse_csv
from example import EDGECASE_PAIRS, PAIRS, PETERSON_PAIRS, WEAK_PAIRS, comparison_runs, resolve_input
from spectrum import WEAK_COMPARISON_SPECTRUM


class RunnerTests(unittest.TestCase):
    def test_performance_schedule_repeats_every_query_in_varying_orders(self):
        pairs = [("P", "Q"), ("A", "B")]
        comparisons = [("bisim", "equivalence"), ("trace", "preorder")]
        ordinary = list(comparison_runs(pairs, comparisons))
        benchmark = list(comparison_runs(pairs, comparisons, benchmark_performance=True))
        expected = {query[1:] for query in ordinary}
        self.assertEqual(len(ordinary), 8)
        self.assertEqual(len(benchmark), 40)
        orders = []
        for run in range(1, 6):
            queries = [query[1:] for query in benchmark if query[0] == run]
            self.assertEqual(len(queries), len(expected))
            self.assertEqual(set(queries), expected)
            orders.append(tuple(queries))
        self.assertEqual(len(set(orders)), 5)
        self.assertEqual(benchmark, list(comparison_runs(pairs, comparisons, True)))

    def test_runners_document_every_performance_run_in_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            source = output_dir / "custom.csv"
            source.write_text("0,1,a\n0,P,implicit-main\n1,Q,implicit-main\n")
            aut_paths = {name: output_dir / f"custom_{name}.aut" for name in ("P", "Q")}
            for module, tool in ((run_equivio, "equivio"), (run_mcrl2, "mcrl2"), (run_cadp, "cadp")):
                for benchmark in (False, True):
                    with self.subTest(tool=tool, benchmark=benchmark), ExitStack() as context:
                        argv = [f"run_{tool}.py", "--csv", str(source), "--output-dir", str(output_dir)]
                        if benchmark:
                            argv.append("--benchmark-performance")
                        context.enter_context(patch.object(module.sys, "argv", argv))
                        context.enter_context(patch.object(module.subprocess, "run"))
                        context.enter_context(patch("builtins.print"))
                        answer = "ready-simulation" if tool == "equivio" else "true"
                        compare = context.enter_context(patch.object(module, "compare", return_value=(0.25, answer, "ok")))
                        if tool == "equivio":
                            context.enter_context(patch.object(module.Path, "glob", return_value=[output_dir / "equivio.jar"]))
                        else:
                            context.enter_context(patch.object(module, "prepare_auts", return_value=aut_paths))
                            bisim = "bisim-bcg-cmp" if tool == "cadp" else "bisim"
                            context.enter_context(patch.object(module, "available_comparisons", return_value=[
                                (bisim, "equivalence"), ("trace", "preorder"),
                            ]))
                            if tool == "cadp":
                                context.enter_context(patch.object(module, "cadp_environment", return_value={}))
                        module.main()
                        report = output_dir / f"custom-{tool}.csv"
                        with report.open(newline="") as result_file:
                            rows = list(csv.DictReader(result_file))
                        repetitions = 5 if benchmark else 1
                        query_count = 2 if tool == "equivio" else 4
                        self.assertEqual(len(rows), query_count * repetitions)
                        self.assertEqual(compare.call_count, len(rows))
                        queries = {}
                        for row in rows:
                            key = (row["left"], row["right"], row.get("equivalence"), row.get("mode"))
                            queries.setdefault(key, []).append(int(row["run"]))
                            self.assertEqual(row["status"], "ok")
                            self.assertEqual(float(row["seconds"]), 0.25)
                        for runs in queries.values():
                            self.assertEqual(sorted(runs), list(range(1, repetitions + 1)))
                        _, costs = load_report(report)
                        self.assertTrue(all(cost.complete for cost in costs.values()))
                        self.assertTrue(all(cost.seconds == (0.25 if tool == "equivio" else 0.5)
                                            for cost in costs.values()))

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

    def test_divergence_frontiers_share_native_notions_but_not_ordinary_notions(self):
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
                         set())
        for native, marked in (
            ("divergence-preserving-branching-bisimulation", "delta-branching-bisimulation"),
            ("divergence-preserving-weak-bisimulation", "delta-weak-bisimulation"),
        ):
            with self.subTest(native=native):
                self.assertTrue(spectrum.dominates(native, marked))
                self.assertTrue(spectrum.dominates(marked, native))
                self.assertEqual(compare_results.notion_family(native), "weak-divergences")

    def test_failures_divergence_is_beside_the_weak_spectrum(self):
        spectrum = WEAK_COMPARISON_SPECTRUM
        self.assertTrue(spectrum.dominates("failures-divergence", "failures-divergence"))
        for notion, _ in spectrum.notions:
            if notion == "failures-divergence":
                continue
            with self.subTest(notion=notion):
                self.assertFalse(spectrum.dominates("failures-divergence", notion))
                self.assertFalse(spectrum.dominates(notion, "failures-divergence"))
        frontier = {"failures-divergence", "delta-sr-branching-bisimulation"}
        self.assertEqual(spectrum.pareto_front(frontier), frontier)
        self.assertEqual(spectrum.unmatched({"failures-divergence"}, {"delta-stable-failure"}),
                         {"failures-divergence"})

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

    def test_comparison_does_not_rank_missing_results_as_different_families(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.csv"
            second = Path(directory) / "second.csv"
            fields = ("left", "right", "equivalence", "mode", "seconds", "equivalent", "status")
            with first.open("w", newline="") as result_file:
                writer = csv.writer(result_file)
                writer.writerow(fields)
                writer.writerow(("P", "Q", "sim", "preorder", 1, "true", "ok"))
            for rows in ([], [("A", "B", "sim", "preorder", 1, "false", "ok")]):
                with second.open("w", newline="") as result_file:
                    writer = csv.writer(result_file)
                    writer.writerow(fields)
                    writer.writerows(rows)
                for reports in ((first, second), (second, first)):
                    with self.subTest(rows=rows, reports=reports):
                        output = io.StringIO()
                        with patch.object(compare_results.sys, "argv", [
                            "compare_results.py", *map(str, reports),
                        ]), patch.object(compare_results.sys, "stdout", output):
                            compare_results.main()
                        self.assertIn("not comparable (missing results)", output.getvalue())
                        self.assertNotIn("different spectrum families", output.getvalue())
                        self.assertNotIn("more precise: first", output.getvalue())
                        self.assertNotIn("more precise: second", output.getvalue())

    def test_cross_tool_checks_false_notions_in_both_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "equivio.csv"
            second = Path(directory) / "native.csv"
            with first.open("w", newline="") as result_file:
                writer = csv.writer(result_file)
                writer.writerow(("left", "right", "spectrum", "seconds", "preorders", "status"))
                writer.writerow(("P", "Q", "strong", 1, "ready-simulation", "ok"))
            with second.open("w", newline="") as result_file:
                writer = csv.writer(result_file)
                writer.writerow(("left", "right", "equivalence", "mode", "seconds", "equivalent", "status"))
                writer.writerows([
                    ("P", "Q", "trace", "equivalence", 1, "false", "ok"),
                    ("P", "Q", "trace", "preorder", 1, "false", "ok"),
                    ("P", "Q", "impossible-futures", "preorder", 1, "true", "ok"),
                ])
            output = io.StringIO()
            with patch.object(compare_results.sys, "argv", ["compare_results.py", str(first), str(second)]), \
                    patch.object(compare_results.sys, "stdout", output):
                compare_results.main()
            self.assertIn("INCONSISTENCY: first reports impossible-future (preorder) false", output.getvalue())
            self.assertIn("INCONSISTENCY: second reports trace (preorder) false", output.getvalue())

    def test_divergence_reports_expose_disagreements_in_both_directions(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "equivio.csv"
            second = Path(directory) / "native.csv"
            with first.open("w", newline="") as result_file:
                writer = csv.writer(result_file)
                writer.writerow(("left", "right", "spectrum", "seconds", "preorders", "status"))
                writer.writerows([
                    ("P", "Q", "weak-divergences", 1, "sr-delay-bisimulation", "ok"),
                    ("A", "B", "weak-divergences", 1, "weak-bisimulation", "ok"),
                ])
            with second.open("w", newline="") as result_file:
                writer = csv.writer(result_file)
                writer.writerow(("left", "right", "equivalence", "mode", "seconds", "equivalent", "status"))
                writer.writerows([
                    ("P", "Q", "dpweak-bisim", "equivalence", 1, "false", "ok"),
                    ("P", "Q", "failures-divergence", "preorder", 1, "false", "ok"),
                    ("A", "B", "dpbranching-bisim", "equivalence", 1, "true", "ok"),
                ])
            output = io.StringIO()
            with patch.object(compare_results.sys, "argv", ["compare_results.py", str(first), str(second)]), \
                    patch.object(compare_results.sys, "stdout", output):
                compare_results.main()
            self.assertIn("INCONSISTENCY: second reports divergence-preserving-weak-bisimulation "
                          "(equivalence) false", output.getvalue())
            self.assertIn("INCONSISTENCY: first reports delta-branching-bisimulation "
                          "(equivalence) false", output.getvalue())
            self.assertNotIn("INCONSISTENCY: second reports failures-divergence "
                          "(preorder) false", output.getvalue())
            self.assertNotIn("not comparable", output.getvalue())
            self.assertIn("under Spectrum II", output.getvalue())

    def test_consistency_checks_only_sound_relation_implications(self):
        cases = [
            ({("strong", "trace", "equivalence"): False},
             {("strong", "ready-simulation", "preorder"): True}, False),
            ({("strong", "trace", "preorder"): False},
             {("strong", "ready-simulation", "equivalence"): True}, True),
            ({("strong", "trace", "equivalence"): False},
             {("strong", "ready-simulation", "equivalence"): True}, True),
            ({("strong", "trace", "preorder"): None},
             {("strong", "ready-simulation", "preorder"): True}, False),
            ({("strong", "trace", "preorder"): False},
             {("strong", "ready-simulation", "preorder"): None}, False),
            ({}, {("strong", "ready-simulation", "preorder"): True}, False),
            ({("weak", "weak-trace", "preorder"): False},
             {("weak-divergences", "delta-branching-bisimulation", "equivalence"): True}, False),
            ({("weak-divergences", "divergence-preserving-branching-bisimulation", "equivalence"): False},
             {("weak-divergences", "delta-branching-bisimulation", "equivalence"): True}, True),
            ({("weak-divergences", "delta-weak-bisimulation", "equivalence"): False},
             {("weak-divergences", "divergence-preserving-branching-bisimulation", "equivalence"): True}, True),
            ({("weak-divergences", "failures-divergence", "preorder"): False},
             {("weak-divergences", "delta-sr-branching-bisimulation", "equivalence"): True}, False),
            ({("weak-divergences", "delta-weak-trace", "preorder"): False},
             {("weak-divergences", "failures-divergence", "equivalence"): True}, False),
            ({("weak-divergences", "delta-stable-failure", "equivalence"): False},
             {("weak-divergences", "failures-divergence", "equivalence"): True}, False),
            ({("weak-divergences", "failures-divergence", "preorder"): False},
             {("weak-divergences", "failures-divergence", "equivalence"): True}, True),
            ({("weak-divergences", "delta-weak-trace", "preorder"): False},
             {("weak-divergences", "delta-branching-bisimulation", "equivalence"): True}, True),
            ({("weak-divergences", "divergence-preserving-branching-bisimulation", "equivalence"): False},
             {("weak-divergences", "divergence-preserving-branching-bisimulation", "equivalence"): True}, True),
            ({("weak", "coupled-simulation", "preorder"): False},
             {("weak", "coupled-simulation", "preorder"): True}, True),
        ]
        for decisions, other, expected in cases:
            with self.subTest(decisions=decisions, other=other):
                self.assertEqual(bool(compare_results.find_inconsistencies(decisions, other)), expected)

    def test_equivio_decisions_reconstruct_closure_and_mutual_preorders(self):
        cases = [
            ("strong", "ready-simulation", None, "trace", None, None),
            ("strong", "ready-simulation", "", "trace", None, False),
            ("strong", "ready-simulation", "ready-simulation", "trace", None, True),
            ("weak", "branching-bisimulation", None, "weak-trace", "weak-bisimulation", None),
            ("weak-divergences", "branching-bisimulation", None,
             "delta-weak-trace", "delta-weak-bisimulation", None),
        ]
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "equivio.csv"
            for spectrum, frontier, reverse, trace, bisimulation, equivalent in cases:
                with self.subTest(spectrum=spectrum, reverse=reverse):
                    with report.open("w", newline="") as result_file:
                        writer = csv.writer(result_file)
                        writer.writerow(("left", "right", "spectrum", "seconds", "preorders", "status"))
                        writer.writerow(("P", "Q", spectrum, 1, frontier, "ok"))
                        if reverse is not None:
                            writer.writerow(("Q", "P", spectrum, 1, reverse, "ok"))
                    _, _, decisions = compare_results.load_report_details(report)
                    pair = decisions[("P", "Q")]
                    self.assertIs(pair[(spectrum, trace, "preorder")], True)
                    self.assertIs(pair.get((spectrum, trace, "equivalence")), equivalent)
                    if bisimulation is not None:
                        self.assertIs(pair[(spectrum, bisimulation, "equivalence")], True)
                        self.assertNotIn((spectrum, bisimulation, "preorder"), pair)

    def test_empty_frontier_records_false_decisions_but_failures_do_not(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "equivio.csv"
            with report.open("w", newline="") as result_file:
                writer = csv.writer(result_file)
                writer.writerow(("left", "right", "spectrum", "seconds", "preorders", "status"))
                writer.writerow(("P", "Q", "strong", 1, "", "ok"))
                writer.writerow(("Q", "P", "strong", 30, "", "timeout"))
            _, _, decisions = compare_results.load_report_details(report)
            self.assertTrue(all(answer is False for answer in decisions[("P", "Q")].values()))
            self.assertTrue(all(answer is None for answer in decisions[("Q", "P")].values()))

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

    def test_repeated_native_queries_use_fastest_algorithm_median(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "native.csv"
            with report.open("w", newline="") as result_file:
                writer = csv.writer(result_file)
                writer.writerow(("left", "right", "equivalence", "mode", "seconds", "equivalent", "status", "run"))
                for algorithm, samples in (
                    ("bisim", [0.01, 9, 9, 10, 11]),
                    ("bisim-gv", [3, 2, 4, 3, 2]),
                ):
                    for run, seconds in enumerate(samples, 1):
                        writer.writerow(("P", "Q", algorithm, "equivalence", seconds, "false", "ok", run))
            results, costs, decisions = compare_results.load_report_details(report)
            self.assertEqual(results[("P", "Q")], (set(), "ok"))
            cost = costs[("P", "Q")]
            self.assertEqual((cost.supported, cost.decided, cost.seconds), (1, 1, 3))
            self.assertIs(decisions[("P", "Q")][("strong", "bisimulation", "equivalence")], False)

    def test_repeated_equivio_queries_use_median_and_retain_decisions(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "equivio.csv"
            for family, frontier, trace, count in (
                ("strong", "ready-simulation", "trace", 13),
                ("weak-divergences", "sr-delay-bisimulation", "delta-weak-trace", 26),
            ):
                with self.subTest(family=family):
                    with report.open("w", newline="") as result_file:
                        writer = csv.writer(result_file)
                        writer.writerow(("left", "right", "spectrum", "seconds", "preorders", "status", "run"))
                        for run, seconds in enumerate([0.01, 9, 2, 4, 3], 1):
                            writer.writerow(("P", "Q", family, seconds, frontier, "ok", run))
                    _, costs, decisions = compare_results.load_report_details(report)
                    cost = costs[("P", "Q")]
                    self.assertEqual((cost.supported, cost.decided, cost.seconds), (count, count, 3))
                    self.assertIs(decisions[("P", "Q")][(family, trace, "preorder")], True)

    def test_repeated_query_conflicts_are_not_timed_as_decisions(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "results.csv"
            cases = [
                (("left", "right", "equivalence", "mode", "seconds", "equivalent", "status", "run"), [
                    ("P", "Q", "sim", "preorder", 1, "true", "ok", 1),
                    ("P", "Q", "sim", "preorder", 2, "false", "ok", 2),
                    ("P", "Q", "sim", "preorder", 30, "", "timeout", 3),
                ]),
                (("left", "right", "spectrum", "seconds", "preorders", "status", "run"), [
                    ("P", "Q", "strong", 1, "trace", "ok", 1),
                    ("P", "Q", "strong", 2, "", "ok", 2),
                    ("P", "Q", "strong", 30, "", "timeout", 3),
                ]),
            ]
            for fields, rows in cases:
                with self.subTest(fields=fields):
                    with report.open("w", newline="") as result_file:
                        writer = csv.writer(result_file)
                        writer.writerow(fields)
                        writer.writerows(rows)
                    with patch.object(compare_results.sys, "stderr", io.StringIO()):
                        results, costs, decisions = compare_results.load_report_details(report)
                    self.assertEqual(results[("P", "Q")], (set(), "conflict"))
                    self.assertEqual(costs[("P", "Q")].decided, 0)
                    self.assertEqual(costs[("P", "Q")].seconds, 0)
                    self.assertTrue(all(answer is None for answer in decisions[("P", "Q")].values()))

    def test_repeated_query_failures_are_excluded_from_median_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "results.csv"
            for native in (False, True):
                with self.subTest(native=native):
                    with report.open("w", newline="") as result_file:
                        writer = csv.writer(result_file)
                        writer.writerow(("left", "right", "equivalence", "mode", "seconds", "equivalent", "status", "run")
                                        if native else ("left", "right", "spectrum", "seconds", "preorders", "status", "run"))
                        for run, (seconds, status) in enumerate([(1, "ok"), (3, "ok"), (5, "ok"),
                                                                (30, "timeout"), (30, "error")], 1):
                            writer.writerow(("P", "Q", "sim", "preorder", seconds,
                                             "false" if status == "ok" else "", status, run)
                                            if native else ("P", "Q", "strong", seconds,
                                                            "trace" if status == "ok" else "", status, run))
                    results, costs, decisions = compare_results.load_report_details(report)
                    self.assertEqual(results[("P", "Q")][1], "timeout")
                    self.assertEqual(costs[("P", "Q")].seconds, 3)
                    self.assertTrue(costs[("P", "Q")].complete)
                    key = ("strong", "simulation" if native else "trace", "preorder")
                    self.assertIs(decisions[("P", "Q")][key], not native)

    def test_repeated_query_run_ids_are_valid_and_unique(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "results.csv"
            for native in (False, True):
                for runs in ([0], [6], ["invalid"], [""], [1, 1]):
                    with self.subTest(native=native, runs=runs):
                        with report.open("w", newline="") as result_file:
                            writer = csv.writer(result_file)
                            writer.writerow(("left", "right", "equivalence", "mode", "seconds", "equivalent", "status", "run")
                                            if native else ("left", "right", "spectrum", "seconds", "preorders", "status", "run"))
                            for run in runs:
                                writer.writerow(("P", "Q", "sim", "preorder", 1, "true", "ok", run)
                                                if native else ("P", "Q", "strong", 1, "trace", "ok", run))
                        with self.assertRaises(ValueError):
                            load_report(report)

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
                results, costs, decisions = compare_results.load_report_details(report)
            self.assertIn("Conflicting algorithm results", errors.getvalue())
            self.assertEqual(results, {("P", "Q"): ({"weak-trace"}, "conflict")})
            self.assertIsNone(decisions[("P", "Q")][("weak", "branching-bisimulation", "equivalence")])
            self.assertIs(decisions[("P", "Q")][("weak", "weak-trace", "preorder")], True)
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
            _, costs, decisions = compare_results.load_report_details(report)
            cost = costs[("P", "Q")]
            self.assertEqual((cost.supported, cost.decided, cost.seconds), (2, 1, 2))
            self.assertFalse(cost.complete)
            self.assertIsNone(decisions[("P", "Q")][("weak", "weak-trace", "preorder")])
            self.assertIs(decisions[("P", "Q")][("weak", "weak-trace", "equivalence")], False)

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

    def test_edgecase_dataset_models_and_curated_pairs(self):
        source = Path(__file__).resolve().parent / "examples" / "edgecases.csv"
        transitions, meta = parse_csv(source)
        names = {entry["state_name"]: entry["state_id"] for entry in meta}
        self.assertEqual(resolve_input(source, weak=True)[1], list(EDGECASE_PAIRS))
        self.assertEqual(len(EDGECASE_PAIRS), 16)
        self.assertEqual(set(names), {name for pair in EDGECASE_PAIRS for name in pair})
        edges = {(row["src"], row["tar"], row["action"]) for row in transitions}
        self.assertEqual({edge for edge in edges if 90 <= edge[0] <= 93}, {
            (90, 90, "tau"), (90, 93, "a"), (90, 92, "tau"),
            (91, 93, "a"), (91, 92, "tau"), (92, 92, "tau"),
        })
        self.assertEqual((names["DivergenceP"], names["DivergenceQ"]), (90, 91))
        self.assertEqual({edge for edge in edges if 100 <= edge[0] <= 104}, {
            (100, 101, "tau"), (101, 102, "tau"), (102, 101, "tau"),
            (101, 103, "tau"), (103, 100, "tau"), (100, 104, "a"),
        })
        self.assertEqual({edge for edge in edges if edge[0] == names["NoDeadlockLoop"]},
                         {(110, 110, "tau")})
        components = [range(0, 6), range(10, 23), range(30, 38), range(40, 46),
                      range(50, 53), range(60, 63), range(70, 73), range(80, 83),
                      range(90, 94), range(100, 105), range(110, 111)]
        owners = {state: component for component, states in enumerate(components) for state in states}
        for source_id, target_id, _ in edges:
            self.assertEqual(owners[source_id], owners[target_id])

    def test_suite_defaults_to_all_curated_csvs(self):
        with patch.object(run_suite.sys, "argv", ["run_suite.py"]), \
                patch.object(run_suite, "run_dataset") as run_dataset:
            run_suite.main()
        self.assertEqual(run_dataset.call_count, 4)
        strong, weak, peterson, edgecases = [call.args for call in run_dataset.call_args_list]
        self.assertEqual((strong[0].name, strong[1], strong[2]), ("ltbts1.csv", list(PAIRS), False))
        self.assertEqual((weak[0].name, weak[1], weak[2]), ("ltbts2.csv", list(WEAK_PAIRS), True))
        self.assertEqual((peterson[0].name, peterson[1], peterson[2]),
                         ("peterson-silent.csv", list(PETERSON_PAIRS), True))
        self.assertEqual((edgecases[0].name, edgecases[1], edgecases[2]),
                 ("edgecases.csv", list(EDGECASE_PAIRS), True))
        self.assertFalse(run_dataset.call_args_list[0].kwargs["divergences"])
        self.assertTrue(run_dataset.call_args_list[1].kwargs["divergences"])
        self.assertTrue(run_dataset.call_args_list[2].kwargs["divergences"])
        self.assertTrue(run_dataset.call_args_list[3].kwargs["divergences"])

    def test_weak_suite_includes_peterson(self):
        for extra_options in ([], ["--divergence"], ["--divergences"], ["--benchmark-performance"]):
            with self.subTest(extra_options=extra_options):
                with patch.object(run_suite.sys, "argv", ["run_suite.py", "--weak", *extra_options]), \
                        patch.object(run_suite, "run_dataset") as run_dataset:
                    run_suite.main()
                self.assertEqual([call.args[0].stem for call in run_dataset.call_args_list],
                                 ["ltbts2", "peterson-silent", "edgecases"])
                self.assertTrue(all(call.args[2] for call in run_dataset.call_args_list))
                self.assertTrue(all(call.kwargs["divergences"] for call in run_dataset.call_args_list))
                self.assertTrue(all(call.kwargs["benchmark_performance"] == ("--benchmark-performance" in extra_options)
                                    for call in run_dataset.call_args_list))

    def test_custom_weak_suite_includes_divergence_by_default(self):
        for extra_options in ([], ["--divergences"]):
            with self.subTest(extra_options=extra_options):
                with patch.object(run_suite.sys, "argv", [
                    "run_suite.py", "--csv", "examples/ltbts2.csv", "--weak", "--pair", "P55", "P56",
                    *extra_options,
                ]), patch.object(run_suite, "run_dataset") as run_dataset:
                    run_suite.main()
                self.assertTrue(run_dataset.call_args.kwargs["divergences"])

    def test_suite_collects_both_weak_spectra(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            source = output_dir / "custom.csv"
            source.write_text("0,0,tau\n0,P,implicit-main\n1,Q,implicit-main\n")
            for tool in (*run_suite.TOOLS, *(f"{tool}-divergences" for tool in run_suite.TOOLS)):
                (output_dir / f"custom-{tool}.csv").write_text("status\nok\n")
            with patch.object(run_suite.subprocess, "run") as run, patch("builtins.print"):
                run_suite.run_dataset(source, [("P", "Q")], True, output_dir, benchmark_performance=True)
            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual(len(commands), 12)
            self.assertEqual(Path(commands[3][1]).name, "run_equivio.py")
            self.assertTrue(all("--benchmark-performance" in command for command in commands[:6]))
            self.assertTrue(all("--benchmark-performance" not in command for command in commands[6:]))
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
                run_suite.run_dataset(source, [("P", "Q")], True, output_dir, Path("/cadp/bin.x64"),
                                      divergences=False)
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