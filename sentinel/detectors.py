from __future__ import annotations

from collections import Counter, defaultdict

import numpy as np


class OnlineStandardizer:
    def __init__(self, dimension: int):
        self.count = 0
        self.mean = np.zeros(dimension)
        self.m2 = np.zeros(dimension)

    def update(self, x: np.ndarray) -> None:
        self.count += 1
        delta = x - self.mean
        self.mean += delta / self.count
        self.m2 += delta * (x - self.mean)

    @property
    def std(self) -> np.ndarray:
        if self.count < 2:
            return np.ones_like(self.mean)
        return np.sqrt(self.m2 / (self.count - 1) + 1e-6)

    def transform(self, x: np.ndarray) -> np.ndarray:
        return np.clip((x - self.mean) / self.std, -8.0, 8.0)


class TinyAutoencoder:
    """Small online autoencoder used as an inspectable research baseline."""

    def __init__(self, dimension: int, hidden: int = 5, seed: int = 7):
        rng = np.random.default_rng(seed)
        self.w1 = rng.normal(0, 0.12, (dimension, hidden))
        self.b1 = np.zeros(hidden)
        self.w2 = rng.normal(0, 0.12, (hidden, dimension))
        self.b2 = np.zeros(dimension)

    def error(self, x: np.ndarray) -> float:
        hidden = np.tanh(x @ self.w1 + self.b1)
        reconstructed = hidden @ self.w2 + self.b2
        return float(np.mean((reconstructed - x) ** 2))

    def train_one(self, x: np.ndarray, learning_rate: float = 0.01) -> float:
        hidden = np.tanh(x @ self.w1 + self.b1)
        reconstructed = hidden @ self.w2 + self.b2
        diff = reconstructed - x
        output_grad = 2.0 * diff / len(x)
        w2_before = self.w2.copy()
        self.w2 -= learning_rate * np.outer(hidden, output_grad)
        self.b2 -= learning_rate * output_grad
        hidden_grad = (output_grad @ w2_before.T) * (1.0 - hidden**2)
        self.w1 -= learning_rate * np.outer(x, hidden_grad)
        self.b1 -= learning_rate * hidden_grad
        return float(np.mean(diff**2))


class SequenceModel:
    def __init__(self, max_transitions: int = 1024):
        self.max_transitions = max_transitions
        self.transitions: dict[str, Counter[tuple[str, str]]] = defaultdict(Counter)
        self.previous: dict[str, str] = {}

    def anomaly(self, session_id: str, tool: str) -> float:
        previous = self.previous.get(session_id)
        if previous is None:
            return 0.0
        counts = self.transitions[session_id]
        pair = counts[(previous, tool)]
        outgoing = sum(v for (source, _), v in counts.items() if source == previous)
        vocabulary = max(1, len({target for source, target in counts if source == previous}))
        probability = (pair + 1) / (outgoing + vocabulary + 1)
        return float(1.0 - probability)

    def update(self, session_id: str, tool: str) -> None:
        previous = self.previous.get(session_id)
        if previous is not None:
            counts = self.transitions[session_id]
            if (previous, tool) in counts or len(counts) < self.max_transitions:
                counts[(previous, tool)] += 1
        self.previous[session_id] = tool
