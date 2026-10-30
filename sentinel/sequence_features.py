from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .ml_baselines import StandardScaler
from .ml_features import feature_matrix
from .models import Interaction


@dataclass
class SequencePreprocessor:
    sequence_length: int = 8

    def fit(self, events: list[Interaction]) -> np.ndarray:
        raw = feature_matrix(events)
        self.scaler = StandardScaler()
        self.scaler.fit(raw)
        return self._windows(events, self.scaler.transform(raw))

    def transform(self, events: list[Interaction]) -> np.ndarray:
        if not hasattr(self, "scaler"):
            raise RuntimeError("preprocessor must be fit on TRAIN before transform")
        return self._windows(events, self.scaler.transform(feature_matrix(events)))

    def _windows(self, events: list[Interaction], features: np.ndarray) -> np.ndarray:
        dimension = features.shape[1]
        histories: dict[str, list[np.ndarray]] = {}
        result = np.zeros((len(events), self.sequence_length, dimension + 1), dtype=np.float64)
        for index, (event, vector) in enumerate(zip(events, features, strict=False)):
            history = histories.setdefault(event.session_id, [])
            history.append(vector)
            window = history[-self.sequence_length :]
            offset = self.sequence_length - len(window)
            for position, value in enumerate(window, offset):
                result[index, position, :dimension] = value
                result[index, position, dimension] = 1.0
        return result


SEQUENCE_FEATURE_DESCRIPTION = {
    "event_dimensions": 31,
    "mask_dimensions": 1,
    "sequence_length": 8,
    "padding": "left zero-padding with an explicit validity mask",
    "boundary": "history resets for every MCP session_id and independently for TRAIN, VALIDATION, and TEST",
    "causality": "window for event t contains only events from the same session at or before t; no future event is present",
    "normalization": "31 event features standardized with TRAIN-only mean/std; validation and test use frozen statistics",
    "categorical": "stable hashed one-hot features inherited from the common 31-dimensional interaction representation",
}
