from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from safetensors import safe_open
from safetensors.numpy import save_file


@dataclass(frozen=True)
class AdapterMetadata:
    base_model_id: str
    revision: str
    rank: int
    target_modules: tuple[str, ...]


def load_metadata(path: Path) -> AdapterMetadata:
    data = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    return AdapterMetadata(
        base_model_id=data["base_model_id"],
        revision=data["revision"],
        rank=int(data["rank"]),
        target_modules=tuple(sorted(data["target_modules"])),
    )


def validate_compatibility(paths: list[Path]) -> AdapterMetadata:
    if len(paths) < 2:
        raise ValueError("At least two adapters are required")
    metadata = [load_metadata(path) for path in paths]
    if any(item != metadata[0] for item in metadata[1:]):
        raise ValueError("LoRA adapters have incompatible metadata")
    tensor_specs: list[dict[str, tuple[tuple[int, ...], str]]] = []
    for path in paths:
        with safe_open(path, framework="np") as handle:
            tensor_specs.append(
                {key: (handle.get_tensor(key).shape, str(handle.get_tensor(key).dtype)) for key in handle.keys()}
            )
    if any(item != tensor_specs[0] for item in tensor_specs[1:]):
        raise ValueError("LoRA adapters have incompatible tensor names, shapes, or dtypes")
    return metadata[0]


def merge_adapters(paths: list[Path], weights: list[float], output: Path) -> str:
    validate_compatibility(paths)
    normalized = np.asarray(weights, dtype=np.float64)
    if len(normalized) != len(paths) or not np.isfinite(normalized).all() or (normalized < 0).any():
        raise ValueError("Weights must be finite, non-negative, and match adapter count")
    if normalized.sum() <= 0:
        raise ValueError("Weights must have a positive sum")
    normalized /= normalized.sum()
    tensors: dict[str, np.ndarray] = {}
    for path, weight in zip(paths, normalized, strict=True):
        with safe_open(path, framework="np") as handle:
            for key in handle.keys():
                value = handle.get_tensor(key).astype(np.float32)
                tensors[key] = tensors.get(key, np.zeros_like(value)) + float(weight) * value
    output.parent.mkdir(parents=True, exist_ok=True)
    save_file(tensors, output)
    return hashlib.sha256(output.read_bytes()).hexdigest()


def verify_checksum(path: Path, expected_sha256: str) -> None:
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if not hmac.compare_digest(actual, expected_sha256.lower()):
        raise ValueError("Model artifact checksum mismatch")

