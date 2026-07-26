#!/usr/bin/env python3
"""
try_it.py — talk to the tutor from your terminal, no Discord needed.

    python3 try_it.py                        interactive
    python3 try_it.py --demo                 run the demo conversations

Interactive commands:
    x^2 - 5x + 6 -> (x-2)(x-3)      show a step you took
    why do logs split up            ask in plain English
    x^2 - 9                         just paste where you're stuck
    quit
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mathcore.tutor import explain_step, explain_question, explain_stuck

BAR = "=" * 72


def respond(line: str) -> str:
    line = line.strip()
    for arrow in ("->", "=>", "-->"):
        if arrow in line:
            before, after = line.split(arrow, 1)
            return explain_step(before, after).to_text()
    # A question if it reads like words; otherwise treat it as an expression.
    if sum(ch.isalpha() for ch in line) > len(line) * 0.5 and " " in line:
        return explain_question(line).to_text()
    r = explain_stuck(line)
    return r.to_text() if r.ok else explain_question(line).to_text()


DEMOS = [
    "x^2 - 5x + 6 -> (x - 2)(x - 3)",
    "log_2(8*4) -> log_2(8) + log_2(4)",
    "2^x -> log(7)/log(2)",
    "why can't I cancel the x in (x+2)/x",
    "3(x + 2) -> 3x + 6",
]


def main():
    if "--demo" in sys.argv:
        for d in DEMOS:
            print(BAR)
            print(f"STUDENT:  {d}")
            print(BAR)
            print(respond(d))
            print()
        return

    print(BAR)
    print("Math 1B tutor — type a step, a question, or 'quit'.")
    print("Example:  x^2 - 5x + 6 -> (x-2)(x-3)")
    print(BAR)
    while True:
        try:
            line = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if line.lower() in {"quit", "exit", "q"}:
            return
        if line:
            print()
            print(respond(line))


if __name__ == "__main__":
    main()
