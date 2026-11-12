"""Analyses the EarRepair CSVs. Standard library only.

    python analysis/analyze.py data/            # folder with earrepair_*_trials.csv and *_blocks.csv
    python analysis/analyze.py --selftest       # checks this script on made-up numbers
    python analysis/analyze.py data/ --latex paper/results.tex   # also writes the paper's numbers

Decided before seeing data, so the pilot cannot be tuned to its own results:
  * Test trials only. Interrupted attempts are dropped. A timeout counts as an error.
  * Primary time measure: rt_from_list_ms, from the start of the list to the finger landing,
    on correct trials where the target was present. This includes hearing the list.
  * Each person gets one value per condition (the median). Tests compare those values.
  * Primary comparisons: spatial vs numbered (is it better than today's approach?) and
    spatial vs plain (is space itself doing the work?). Holm-corrected within each measure.
  * Tests are exact sign-flip permutation tests on paired differences, with bootstrap 95% CIs.
    With 10-15 people, treat all of this as preliminary effect sizes, not proof.

Measures: time, accuracy, replays, raw TLX, walking speed as a share of baseline (walking only).
"""
import csv
import glob
import itertools
import math
import os
import random
import statistics
import sys

CONDITIONS = ("numbered", "plain", "spatial")
PAIRS = (("spatial", "numbered"), ("spatial", "plain"))
TLX = ("mental", "physical", "temporal", "performance", "effort", "frustration")


def read(pattern):
    rows = []
    for path in sorted(glob.glob(pattern)):
        with open(path, encoding="utf-8", newline="") as f:
            rows += list(csv.DictReader(f))
    return rows


def paired_test(a, b):
    """Exact two-sided sign-flip test on the mean difference (Monte Carlo above 16 people)."""
    d = [x - y for x, y in zip(a, b)]
    observed = abs(sum(d))
    if len(d) <= 16:
        signs = itertools.product((1, -1), repeat=len(d))
        count = total = 0
        for s in signs:
            total += 1
            count += abs(sum(x * y for x, y in zip(s, d))) >= observed - 1e-9
    else:
        rng = random.Random(1)
        total = 100000
        count = sum(abs(sum(x * rng.choice((1, -1)) for x in d)) >= observed - 1e-9 for _ in range(total))
    return count / total


def bootstrap_ci(d, seed=1):
    rng = random.Random(seed)
    means = sorted(statistics.mean(rng.choices(d, k=len(d))) for _ in range(10000))
    return means[249], means[9749]


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    out, running = [0] * len(ps), 0
    for rank, i in enumerate(order):
        running = max(running, min(1, ps[i] * (len(ps) - rank)))
        out[i] = running
    return out


LATEX = {}   # measure key -> numbers for the paper, filled by report(..., key=...)


def report(name, table, unit="", scale=1, digits=2, key=None):
    """table: {pid: {condition: value}}. Only people with all three conditions are compared."""
    people = sorted(p for p, v in table.items() if all(c in v for c in CONDITIONS))
    print(f"\n{name}  (n={len(people)})")
    if len(people) < 2:
        print("  not enough people to compare")
        return
    store = {"n": len(people), "digits": digits, "cond": {}, "pairs": {}}
    for c in CONDITIONS:
        values = [table[p][c] * scale for p in people]
        store["cond"][c] = (statistics.mean(values), statistics.stdev(values))
        print(f"  {c:9s} mean {statistics.mean(values):.{digits}f}{unit}  sd {statistics.stdev(values):.{digits}f}"
              f"  median {statistics.median(values):.{digits}f}")
    results = []
    for x, y in PAIRS:
        a = [table[p][x] * scale for p in people]
        b = [table[p][y] * scale for p in people]
        d = [i - j for i, j in zip(a, b)]
        sd = statistics.stdev(d)
        results.append((x, y, statistics.mean(d), bootstrap_ci(d), statistics.mean(d) / sd if sd else 0.0,
                        paired_test(a, b)))
    adjusted = holm([r[5] for r in results])
    for (x, y, mean, ci, dz, p), padj in zip(results, adjusted):
        store["pairs"][y] = (mean, ci, dz, padj)
        print(f"  {x} - {y}: {mean:+.{digits}f}{unit} [95% CI {ci[0]:+.{digits}f}, {ci[1]:+.{digits}f}]"
              f"  dz {dz:+.2f}  p {p:.4f}  Holm p {padj:.4f}")
    if key:
        LATEX[key] = store


