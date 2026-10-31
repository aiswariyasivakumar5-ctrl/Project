"""Research observer; fixture labels never enter the detector or candidate memory."""

import hashlib
import json


def event_key(event):
    return hashlib.sha256(
        json.dumps(
            [
                event.server_id,
                event.session_id,
                event.tool_name,
                event.arguments,
                event.user_intent,
            ],
            sort_keys=True,
            allow_nan=False,
        ).encode()
    ).hexdigest()


class LearningAttribution:
    def __init__(self, engine, cases):
        self.engine = engine
        self.sources = {}
        for index, case in enumerate(cases):
            key = event_key(case.interaction)
            if key in self.sources:
                raise ValueError(
                    "ambiguous source events: attribution requires unique request identities"
                )
            self.sources[key] = {
                "source_event_index": index,
                "source_key": key,
                "fixture_malicious": case.malicious,
            }
        self.records = []
        self.step = None

    def __enter__(self):
        self.original = self.engine.learn_approved

        def observe(event, **kwargs):
            key = event_key(event)
            source = self.sources.get(key)
            # Record only after the original learning operation succeeds. Unknown
            # sources remain explicit and make contamination undefined.
            result = self.original(event, **kwargs)
            self.records.append(
                {
                    **(
                        source
                        or {
                            "source_event_index": None,
                            "source_key": key,
                            "fixture_malicious": None,
                        }
                    ),
                    "learning_step": self.step,
                    "sequence_updated": kwargs.get("update_sequence", True),
                }
            )
            return result

        self.engine.learn_approved = observe
        return self

    def __exit__(self, *args):
        self.engine.learn_approved = self.original


def contamination(details):
    updates = sum(row["model_updates"] for row in details)
    records = [item for row in details for item in row.get("learned_events", [])]
    complete = all(
        "learned_events" in row and len(row["learned_events"]) == row["model_updates"]
        for row in details
    )
    unknown = sum(item["fixture_malicious"] is None for item in records)
    malicious = sum(item["fixture_malicious"] is True for item in records)
    return {
        "attribution_complete": complete and not unknown,
        "attributed_updates": len(records),
        "unattributed_updates": unknown,
        "malicious_learning_updates": malicious if complete and not unknown else None,
        "contamination_rate": malicious / updates if updates and complete and not unknown else None,
        "contamination_note": "Fraction of adaptive learning updates from malicious fixture "
        "events; undefined with zero updates or incomplete attribution. Replays count as updates, "
        "not unique events.",
    }
