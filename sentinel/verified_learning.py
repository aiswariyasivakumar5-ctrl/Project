"""Experimental application-verified learning; not a general semantic detector."""

import copy
import math

from .novelty import NoveltySentinelEngine


def verify_calculation(event):
    """Trusted local reference implementation for the mock calculator only.

    None means unsupported, not safe. This checks result correctness, not user
    authorization, attestation authenticity, or suitability for other tools.
    """
    if event.tool_name != "calculate":
        return None
    if not event.success or event.side_effect or set(event.arguments) != {"a", "b"}:
        return False
    values = list(event.arguments.values())
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        return False
    expected = values[0] + values[1]
    if not math.isfinite(expected):
        return False
    result = event.response
    if (
        not isinstance(result, dict)
        or set(result) - {"content", "isError"}
        or result.get("isError", False) is not False
    ):
        return False
    content = result.get("content")
    if not isinstance(content, list) or len(content) != 1 or not isinstance(content[0], dict):
        return False
    item = content[0]
    if (
        set(item) != {"type", "text"}
        or item["type"] != "text"
        or not isinstance(item["text"], str)
        or len(item["text"]) > 128
    ):
        return False
    try:
        value = float(item["text"])
    except ValueError:
        return False
    return math.isfinite(value) and value == expected


class VerifiedLearningEngine(NoveltySentinelEngine):
    """Opt-in wrapper. Verification failures withhold learning, not responses.

    The embedding application supplies a trusted, bounded verifier; no caller
    header or remote-server assertion can supply it. Unknown/errors fail closed.
    Existing engine defaults and published experiment variants stay unchanged.
    """

    def __init__(self, *args, verifier=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.verifier = verifier

    def _verified(self, event):
        if self.verifier is None:
            return False
        try:
            # A verifier cannot mutate the original event or queued candidate.
            return self.verifier(copy.deepcopy(event)) is True
        except Exception:
            return False

    def _evaluate(
        self,
        event,
        *,
        trusted_enrollment=False,
        attested=False,
        learn=True,
        independent_session=None,
    ):
        checked = 0
        authorized = False
        if learn:
            checked = 1
            authorized = self._verified(event)
            candidate = self.memory.candidates.get(
                (event.server_id, event.tool_name, self.memory.fingerprint(event))
            )
            if authorized and candidate is not None:
                for previous in candidate.events:
                    checked += 1
                    if not self._verified(previous):
                        authorized = False
                        break
        verdict = super()._evaluate(
            event,
            trusted_enrollment=trusted_enrollment,
            attested=attested,
            learn=learn and authorized,
            independent_session=independent_session,
        )
        verdict.base.provenance = {
            **(verdict.base.provenance or {}),
            "learning_verification": {
                "requested": learn,
                "passed": authorized if learn else None,
                "events_checked": checked,
                "scope": "application-side result verification; not response blocking",
            },
        }
        if learn and not authorized:
            verdict.memory_disposition = "evidence-withheld"
            verdict.reasons = (
                *verdict.reasons,
                "learning withheld: result verification unavailable or failed",
            )
        return verdict
