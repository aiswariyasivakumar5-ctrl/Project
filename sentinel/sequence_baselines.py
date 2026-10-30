from __future__ import annotations

import math
from typing import Any

import numpy as np


class _PredictionHead:
    def _fit_head(
        self, representations: np.ndarray, targets: np.ndarray, rng: np.random.Generator
    ) -> None:
        self.head_w = rng.normal(0, 0.03, (representations.shape[1], targets.shape[1]))
        self.head_b = np.zeros(targets.shape[1])
        for _ in range(self.epochs):
            order = rng.permutation(len(targets))
            for start in range(0, len(targets), self.batch_size):
                indices = order[start : start + self.batch_size]
                hidden, expected = representations[indices], targets[indices]
                prediction = hidden @ self.head_w + self.head_b
                gradient = 2 * (prediction - expected) / (len(indices) * expected.shape[1])
                self.head_w -= self.learning_rate * hidden.T @ gradient
                self.head_b -= self.learning_rate * gradient.sum(axis=0)

    @staticmethod
    def _targets(x: np.ndarray) -> np.ndarray:
        return x[:, -1, :-1]

    def score(self, x: np.ndarray) -> np.ndarray:
        prediction = self._represent(x) @ self.head_w + self.head_b
        return np.mean((prediction - self._targets(x)) ** 2, axis=1)

    @property
    def parameter_count(self) -> int:
        return int(sum(value.size for value in self._parameters()))

    @property
    def model_size_bytes(self) -> int:
        return int(sum(value.nbytes for value in self._parameters()))


class LSTMAnomalyDetector(_PredictionHead):
    name = "lstm"

    def __init__(
        self,
        seed: int = 42,
        hidden: int = 16,
        epochs: int = 20,
        learning_rate: float = 0.01,
        batch_size: int = 128,
        sequence_length: int = 8,
    ):
        self.seed, self.hidden, self.epochs = seed, hidden, epochs
        self.learning_rate, self.batch_size, self.sequence_length = (
            learning_rate,
            batch_size,
            sequence_length,
        )
        self.configuration: dict[str, Any] = {
            "seed": seed,
            "hidden_dimension": hidden,
            "layers": 1,
            "dropout": 0.0,
            "learning_rate": learning_rate,
            "epochs": epochs,
            "batch_size": batch_size,
            "sequence_length": sequence_length,
            "optimizer": "mini-batch gradient descent on reconstruction head",
            "objective": "normal-only current-event reconstruction from a causal same-session LSTM representation",
            "encoder_training": "deterministic fixed LSTM encoder; reconstruction head optimized on TRAIN",
        }

    def fit(self, x: np.ndarray) -> None:
        rng = np.random.default_rng(self.seed)
        dimension = x.shape[2]
        scale = 1 / math.sqrt(dimension + self.hidden)
        self.w = rng.normal(0, scale, (dimension + self.hidden, 4 * self.hidden))
        self.b = np.zeros(4 * self.hidden)
        representations = self._represent(x)
        self._fit_head(representations, self._targets(x), rng)
        self.configuration.update(
            {
                "parameter_count": self.parameter_count,
                "model_size_bytes": self.model_size_bytes,
                "input_dimension": dimension,
            }
        )

    def _represent(self, x: np.ndarray) -> np.ndarray:
        h = np.zeros((len(x), self.hidden))
        cell = np.zeros_like(h)
        for position in range(x.shape[1]):
            valid = x[:, position, -1:]
            joined = np.concatenate([x[:, position], h], axis=1)
            gates = joined @ self.w + self.b
            i = 1 / (1 + np.exp(-np.clip(gates[:, : self.hidden], -30, 30)))
            f = 1 / (1 + np.exp(-np.clip(gates[:, self.hidden : 2 * self.hidden], -30, 30)))
            g = np.tanh(gates[:, 2 * self.hidden : 3 * self.hidden])
            o = 1 / (1 + np.exp(-np.clip(gates[:, 3 * self.hidden :], -30, 30)))
            candidate_cell = f * cell + i * g
            candidate_h = o * np.tanh(candidate_cell)
            cell = valid * candidate_cell + (1 - valid) * cell
            h = valid * candidate_h + (1 - valid) * h
        return h

    def _parameters(self) -> list[np.ndarray]:
        return [self.w, self.b, self.head_w, self.head_b]


