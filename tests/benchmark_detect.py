"""
Benchmark for the transformation detector.

Each row is (before, after, correct_concept_id) written the way a real
Math 1B student would type it. This measures top-1 and top-3 accuracy.

THIS FILE IS THE PROJECT'S EVIDENCE. Grow it as real student steps come in.
"""

import sys, os
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mathcore import parse_student
from mathcore.detect import detect_transformation

CASES = [
    # --- distributive property ---
    ("3(x + 2)",            "3x + 6",                 "distributive-property"),
    ("4(y + 5)",            "4y + 20",                "distributive-property"),
    ("x(x + 7)",            "x^2 + 7x",               "distributive-property"),
    ("(x + 1)(x + 3)",      "x^2 + 4x + 3",           "distributive-property"),
    ("(x + 2)^2",           "x^2 + 4x + 4",           "distributive-property"),
    ("-2(x - 5)",           "-2x + 10",               "distributive-property"),

    # --- GCF ---
    ("6x + 9",              "3(2x + 3)",              "gcf-factoring"),
    ("5x + 5",              "5(x + 1)",               "gcf-factoring"),
    ("4x^2 + 8x",           "4x(x + 2)",              "gcf-factoring"),
    ("12y - 18",            "6(2y - 3)",              "gcf-factoring"),

    # --- factoring simple quadratics ---
    ("x^2 + 7x + 12",       "(x + 3)(x + 4)",         "factoring-quadratic-simple"),
    ("x^2 - 5x + 6",        "(x - 2)(x - 3)",         "factoring-quadratic-simple"),
    ("x^2 + x - 6",         "(x + 3)(x - 2)",         "factoring-quadratic-simple"),
    ("x^2 - 2x - 8",        "(x - 4)(x + 2)",         "factoring-quadratic-simple"),

    # --- difference of squares ---
    ("x^2 - 25",            "(x + 5)(x - 5)",         "difference-of-squares"),
    ("x^2 - 9",             "(x + 3)(x - 3)",         "difference-of-squares"),
    ("4x^2 - 49",           "(2x + 7)(2x - 7)",       "difference-of-squares"),
    ("x^2 - 1",             "(x + 1)(x - 1)",         "difference-of-squares"),

    # --- grouping ---
    ("2x + 2y + 3*x*z + 3*y*z", "(2 + 3z)(x + y)",    "factoring-by-grouping"),
    ("x^3 + x^2 + 2x + 2",  "(x^2 + 2)(x + 1)",       "factoring-by-grouping"),

    # --- log definition ---
    ("log_3(81)",           "4",                      "log-definition"),
    ("log_2(8)",            "3",                      "log-definition"),
    ("log(1000)",           "3",                      "log-definition"),

    # --- log product / quotient ---
    ("log_2(8*4)",          "log_2(8) + log_2(4)",    "log-product-rule"),
    ("log(x*y)",            "log(x) + log(y)",        "log-product-rule"),
    ("log_2(16/2)",         "log_2(16) - log_2(2)",   "log-quotient-rule"),
    ("log(x/y)",            "log(x) - log(y)",        "log-quotient-rule"),

    # --- log power ---
    ("log_5(25^3)",         "3*log_5(25)",            "log-power-rule"),
    ("log(x^4)",            "4*log(x)",               "log-power-rule"),
    ("ln(x^2)",             "2*ln(x)",                "log-power-rule"),

    # --- solving exponential ---
    ("2^x",                 "log(7)/log(2)",          "solving-exponential-equations"),
    ("3^x",                 "log(20)/log(3)",         "solving-exponential-equations"),
    ("5^(x+1)",             "log(30)/log(5)",         "solving-exponential-equations"),

    # --- exponent rules ---
    ("x^3 * x^4",           "x^7",                    "exponent-rules"),
    ("y^2 * y^5",           "y^7",                    "exponent-rules"),
    ("(x^2)^3",             "x^6",                    "exponent-rules"),
    ("x^7 / x^2",           "x^5",                    "exponent-rules"),

    # --- rational ---
    ("(x^2 - 9)/(x + 3)",   "x - 3",                  "simplify-rational"),
    ("(x^2 - 4)/(x - 2)",   "x + 2",                  "simplify-rational"),
    ("(6x^2)/(3x)",         "2x",                     "simplify-rational"),

    # --- trig ---
    ("sin(t)^2 + cos(t)^2", "1",                      "pythagorean-identity"),
    ("1 - sin(t)^2",        "cos(t)^2",               "pythagorean-identity"),
    ("1 - cos(x)^2",        "sin(x)^2",               "pythagorean-identity"),

    # --- absolute value ---
    ("|x - 1|",             "3",                      "absolute-value-equations"),
    ("|2x + 4|",            "10",                     "absolute-value-equations"),
]


def run(verbose=True):
    top1 = top3 = total = 0
    misses = []
    per_concept = defaultdict(lambda: [0, 0])   # concept -> [correct, total]

    for before_s, after_s, expected in CASES:
        total += 1
        per_concept[expected][1] += 1
        try:
            # structural=True keeps the SHAPE the student typed, which is
            # what tells us which idea they were reaching for.
            b = parse_student(before_s, structural=True)
            a = parse_student(after_s, structural=True)
        except Exception as exc:
            misses.append((before_s, after_s, expected, f"PARSE FAIL: {exc}"))
            continue

        hits = detect_transformation(b, a)
        ids = [h.concept_id for h in hits]

        if ids and ids[0] == expected:
            top1 += 1
            top3 += 1
            per_concept[expected][0] += 1
        elif expected in ids:
            top3 += 1
            misses.append((before_s, after_s, expected, f"ranked #{ids.index(expected)+1}: {ids}"))
        else:
            misses.append((before_s, after_s, expected, f"got {ids or 'nothing'}"))

    print("=" * 74)
    print(f"BENCHMARK — {total} labeled student steps")
    print("=" * 74)
    print(f"  Top-1 accuracy: {top1}/{total}  =  {100*top1/total:.1f}%")
    print(f"  Top-3 accuracy: {top3}/{total}  =  {100*top3/total:.1f}%")

    print()
    print("Per concept:")
    for cid, (c, t) in sorted(per_concept.items()):
        bar = "#" * int(10 * c / t) + "." * (10 - int(10 * c / t))
        print(f"  {bar}  {c}/{t}  {cid}")

    if misses and verbose:
        print()
        print("-" * 74)
        print(f"MISSES ({len(misses)})")
        print("-" * 74)
        for b, a, exp, why in misses:
            print(f"  {b:24} -> {a:22}")
            print(f"      wanted {exp}")
            print(f"      {why}")

    print("=" * 74)
    return top1, total


if __name__ == "__main__":
    run()
