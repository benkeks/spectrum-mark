import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import run_suite
from artifact import benchmarks, cross_checks


class ArtifactBenchmarkTests(unittest.TestCase):
    def test_summary_uses_paper_trimmed_mean_and_preserves_quotients(self):
        rows = [
            {"System": benchmarks.input_path("peterson"), "Spectroscopy time": str(time),
             "States": "100", "Bisim pre-minimized size": "26", "Game moves": "50",
             "enabledness": "2", "trace": "5", "simulation": "8", "Status": "ok"}
            for time in (1000, 9000, 2000, 5000, 3000)
        ]
        result = benchmarks.summarize(rows, ("peterson",), 5, "strong")[0]
        self.assertEqual(result["time (s)"], "3.33")
        self.assertEqual(result["States"], "100")
        self.assertEqual(result["trace"], "5")
        self.assertEqual(result["Status"], "ok")
        rows[-1] = {"System": benchmarks.input_path("peterson"), "Status": "timeout"}
        result = benchmarks.summarize(rows, ("peterson",), 5, "strong")[0]
        self.assertEqual(result["time (s)"], "")
        self.assertEqual(result["Status"], "timeout")

    def test_summary_rejects_changed_quotient_sizes(self):
        row = {"System": benchmarks.input_path("peterson"), "Spectroscopy time": "1",
               "States": "100", "Bisim pre-minimized size": "26", "Game moves": "50",
               "enabledness": "2", "trace": "5", "simulation": "8", "Status": "ok"}
        with self.assertRaisesRegex(ValueError, "Non-deterministic trace"):
            benchmarks.summarize([row, {**row, "trace": "6"}], ("peterson",), 2, "strong")

    def test_measurement_validates_shape_and_isolates_timeouts(self):
        fields = (*benchmarks.COLUMNS, *benchmarks.notions("strong"))
        output = ", ".join(fields) + "\n" + ", ".join(
            (benchmarks.input_path("peterson"), *("1" for _ in fields[1:]))
        ) + "\n"
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "sample.log"
            with patch.object(benchmarks.subprocess, "run",
                              return_value=SimpleNamespace(stdout=output, stderr="")) as run:
                row = benchmarks.measurement(Path("tool.jar"), "strong", "peterson", 500, log)
            self.assertEqual(row["Status"], "ok")
            self.assertIn("-Xmx8g", run.call_args.args[0])
            self.assertEqual(run.call_args.kwargs["timeout"], 500)
            with patch.object(benchmarks.subprocess, "run", side_effect=subprocess.TimeoutExpired(
                ["java"], 1, output=b"partial", stderr=b"diagnostic"
            )):
                row = benchmarks.measurement(Path("tool.jar"), "strong", "peterson", 1, log)
            self.assertEqual(row["Status"], "timeout")
            self.assertIn(b"diagnostic", log.read_bytes())
            with patch.object(benchmarks.subprocess, "run",
                              return_value=SimpleNamespace(stdout=output + output, stderr="")):
                with self.assertRaisesRegex(ValueError, "Unexpected benchmark output"):
                    benchmarks.measurement(Path("tool.jar"), "strong", "peterson", 500, log)

    def test_measurement_keeps_jvm_failure_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "failure.log"
            error = subprocess.CalledProcessError(1, ["java"], output="", stderr="out of memory")
            with patch.object(benchmarks.subprocess, "run", side_effect=error):
                with self.assertRaisesRegex(ValueError, "JVM exited"):
                    benchmarks.measurement(Path("tool.jar"), "strong", "peterson", 500, log)
            self.assertEqual(log.read_text(), "out of memory")


class OptionalCADPTests(unittest.TestCase):
    def test_cadp_absence_is_explicit_and_bad_configuration_is_not_ignored(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(Path, "exists", return_value=False), patch("builtins.print") as printer:
            self.assertIsNone(cross_checks.cadp_directory("auto"))
        self.assertIn("N/A", printer.call_args.args[0])
        with patch.dict(os.environ, {"CADP_BIN": "/nonexistent/cadp/bin.x64"}, clear=True):
            with self.assertRaisesRegex(ValueError, "CADP executable"):
                cross_checks.cadp_directory("auto")
            self.assertIsNone(cross_checks.cadp_directory("off"))

    def test_suite_only_runs_and_compares_selected_tools_in_both_tracks(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            source = output / "input.csv"
            source.write_text("0,0,tau\n0,P,main\n1,Q,main\n")
            for tool in ("equivio", "mcrl2"):
                for suffix in ("", "-divergences"):
                    (output / f"input-{tool}{suffix}.csv").write_text("status\nok\n")
            with patch.object(run_suite.subprocess, "run") as run, \
                    patch.object(run_suite, "record_environment"), patch("builtins.print"):
                run_suite.run_dataset(source, [("P", "Q")], True, output,
                                      tools=("equivio", "mcrl2"))
            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual(len(commands), 6)
            self.assertFalse(any("run_cadp.py" in " ".join(command) for command in commands))
            self.assertEqual(len(list(output.glob("*-vs-*.txt"))), 2)

    def test_suite_rejects_empty_unknown_or_duplicate_tool_selection(self):
        for tools in ((), ("other",), ("equivio", "equivio")):
            with self.subTest(tools=tools), self.assertRaisesRegex(ValueError, "distinct tools"):
                run_suite.run_dataset(Path("input.csv"), [], False, Path("."), tools=tools)

    def test_suite_cli_forwards_tool_selection(self):
        with patch.object(run_suite.sys, "argv", ["run_suite.py", "--tools", "equivio", "mcrl2"]), \
                patch.object(run_suite, "run_dataset") as run:
            run_suite.main()
        self.assertTrue(all(call.kwargs["tools"] == ["equivio", "mcrl2"]
                            for call in run.call_args_list))

    def test_older_cadp_conflicts_are_retained_without_certifying_results(self):
        def validate(path, **kwargs):
            if "-cadp" in path.name:
                raise ValueError(f"Conflicting answers in {path}")

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results"
            source = Path(directory) / "input.csv"
            source.write_text("0,0,tau\n0,P,main\n1,Q,main\n")
            with patch.object(cross_checks, "cadp_directory", return_value=Path("/cadp/bin.x64")), \
                    patch.object(cross_checks, "SUITE_DATASETS", (("input", (("P", "Q"),), True, True),)), \
                    patch.object(cross_checks, "resolve_input", return_value=(source, [("P", "Q")])), \
                    patch.object(cross_checks, "run_dataset"), \
                    patch.object(cross_checks, "validate_report", side_effect=validate), \
                    patch.object(cross_checks.subprocess, "run") as run, \
                    patch.object(cross_checks, "record_environment"), \
                    patch.object(cross_checks, "generate_latex", return_value="incomplete table\n"), \
                    patch("builtins.print"):
                cross_checks.reproduce(output, full=True)
            metadata = json.loads((output / "validation.json").read_text())
            self.assertEqual(metadata["cadp"], "warnings")
            self.assertEqual(len(metadata["warnings"]), 2)
            self.assertEqual(metadata["validated_tools"], ["equivio", "mcrl2"])
            cadp_commands = [call.args[0] for call in run.call_args_list
                             if call.args[0][1].endswith("run_cadp.py")]
            self.assertEqual(len(cadp_commands), 2)
            self.assertTrue(all("--benchmark-performance" in command for command in cadp_commands))
            self.assertIn("--divergences", cadp_commands[1])


if __name__ == "__main__":
    unittest.main()