class TransformerAnomalyDetector(_PredictionHead):
    name = "transformer"

    def __init__(
        self,
        seed: int = 42,
        embedding: int = 16,
        heads: int = 2,
        layers: int = 1,
        feed_forward: int = 32,
        epochs: int = 20,
        learning_rate: float = 0.01,
        batch_size: int = 128,
        sequence_length: int = 8,
        dropout: float = 0.0,
    ):
        if embedding % heads:
            raise ValueError("embedding dimension must be divisible by heads")
        self.seed, self.embedding, self.heads, self.layers, self.feed_forward = (
            seed,
            embedding,
            heads,
            layers,
            feed_forward,
        )
        self.epochs, self.learning_rate, self.batch_size, self.sequence_length = (
            epochs,
            learning_rate,
            batch_size,
            sequence_length,
        )
        self.configuration: dict[str, Any] = {
            "seed": seed,
            "embedding_dimension": embedding,
            "attention_heads": heads,
            "layers": layers,
            "feed_forward_dimension": feed_forward,
            "dropout": dropout,
            "learning_rate": learning_rate,
            "epochs": epochs,
            "batch_size": batch_size,
            "sequence_length": sequence_length,
            "optimizer": "mini-batch gradient descent on reconstruction head",
            "objective": "normal-only current-event reconstruction from causal masked same-session self-attention",
            "encoder_training": "deterministic fixed Transformer encoder; reconstruction head optimized on TRAIN",
            "positional_encoding": "fixed sinusoidal",
        }

    def fit(self, x: np.ndarray) -> None:
        rng = np.random.default_rng(self.seed)
        dimension = x.shape[2]
        scale = 1 / math.sqrt(dimension)
        self.input_w = rng.normal(0, scale, (dimension, self.embedding))
        self.input_b = np.zeros(self.embedding)
        self.blocks = []
        for _ in range(self.layers):
            self.blocks.append(
                tuple(
                    rng.normal(0, 1 / math.sqrt(self.embedding), shape)
                    for shape in (
                        (self.embedding, self.embedding),
                        (self.embedding, self.embedding),
                        (self.embedding, self.embedding),
                        (self.embedding, self.embedding),
                        (self.embedding, self.feed_forward),
                        (self.feed_forward, self.embedding),
                    )
                )
            )
        representations = self._represent(x)
        self._fit_head(representations, self._targets(x), rng)
        self.configuration.update(
            {
                "parameter_count": self.parameter_count,
                "model_size_bytes": self.model_size_bytes,
                "input_dimension": dimension,
            }
        )

    def _position(self, length: int) -> np.ndarray:
        positions = np.arange(length)[:, None]
        frequencies = np.exp(np.arange(0, self.embedding, 2) * (-math.log(10000) / self.embedding))
        result = np.zeros((length, self.embedding))
        result[:, 0::2] = np.sin(positions * frequencies)
        result[:, 1::2] = np.cos(positions * frequencies)
        return result

    def _represent(self, x: np.ndarray) -> np.ndarray:
        mask = x[:, :, -1].astype(bool)
        hidden = np.tanh(x @ self.input_w + self.input_b) + self._position(x.shape[1])[None, :, :]
        hidden *= mask[:, :, None]
        for q_w, k_w, v_w, o_w, f1, f2 in self.blocks:
            q, k, v = hidden @ q_w, hidden @ k_w, hidden @ v_w
            head_dim = self.embedding // self.heads
            attended = []
            for head in range(self.heads):
                sl = slice(head * head_dim, (head + 1) * head_dim)
                logits = (q[:, :, sl] @ np.swapaxes(k[:, :, sl], 1, 2)) / math.sqrt(head_dim)
                causal = np.triu(np.ones((x.shape[1], x.shape[1]), dtype=bool), 1)
                invalid = causal[None, :, :] | (~mask[:, None, :])
                logits = np.where(invalid, -1e9, logits)
                logits -= logits.max(axis=2, keepdims=True)
                weights = np.exp(logits) * mask[:, None, :]
                weights /= np.maximum(weights.sum(axis=2, keepdims=True), 1e-12)
                attended.append(weights @ v[:, :, sl])
            hidden = np.tanh(hidden + np.concatenate(attended, axis=2) @ o_w)
            hidden = np.tanh(hidden + np.tanh(hidden @ f1) @ f2)
            hidden *= mask[:, :, None]
        return hidden[:, -1, :]

    def _parameters(self) -> list[np.ndarray]:
        return [
            self.input_w,
            self.input_b,
            *[value for block in self.blocks for value in block],
            self.head_w,
            self.head_b,
        ]


SEQUENCE_DETECTORS = {"lstm": LSTMAnomalyDetector, "transformer": TransformerAnomalyDetector}
