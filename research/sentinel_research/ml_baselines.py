from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

import numpy as np


class OfflineDetector(Protocol):
    name: str
    configuration: dict[str, object]

    def fit(self, x: np.ndarray) -> None: ...
    def score(self, x: np.ndarray) -> np.ndarray: ...


class StandardScaler:
    def fit(self, x: np.ndarray) -> None:
        self.mean = x.mean(axis=0)
        self.std = x.std(axis=0) + 1e-6

    def transform(self, x: np.ndarray) -> np.ndarray:
        return np.clip((x - self.mean) / self.std, -10, 10)


@dataclass
class IsolationNode:
    size: int
    feature: int | None = None
    split: float | None = None
    left: IsolationNode | None = None
    right: IsolationNode | None = None


def _c_factor(size: int) -> float:
    if size <= 1:
        return 0.0
    if size == 2:
        return 1.0
    return 2 * (math.log(size - 1) + 0.5772156649) - 2 * (size - 1) / size


class IsolationForestDetector:
    name = "isolation_forest"

    def __init__(self, seed: int = 42, trees: int = 64, sample_size: int = 256):
        self.seed, self.trees, self.sample_size = seed, trees, sample_size
        self.configuration = {"seed": seed, "trees": trees, "sample_size": sample_size}

    def _build(
        self, x: np.ndarray, depth: int, limit: int, rng: np.random.Generator
    ) -> IsolationNode:
        node = IsolationNode(len(x))
        if depth >= limit or len(x) <= 1:
            return node
        ranges = np.ptp(x, axis=0)
        candidates = np.flatnonzero(ranges > 1e-12)
        if not len(candidates):
            return node
        feature = int(rng.choice(candidates))
        low, high = float(x[:, feature].min()), float(x[:, feature].max())
        split = float(rng.uniform(low, high))
        mask = x[:, feature] < split
        if not mask.any() or mask.all():
            return node
        node.feature, node.split = feature, split
        node.left = self._build(x[mask], depth + 1, limit, rng)
        node.right = self._build(x[~mask], depth + 1, limit, rng)
        return node

    def fit(self, x: np.ndarray) -> None:
        rng = np.random.default_rng(self.seed)
        size = min(self.sample_size, len(x))
        limit = math.ceil(math.log2(max(2, size)))
        self.forest = []
        for _ in range(self.trees):
            sample = x[rng.choice(len(x), size=size, replace=False)]
            self.forest.append(self._build(sample, 0, limit, rng))
        self.normalizer = max(_c_factor(size), 1e-6)

    def _path(self, row: np.ndarray, node: IsolationNode, depth: int = 0) -> float:
        if node.feature is None:
            return depth + _c_factor(node.size)
        child = node.left if row[node.feature] < node.split else node.right
        return self._path(row, child, depth + 1)

    def score(self, x: np.ndarray) -> np.ndarray:
        paths = np.asarray([[self._path(row, tree) for tree in self.forest] for row in x])
        return np.power(2.0, -paths.mean(axis=1) / self.normalizer)


class OneClassSVMDetector:
    """Primal one-class SVM over deterministic random Fourier RBF features."""

    name = "one_class_svm"

    def __init__(
        self,
        seed: int = 42,
        nu: float = 0.05,
        gamma: float = 0.1,
        rff_dimensions: int = 96,
        epochs: int = 30,
        learning_rate: float = 0.02,
    ):
        self.seed, self.nu, self.gamma = seed, nu, gamma
        self.rff_dimensions, self.epochs, self.learning_rate = rff_dimensions, epochs, learning_rate
        self.configuration = {
            "seed": seed,
            "nu": nu,
            "gamma": gamma,
            "rff_dimensions": rff_dimensions,
            "epochs": epochs,
            "learning_rate": learning_rate,
            "kernel": "RBF-RFF approximation",
        }

    def _project(self, x: np.ndarray) -> np.ndarray:
        return math.sqrt(2 / self.rff_dimensions) * np.cos(x @ self.omega + self.phase)

    def fit(self, x: np.ndarray) -> None:
        self.scaler = StandardScaler()
        self.scaler.fit(x)
        z = self.scaler.transform(x)
        rng = np.random.default_rng(self.seed)
        self.omega = rng.normal(0, math.sqrt(2 * self.gamma), (z.shape[1], self.rff_dimensions))
        self.phase = rng.uniform(0, 2 * math.pi, self.rff_dimensions)
        phi = self._project(z)
        self.w = phi.mean(axis=0)
        self.rho = float(np.quantile(phi @ self.w, self.nu))
        batch_size = min(128, len(phi))
        for epoch in range(self.epochs):
            order = rng.permutation(len(phi))
            lr = self.learning_rate / math.sqrt(epoch + 1)
            for start in range(0, len(phi), batch_size):
                batch = phi[order[start : start + batch_size]]
                margins = batch @ self.w
                violating = batch[margins < self.rho]
                gradient = self.w.copy()
                if len(violating):
                    gradient -= violating.mean(axis=0) / self.nu
                self.w -= lr * gradient
            self.rho = float(np.quantile(phi @ self.w, self.nu))

    def score(self, x: np.ndarray) -> np.ndarray:
        decision = self._project(self.scaler.transform(x)) @ self.w - self.rho
        return -decision


class DenseAutoencoderDetector:
    name = "dense_autoencoder"

    def __init__(
        self,
        seed: int = 42,
        hidden: int = 12,
        epochs: int = 40,
        learning_rate: float = 0.01,
        batch_size: int = 128,
    ):
        self.seed, self.hidden, self.epochs = seed, hidden, epochs
        self.learning_rate, self.batch_size = learning_rate, batch_size
        self.configuration = {
            "seed": seed,
            "hidden": hidden,
            "epochs": epochs,
            "learning_rate": learning_rate,
            "batch_size": batch_size,
        }

    def fit(self, x: np.ndarray) -> None:
        self.scaler = StandardScaler()
        self.scaler.fit(x)
        z = self.scaler.transform(x)
        rng = np.random.default_rng(self.seed)
        self.w1 = rng.normal(0, 0.12, (z.shape[1], self.hidden))
        self.b1 = np.zeros(self.hidden)
        self.w2 = rng.normal(0, 0.12, (self.hidden, z.shape[1]))
        self.b2 = np.zeros(z.shape[1])
        for _ in range(self.epochs):
            for start in range(0, len(z), self.batch_size):
                batch = z[rng.permutation(len(z))[start : start + self.batch_size]]
                hidden = np.tanh(batch @ self.w1 + self.b1)
                output = hidden @ self.w2 + self.b2
                grad_out = 2 * (output - batch) / (len(batch) * z.shape[1])
                w2_before = self.w2.copy()
                self.w2 -= self.learning_rate * hidden.T @ grad_out
                self.b2 -= self.learning_rate * grad_out.sum(axis=0)
                grad_hidden = (grad_out @ w2_before.T) * (1 - hidden**2)
                self.w1 -= self.learning_rate * batch.T @ grad_hidden
                self.b1 -= self.learning_rate * grad_hidden.sum(axis=0)

    def score(self, x: np.ndarray) -> np.ndarray:
        z = self.scaler.transform(x)
        output = np.tanh(z @ self.w1 + self.b1) @ self.w2 + self.b2
        return np.mean((output - z) ** 2, axis=1)


DETECTORS = {
    "isolation_forest": IsolationForestDetector,
    "one_class_svm": OneClassSVMDetector,
    "dense_autoencoder": DenseAutoencoderDetector,
}
