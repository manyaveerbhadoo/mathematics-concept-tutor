"""Torture test for the parser.

Three groups:
  GROUP A — messy but valid input a real student would type. Must parse.
  GROUP B — broken input. Must fail with a FRIENDLY message, never a crash.
  GROUP C — malicious input. Must be refused.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sympy
from mathcore import parse_student, MathInputError

x = sympy.Symbol("x")

# (input, expected result as a SymPy expression)
GROUP_A = [
    ("2x + 3",              2*x + 3),
    ("x^2 - 5x + 6",        x**2 - 5*x + 6),
    ("3(x+1)^2",            3*(x + 1)**2),
    ("x²  - 4",             x**2 - 4),                    # unicode superscript
    ("2x − 7",              2*x - 7),                     # unicode minus (PDF paste)
    ("4 × x ÷ 2",           2*x),                         # unicode times/divide
    ("√(x+1)",              sympy.sqrt(x + 1)),           # unicode radical
    ("sqrt x",              sympy.sqrt(x)),               # missing parens
    ("|x - 3|",             sympy.Abs(x - 3)),            # absolute value
    ("log_2(8)",            sympy.log(8, 2)),             # log with base
    ("log2(8)",             sympy.log(8, 2)),             # base, no underscore
    ("log(100)",            sympy.log(100, 10)),          # bare log = base 10
    ("ln(e)",               sympy.log(sympy.E)),          # ln = natural
    ("sin(x)^2 + cos(x)^2", sympy.sin(x)**2 + sympy.cos(x)**2),
    ("2pi",                 2*sympy.pi),
    ("  5x  ",              5*x),                         # stray whitespace
]

GROUP_B = [
    "",                 # nothing
    "3(x + 1",          # unbalanced paren
    "x + )",            # stray close paren
    "|x - 3",           # unmatched pipe
    "x^^2",             # typo
    "2x = 5",           # equation sent to expression parser
    "x" * 600,          # absurdly long
]

GROUP_C = [
    "__import__('os').system('ls')",
    "eval('1+1')",
    "lambda: 1",
    "open('/etc/passwd').read()",
]


def run():
    passed = failed = 0

    print("=" * 68)
    print("GROUP A — messy but valid student input (must parse correctly)")
    print("=" * 68)
    for raw, expected in GROUP_A:
        try:
            got = parse_student(raw)
            ok = sympy.simplify(got - expected) == 0
            status = "PASS" if ok else f"FAIL (got {got}, wanted {expected})"
        except Exception as exc:
            ok, status = False, f"FAIL (raised {type(exc).__name__}: {exc})"
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        print(f"  [{status:<10.10}] {raw!r:24} -> {got if ok else '---'}")

    print()
    print("=" * 68)
    print("GROUP B — broken input (must give a FRIENDLY error, never crash)")
    print("=" * 68)
    for raw in GROUP_B:
        label = repr(raw if len(raw) < 24 else raw[:20] + "...")
        try:
            parse_student(raw)
            ok, msg = False, "FAIL - accepted bad input!"
        except MathInputError as exc:
            ok, msg = True, f'"{exc}"'
        except Exception as exc:
            ok, msg = False, f"FAIL - ugly crash: {type(exc).__name__}"
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        print(f"  [{'PASS' if ok else 'FAIL':<4}] {label:<26} {msg}")

    print()
    print("=" * 68)
    print("GROUP C — code injection attempts (must be refused)")
    print("=" * 68)
    for raw in GROUP_C:
        try:
            parse_student(raw)
            ok, msg = False, "FAIL - EXECUTED! security hole"
        except MathInputError:
            ok, msg = True, "refused safely"
        except Exception as exc:
            ok, msg = False, f"FAIL - crashed: {type(exc).__name__}"
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        print(f"  [{'PASS' if ok else 'FAIL':<4}] {raw[:34]:<36} {msg}")

    print()
    print("=" * 68)
    print(f"RESULT: {passed} passed, {failed} failed")
    print("=" * 68)
    return failed


if __name__ == "__main__":
    sys.exit(1 if run() else 0)
