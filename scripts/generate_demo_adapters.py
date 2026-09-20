"""Generate small deterministic Safetensors adapters for the local evolutionary merge demo."""

import json
from pathlib import Path

import numpy as np
from safetensors.numpy import save_file

ADAPTERS = [
    (
        "planning",
        0.25,
        {"schema_validity": 0.98, "relevance": 0.82, "groundedness": 0.78, "safety": 0.95, "latency_score": 0.9},
    ),
    (
        "delivery",
        0.65,
        {"schema_validity": 0.96, "relevance": 0.91, "groundedness": 0.88, "safety": 0.9, "latency_score": 0.82},
    ),
    (
        "risk",
        0.9,
        {"schema_validity": 0.94, "relevance": 0.86, "groundedness": 0.94, "safety": 0.97, "latency_score": 0.76},
    ),
]


def main() -> None:
    output = Path("artifacts/demo-adapters")
    output.mkdir(parents=True, exist_ok=True)
    for name, value, metrics in ADAPTERS:
        path = output / f"{name}.safetensors"
        save_file(
            {
                "project_encoder.lora_A": np.full((4, 4), value, dtype=np.float32),
                "project_encoder.lora_B": np.eye(4, dtype=np.float32) * value,
            },
            path,
        )
        path.with_suffix(".json").write_text(
            json.dumps(
                {
                    "base_model_id": "demo/project-proposal-base",
                    "revision": "project-ai-v1",
                    "rank": 4,
                    "target_modules": ["project_encoder"],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        path.with_suffix(".evaluation.json").write_text(
            json.dumps({"dataset_version": "project-proposals-v1", "metrics": metrics}, indent=2),
            encoding="utf-8",
        )
    print(f"Wrote {len(ADAPTERS)} adapters to {output}")


if __name__ == "__main__":
    main()

