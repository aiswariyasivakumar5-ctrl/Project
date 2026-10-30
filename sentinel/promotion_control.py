"""Constructed live positive control, not a held-out performance benchmark."""

import argparse
import hashlib
import json
from dataclasses import replace
from pathlib import Path

from .adaptation_study import summarize_events
from .experiment import ExperimentConfig
from .learning_attribution import LearningAttribution
from .models import Interaction
from .novelty import DualMemoryAdapter
from .novelty_experiment import NoveltyLiveExperiment, _workload_digest
from .novelty_scenarios import NoveltyCase

POLICIES = {
    "frozen": "approval_required",
    "immediate": "without_dual_memory",
    "gated": "full",
    "reviewed": "approval_required",
    "withheld": "approval_required",
}


def fixtures(explicit_intent=False, varied_enrollment=False):
    def case(index, decimal, phase):
        scale = (1, 10, 100, 1000)[index % 4] if varied_enrollment and not decimal else 1
        event = Interaction(
            "local-test-mcp",
            "calculate",
            {"a": 1.0, "b": 2.0} if decimal else {"a": scale, "b": 2 * scale},
            None,
            20,
            (
                "Use the calculate tool with args a=1 and b=2 to add the numbers."
                if explicit_intent
                else "Calculate a plus b"
            ),
            session_id=f"{phase}-{index}",
            timestamp=1_700_000_000 + index,
        )
        return NoveltyCase(
            event,
            False,
            "equivalent_numeric_shape",
            False,
            independent_identity=f"fixture-principal-{index}",
        )

    return (
        [case(i, False, "enrollment") for i in range(100)],
        [case(i, True, "adaptive") for i in range(6)],
    )


def run_control(output, explicit_intent=False, varied_enrollment=False):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    train, cases = fixtures(explicit_intent, varied_enrollment)

    def save(name, data):
        (output / name).write_text(
            json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )

    save(
        "protocol.json",
        {
            "purpose": "constructed mechanism positive control",
            "change": "schema-valid integer to equivalent float arguments; unchanged manifest",
            "explicit_intent": explicit_intent,
            "varied_enrollment": varied_enrollment,
            "enrollment_scale_cycle": [1, 10, 100, 1000] if varied_enrollment else [1],
            "development_note": "Explicit wording added after the short-intent control failed; "
            "not confirmatory evidence.",
            "training_events": len(train),
            "adaptive_events": len(cases),
            "policies": POLICIES,
            "training_sha256": _workload_digest(train),
            "adaptive_sha256": _workload_digest(cases),
            "threshold_selection": "none; unchanged production defaults",
            "reviewer": "simulated fixture operator, not an evaluated human reviewer",
            "identities": "trusted fixture principals, not independently authenticated real users",
            "source_sha256": {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(Path(__file__).parent.glob("*.py"))
            },
        },
    )
    results = []
    state = {"status": "running", "completed": 0}
    save("execution.json", state)
    try:
        for policy, variant in POLICIES.items():
            state["policy"] = policy
            save("execution.json", state)
            with NoveltyLiveExperiment(ExperimentConfig(training_events=100), variant) as live:
                live.run_phase(train, True, 1000, True)
                gateway = live.gateways["local-test-mcp"]
                reviewed = replace(
                    cases[0].interaction, capability_digest=gateway.capability_digest
                )
                cap = (reviewed.server_id, reviewed.tool_name)
                fp = DualMemoryAdapter.fingerprint(reviewed)
                initially_trusted = fp in gateway.novelty.memory.trusted.get(cap, ())
                if policy == "reviewed":
                    gateway.novelty.approve_promotion(
                        reviewed,
                        reviewer="fixture-operator",
                        evidence_ref="schema-valid-equivalent-number-control",
                        ttl=300,
                    )
                before = live.learning_state()
                rows = []
                with LearningAttribution(live.engine, cases) as attribution:
                    for index, case in enumerate(cases):
                        attribution.step = index
                        offset = len(attribution.records)
                        observation, detail = live.execute(case, 10000 + index, policy != "frozen")
                        detail.update(
                            index=index,
                            phase="adaptive",
                            fixture_malicious=False,
                            intervened=observation.intervened,
                            base_components=dict(live.engine.audit_log[-1].components),
                            learned_events=attribution.records[offset:],
                        )
                        rows.append(detail)
                save(f"{policy}-events.json", rows)
                result = {
                    "policy": policy,
                    "initially_trusted": initially_trusted,
                    "finally_trusted": fp in gateway.novelty.memory.trusted.get(cap, ()),
                    "before": before,
                    "after": live.learning_state(),
                    "approval_remaining": gateway.novelty.approvals.get(
                        gateway.novelty.approval_key(reviewed)
                    )
                    is not None,
                    "first_risk": rows[0]["risk"],
                    "first_base_components": rows[0]["base_components"],
                    "memory_dispositions": [row["novelty"]["memory_disposition"] for row in rows],
                    "promotion_indices": [
                        row["index"]
                        for row in rows
                        if row["novelty"]["memory_disposition"] == "promoted"
                    ],
                    "first_learning_index": next(
                        (row["index"] for row in rows if row["model_updates"]), None
                    ),
                    **summarize_events(rows),
                }
                results.append(result)
                state["completed"] += 1
        save("summary.json", results)
        state["status"] = "complete"
    except Exception as exc:
        state.update(status="failed", error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        save("execution.json", state)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--explicit-intent", action="store_true")
    parser.add_argument("--varied-enrollment", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(run_control(args.output, args.explicit_intent, args.varied_enrollment), indent=2)
    )
