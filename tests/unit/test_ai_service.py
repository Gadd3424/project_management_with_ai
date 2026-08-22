from apps.api.app.ai_service import delay_probability


def test_delay_probability_increases_for_unassigned_near_due_task() -> None:
    safe = delay_probability({"days_to_due": 20, "status": "in_progress", "has_assignee": True, "priority": "medium"})
    risky = delay_probability({"days_to_due": 1, "status": "todo", "has_assignee": False, "priority": "high"})
    assert risky > safe
    assert 0 <= safe <= 1
    assert 0 <= risky <= 1
