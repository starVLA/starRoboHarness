from hybrid_rollout.robodojo.prompt_context import task_context


def test_category_tasks_expose_completion_ledger_policy():
    context = task_context("classify_objects_by_language")
    policy = context["category_completion"]
    assert "instances" in policy["ledger_fields"]
    assert "Finish and verify" in policy["priority"]
    assert "fresh observation" in policy["evidence"]


def test_non_category_task_does_not_receive_category_ledger():
    assert "category_completion" not in task_context("arrange_largest_number")
