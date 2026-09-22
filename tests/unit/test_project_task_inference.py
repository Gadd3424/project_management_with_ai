import hashlib
from pathlib import Path

import numpy as np
from safetensors.numpy import save_file

from services.inference.main import EvolutionModel, ProjectTaskSuggestionsRequest, project_task_suggestions


def test_initial_tasks_use_verified_evolutionary_merge_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "merged-adapter.safetensors"
    save_file({"layer.lora_A": np.full((2, 2), 0.5, dtype=np.float32)}, artifact)
    checksum = hashlib.sha256(artifact.read_bytes()).hexdigest()
    response = project_task_suggestions(
        ProjectTaskSuggestionsRequest(
            snapshot={
                "name": "新規事業",
                "description": "検証を行う",
                "objective": "顧客価値を検証する",
                "success_criteria": "顧客が試行を完了する",
                "due_date": None,
            },
            model=EvolutionModel(
                id="merged-model",
                version="1.0",
                artifact_path=str(artifact),
                checksum=checksum,
            ),
        )
    )
    assert response.provider == "evolutionary_merge"
    assert response.model_id == "merged-model"
    assert len(response.proposed_values["tasks"]) >= 3
    assert any(item["type"] == "evolutionary_model_signal" for item in response.evidence)
