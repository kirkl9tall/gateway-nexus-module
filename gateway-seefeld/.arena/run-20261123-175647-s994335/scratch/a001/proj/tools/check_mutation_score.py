"""Parse mutmut results and fail if score below threshold."""
import re
import sys


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: check_mutation_score.py <report_file> <threshold>", file=sys.stderr)
        return 2
    path, thr = sys.argv[1], float(sys.argv[2])
    text = open(path, encoding="utf-8").read()
    survived = len(re.findall(r"survived", text, re.I))
    killed   = len(re.findall(r"killed",   text, re.I))
    total    = survived + killed
    if total == 0:
        print("no mutations found — passing (nothing mutated).")
        return 0
    score = 100.0 * killed / total
    print(f"mutation score = {score:.1f}%  ({killed}/{total} killed)")
    if score < thr:
        print(f"FAIL: below threshold {thr:.1f}%", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
