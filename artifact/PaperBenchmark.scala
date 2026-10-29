package io.equiv.eqfiddle.artifact

import io.equiv.eqfiddle.algo.AlgorithmLogging
import io.equiv.eqfiddle.hml.HML
import io.equiv.eqfiddle.spectroscopy.{Spectroscopy, StrongSpectroscopy, WeakSpectroscopy}
import io.equiv.eqfiddle.tool.benchmark.VeryLargeTransitionSystems
import io.equiv.eqfiddle.ts.WeakTransitionSystem

object PaperBenchmark {
  def main(args: Array[String]): Unit = {
    require(args.length == 2 && Set("strong", "weak")(args(0)),
      "Usage: PaperBenchmark <strong|weak> <csv-file>")
    val weak = args(0) == "weak"
    val algorithm: WeakTransitionSystem[Int, Symbol, String] =>
        Spectroscopy[Int, Symbol, String, HML.Formula[Symbol]] =
      if (weak) system => new WeakSpectroscopy(system)
      else system => new StrongSpectroscopy(system)
    val notions = if (weak)
      List("weak-enabledness", "weak-trace", "weak-simulation", "sr-branching-bisimulation")
    else List("enabledness", "trace", "simulation")
    AlgorithmLogging.loggingActive = true
    AlgorithmLogging.debugLogActive = false
    println(("System, States, Transitions, Bisim pre-minimization time, Bisim pre-minimized size, Initial pairs, Spectroscopy time, Game positions, Game moves" +: notions).mkString(", "))
    new VeryLargeTransitionSystems(algorithm, Spectroscopy.Config(
      useCleverSpectroscopyGame = true,
      useBranchingSpectroscopyGame = true,
      useSymmetryPruning = true), branchingBisim = weak)
      .listMinimizations(args(1), notions)
  }
}
