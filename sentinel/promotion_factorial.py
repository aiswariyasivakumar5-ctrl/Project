"""Fixed 2x2 development diagnostic; never chooses a winning configuration."""

import argparse
import json
from pathlib import Path

from .promotion_control import run_control


def run_factorial(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)

    def save(name, value):
        (output / name).write_text(
            json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )

    cells = [(varied, explicit) for varied in (False, True) for explicit in (False, True)]
    save(
        "protocol.json",
        {
            "purpose": "development-only factor isolation following failed controls",
            "cells": [{"varied_enrollment": v, "explicit_intent": e} for v, e in cells],
            "enrollment": "100 integer calls; constant scale 1 or balanced cycle 1,10,100,1000",
            "adaptive": "same six decimal-input calls within each intent condition",
            "interpretation": "Fixed synthetic controls, not independent research seeds or statistical evidence.",
            "policy_selection": "all five existing controls; no threshold selection or production changes",
        },
    )
    state = {"status": "running", "completed_cells": 0}
    save("execution.json", state)
    rows = []
    try:
        for varied, explicit in cells:
            name = f"{'varied' if varied else 'constant'}-{'explicit' if explicit else 'short'}"
            state["cell"] = name
            save("execution.json", state)
            for row in run_control(output / name, explicit, varied):
                rows.append(
                    {"cell": name, "varied_enrollment": varied, "explicit_intent": explicit, **row}
                )
            state["completed_cells"] += 1
            save("execution.json", state)
        save("summary.json", rows)
        state["status"] = "complete"
    except Exception as exc:
        state.update(status="failed", error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        save("execution.json", state)
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    rows = run_factorial(parser.parse_args().output)
    print(
        json.dumps(
            [
                {
                    "cell": row["cell"],
                    "policy": row["policy"],
                    "updates": row["model_updates"],
                    "promotions": row["promotion_indices"],
                    "first_risk": row["first_risk"],
                }
                for row in rows
            ],
            indent=2,
        )
    )
