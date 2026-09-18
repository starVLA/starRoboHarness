"""Small structured-output surface for bounded direct and hybrid control."""


def obj(properties):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


TEXT = {"type": "string"}
POSE = obj(
    {
        "position": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
        "quaternion_wxyz": {
            "type": "array",
            "items": {"type": "number"},
            "minItems": 4,
            "maxItems": 4,
        },
        "gripper_closed": {"type": "boolean"},
    }
)
PROGRESS = obj(
    {
        "verified_completed": {"type": "array", "items": TEXT},
        "currently_attempting": TEXT,
        "remaining": {"type": "array", "items": TEXT},
    }
)
ASSESSMENT = obj(
    {
        "task_progress": PROGRESS,
        "current_subgoal": TEXT,
        "execution_status": {
            "type": "string",
            "enum": ["not_started", "progressing", "failed", "uncertain", "recovered"],
        },
        "execution_evidence": TEXT,
        "expected_next_intent": TEXT,
        "predicted_next_intent": TEXT,
        "intent_status": {"type": "string", "enum": ["aligned", "misaligned", "uncertain"]},
        "intent_evidence": TEXT,
    }
)


def decision_schema(hybrid):
    properties = {
        "request_id": TEXT,
        "reason": TEXT,
        "mode": {"type": "string", "enum": ["student", "eef"] if hybrid else ["eef"]},
        "steps": {"type": "integer", "minimum": 1, "maximum": 15 if hybrid else 5},
        "target": {"anyOf": [obj({"left": POSE, "right": POSE}), {"type": "null"}]},
        "memory": TEXT,
    }
    if hybrid:
        properties["assessment"] = ASSESSMENT
    return obj(properties)
