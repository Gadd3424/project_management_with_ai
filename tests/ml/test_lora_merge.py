import json
from pathlib import Path

import numpy as np
import pytest
from safetensors.numpy import load_file, save_file

from services.evolutionary_merge.lora_merge import (
    merge_adapters,
    validate_compatibility,
    verify_checksum,
)


def adapter(path: Path, value: float, rank: int = 4) -> Path:
    save_file({"layer.lora_A": np.full((2, 2), value, dtype=np.float32)}, path)
    path.with_suffix(".json").write_text(
        json.dumps(
            {
                "base_model_id": "demo/base",
                "revision": "abc123",
                "rank": rank,
                "target_modules": ["layer"],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_compatible_adapters_are_weighted_and_checksummed(tmp_path: Path) -> None:
    first = adapter(tmp_path / "first.safetensors", 1.0)
    second = adapter(tmp_path / "second.safetensors", 3.0)
    output = tmp_path / "merged.safetensors"
    checksum = merge_adapters([first, second], [0.25, 0.75], output)
    merged = load_file(output)["layer.lora_A"]
    assert np.allclose(merged, 2.5)
    verify_checksum(output, checksum)


def test_incompatible_rank_is_rejected(tmp_path: Path) -> None:
    first = adapter(tmp_path / "first.safetensors", 1.0, rank=4)
    second = adapter(tmp_path / "second.safetensors", 2.0, rank=8)
    with pytest.raises(ValueError, match="incompatible metadata"):
        validate_compatibility([first, second])


def test_artifact_tampering_is_detected(tmp_path: Path) -> None:
    first = adapter(tmp_path / "first.safetensors", 1.0)
    second = adapter(tmp_path / "second.safetensors", 3.0)
    output = tmp_path / "merged.safetensors"
    checksum = merge_adapters([first, second], [0.5, 0.5], output)
    output.write_bytes(output.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_checksum(output, checksum)