def write_latex(path, n_people):
    """Macros for the paper. Names: \\res<Measure><Cond> = mean, \\res<Measure>Sd<Cond> = sd,
    \\res<Measure>Vs<Numbered|Plain> = spatial minus that condition, \\res<Measure>Ci<...> = '[lo, hi]',
    \\res<Measure>P<...> = Holm p."""
    cap = {"numbered": "Numbered", "plain": "Plain", "spatial": "Spatial"}
    lines = ["% Written by analysis/analyze.py. Do not edit by hand: rerun the analysis.",
             "\\haveresultstrue", f"\\newcommand{{\\resN}}{{{n_people}}}"]
    for key, s in sorted(LATEX.items()):
        d = s["digits"]
        lines.append(f"\\newcommand{{\\res{key}N}}{{{s['n']}}}")
        for c, (mean, sd) in s["cond"].items():
            lines.append(f"\\newcommand{{\\res{key}{cap[c]}}}{{{mean:.{d}f}}}")
            lines.append(f"\\newcommand{{\\res{key}Sd{cap[c]}}}{{{sd:.{d}f}}}")
        for other, (mean, ci, dz, padj) in s["pairs"].items():
            lines.append(f"\\newcommand{{\\res{key}Vs{cap[other]}}}{{${mean:+.{d}f}$}}")
            lines.append(f"\\newcommand{{\\res{key}Ci{cap[other]}}}{{[${ci[0]:+.{d}f}$, ${ci[1]:+.{d}f}$]}}")
            lines.append(f"\\newcommand{{\\res{key}P{cap[other]}}}{{{padj:.3f}}}")
            lines.append(f"\\newcommand{{\\res{key}Dz{cap[other]}}}{{${dz:+.2f}$}}")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nwrote {len(lines)} lines of LaTeX macros -> {path}")


def per_person(rows, value):
    table = {}
    for pid in {r["pid"] for r in rows}:
        for c in CONDITIONS:
            mine = [r for r in rows if r["pid"] == pid and r["condition"] == c]
            result = value(mine)
            if result is not None:
                table.setdefault(pid, {})[c] = result
    return table


def median_rt(rows):
    values = [float(r["rt_from_list_ms"]) for r in rows if r["correct"] == "1" and r["absent"] == "0"]
    return statistics.median(values) if values else None


def share(rows, test):
    return sum(test(r) for r in rows) / len(rows) if rows else None


