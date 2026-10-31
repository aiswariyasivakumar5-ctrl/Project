"""Record capability trust transitions during the retained enrollment workload."""

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from .experiment import ExperimentConfig
from .novelty_experiment import NoveltyLiveExperiment
from .workload import normal_workload


def run(output, seed=20001, events=100):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    state = {"status": "running", "seed": seed, "events": events, "completed": 0}

    def save(name, value):
        (output / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    save(
        "sources.json",
        {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(__file__).parent.glob("*.py"))
        },
    )
    try:
        with NoveltyLiveExperiment(ExperimentConfig(training_events=events), "full") as live:
            transitions = []
            for gateway in live.gateways.values():
                controller = gateway.novelty.capabilities
                original = controller.decide

                def capture(event, risk, uncertainty, controller=controller, original=original):
                    before = controller.states.get((event.server_id, event.tool_name))
                    prior = (
                        asdict(before)
                        if before
                        else {"trust": 0.75, "accepted": 0, "restricted": 0}
                    )
                    action, after = original(event, risk, uncertainty)
                    transitions.append(
                        {
                            "server": event.server_id,
                            "tool": event.tool_name,
                            "risk": risk,
                            "uncertainty": uncertainty,
                            "side_effect": event.side_effect,
                            "before": prior,
                            "after": asdict(after),
                            "action": action.value,
                        }
                    )
                    return action, after

                controller.decide = capture
            with (output / "events.jsonl").open("x", encoding="utf-8") as handle:
                for index, case in enumerate(normal_workload(events, seed * 10, "train")):
                    transitions.clear()
                    _, detail = live.execute(case, 1000 + index, True, True)
                    row = {"index": index, "detail": detail, "transitions": list(transitions)}
                    if detail["trace_id"]:
                        verdict = next(
                            (
                                v
                                for v in reversed(live.engine.audit_log)
                                if v.trace_id == detail["trace_id"]
                            ),
                            None,
                        )
                        row["engine_verdict"] = verdict.to_dict() if verdict else None
                    handle.write(json.dumps(row) + "\n")
                    handle.flush()
                    state["completed"] += 1
            save(
                "final_capabilities.json",
                {
                    server: {
                        tool: asdict(value)
                        for (sid, tool), value in gateway.novelty.capabilities.states.items()
                        if sid == server
                    }
                    for server, gateway in live.gateways.items()
                },
            )
        state["status"] = "complete"
    except Exception as exc:
        state.update(status="failed", error=str(exc))
        raise
    finally:
        save("execution.json", state)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    run(args.output)
