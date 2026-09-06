# Corrections

Reference implementations and hints live here. `lab check` imports them to grade
your work; nothing else reads this directory.

It is hidden by convention, not by git. You *can* read it, and sometimes you
should — but make that a decision rather than a reflex. `lab hint` gives you a
nudge first, and `lab solve --yes` prints a reference solution when you actually
want one.

The tree mirrors `exercises/` exactly. An exercise at
`exercises/pandas/03_transforming/07_np_where.py` is graded against
`.corrections/pandas/03_transforming/07_np_where.py`.

## Why there are no expected answers stored here

Your dataset is generated from a seed unique to your clone, so a stored answer
would be wrong on every other machine. Instead the grader runs the reference
implementation against *your* data and compares its output to yours. That is why
answers cannot be memorised, shared between learners, or worked out by hand.