def analyse(trials, blocks):
    test = [r for r in trials if r["phase"] == "test" and r["status"] != "interrupted"]
    pids = sorted({r["pid"] for r in test})
    print(f"{len(pids)} participants, {len(test)} trials, "
          f"{sum(r['status'] == 'timeout' for r in test)} timeouts, "
          f"{sum(r['status'] == 'interrupted' for r in trials)} interrupted attempts dropped")
    print("contexts:", sorted({r['context'] for r in test}))
    for pid in pids:
        n = sum(r["pid"] == pid for r in test)
        if n != 45:
            print(f"  WARNING {pid}: {n} trials instead of 45")
    delays = [float(r["delay_ms"]) for r in test if r["delay_ms"]]
    if delays:
        print(f"reported output delay: median {statistics.median(delays):.0f} ms, max {max(delays):.0f} ms")

    report("Time to answer, from list start (correct, target present)", per_person(test, median_rt), " s", 0.001,
           key="Time")
    report("  same, confusable names only",
           per_person([r for r in test if r["similarity"] == "confusable"], median_rt), " s", 0.001)
    report("  same, distinct names only",
           per_person([r for r in test if r["similarity"] == "distinct"], median_rt), " s", 0.001)
    report("Accuracy, all trials", per_person(test, lambda rs: share(rs, lambda r: r["correct"] == "1")), "%", 100, 1,
           key="Acc")
    report("  accuracy, confusable names only",
           per_person([r for r in test if r["similarity"] == "confusable"],
                      lambda rs: share(rs, lambda r: r["correct"] == "1")), "%", 100, 1)
    report("  accuracy, 'none of these' trials",
           per_person([r for r in test if r["absent"] == "1"],
                      lambda rs: share(rs, lambda r: r["correct"] == "1")), "%", 100, 1)
    report("Trials with a replay", per_person(test, lambda rs: share(rs, lambda r: int(r["replays"]) > 0)), "%", 100, 1)
    report("Answered before the list ended",
           per_person([r for r in test if r["status"] == "ok"],
                      lambda rs: share(rs, lambda r: float(r["rt_from_list_end_ms"]) < 0)), "%", 100, 1)

    # Which wrong answers? In the spatial block, are errors next to the target or across the head?
    wrong = [r for r in test if r["status"] == "ok" and r["correct"] == "0"]
    print(f"\nErrors by requested position -> chosen position ({len(wrong)} wrong swipes)")
    for c in CONDITIONS:
        pairs = {}
        for r in wrong:
            if r["condition"] == c:
                key = f"{r['target_pos']}->{r['chosen_pos']}"
                pairs[key] = pairs.get(key, 0) + 1
        print(f"  {c:9s} {dict(sorted(pairs.items())) or 'none'}")

    def table(field):
        out = {}
        for r in blocks:
            if r.get(field) not in ("", None):
                out.setdefault(r["pid"], {})[r["condition"]] = float(r[field])
        return out

    raw = {}
    for r in blocks:
        raw.setdefault(r["pid"], {})[r["condition"]] = statistics.mean(float(r["tlx_" + k]) for k in TLX)
    report("Raw TLX, mean of 6 scales (0-100, lower is better)", raw, "", 1, 1, key="Tlx")
    for key in ("mental", "frustration"):
        report(f"  TLX {key}", table("tlx_" + key), "", 1, 1)

    speed = {}
    for r in blocks:
        if r.get("laps") and float(r["duration_s"]) > 0:
            walked = float(r["laps"]) * float(r["lap_m"]) / float(r["duration_s"])
            baseline = float(r["lap_m"]) / float(r["baseline_lap_s"])
            speed.setdefault(r["pid"], {})[r["condition"]] = walked / baseline
    if speed:
        report("Walking speed, share of baseline", speed, "%", 100, 1, key="Walk")
    return len(pids)

    people = {r["pid"]: r for r in blocks if r.get("pref_best")}
    print("\nPreference (people):")
    for c in CONDITIONS:
        print(f"  {c:9s} best {sum(r['pref_best'] == c for r in people.values())}"
              f"  worst {sum(r['pref_worst'] == c for r in people.values())}")
    comments = sorted({(r["pid"], r["comments"]) for r in blocks if r.get("comments")})
    if comments:
        print("\nComments:")
        for pid, text in comments:
            print(f"  {pid}: {text}")


def selftest():
    """Known answers. Nothing here is written to disk or resembles study data."""
    assert abs(paired_test([1, 2, 3, 4], [0, 0, 0, 0]) - 2 / 16) < 1e-9     # only all-plus / all-minus reach 10
    assert paired_test([1, 1, 1], [1, 1, 1]) == 1
    assert holm([0.01, 0.04]) == [0.02, 0.04]
    assert holm([0.04, 0.03]) == [0.06, 0.06]
    lo, hi = bootstrap_ci([1.0] * 10)
    assert lo == hi == 1.0
    assert median_rt([{"correct": "1", "absent": "0", "rt_from_list_ms": "100"},
                      {"correct": "0", "absent": "0", "rt_from_list_ms": "900"},
                      {"correct": "1", "absent": "1", "rt_from_list_ms": "900"}]) == 100
    print("selftest passed")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if sys.argv[1] == "--selftest":
        selftest()
    else:
        folder = sys.argv[1]
        trials = read(os.path.join(folder, "*_trials.csv"))
        blocks = read(os.path.join(folder, "*_blocks.csv"))
        if not trials:
            sys.exit(f"no *_trials.csv files in {folder}")
        n_people = analyse(trials, blocks)
        if "--latex" in sys.argv:
            write_latex(sys.argv[sys.argv.index("--latex") + 1], n_people)
