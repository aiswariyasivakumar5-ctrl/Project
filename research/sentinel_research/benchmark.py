from __future__ import annotations

import json
import time

from sentinel.engine import SentinelEngine
from sentinel.models import Action
from .simulator import attack_events, cross_server_attack, normal_events


def run_benchmark(training_count: int = 100, test_count: int = 100) -> dict[str, object]:
    engine = SentinelEngine(warmup_events=20)
    for event in normal_events(training_count, seed=11):
        engine.evaluate(event)

    started = time.perf_counter()
    normal_verdicts = [
        engine.evaluate(event, learn=False) for event in normal_events(test_count, seed=99)
    ]
    attack_verdicts = [engine.evaluate(event, learn=False) for _, event in attack_events()]
    first, second = cross_server_attack()
    engine.evaluate(first, learn=False)
    cross_server_verdict = engine.evaluate(second, learn=False)
    elapsed = time.perf_counter() - started
    malicious = attack_verdicts + [cross_server_verdict]
    blocked_actions = {Action.CONFIRM, Action.SANDBOX, Action.ISOLATE}
    return {
        "training_events": training_count,
        "normal_test_events": test_count,
        "attack_test_events": len(malicious),
        "false_positive_rate": sum(v.action in blocked_actions for v in normal_verdicts)
        / len(normal_verdicts),
        "attack_intervention_rate": sum(v.action in blocked_actions for v in malicious)
        / len(malicious),
        "mean_normal_risk": sum(v.anomaly_score for v in normal_verdicts) / len(normal_verdicts),
        "mean_attack_risk": sum(v.anomaly_score for v in malicious) / len(malicious),
        "mean_latency_ms": elapsed * 1000 / (len(normal_verdicts) + len(malicious) + 1),
        "attack_actions": [v.action.value for v in malicious],
    }


def print_benchmark(training_count: int = 100, test_count: int = 100) -> None:
    print(json.dumps(run_benchmark(training_count, test_count), indent=2))
