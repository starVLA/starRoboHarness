# Five-task paired baseline

25/25 pure QwenPI_v3 cases paired with 25 frozen first-generation hybrid cases. Task, variant, layout hash and seeds were verified from all 50 native receipts.

| Task | Policy SR / Score | Hybrid SR / Score |
| --- | ---: | ---: |
| Put bottles into dustbin | 60% / 64 | 80% / 82 |
| Classify objects | 0% / 6 | 0% / 22 |
| Build tower | 80% / 82 | 80% / 86 |
| Make Kong | 20% / 20 | 60% / 60 |
| Pack objects into box | 0% / 20 | 0% / 2 |
| Overall | 32% / 38.4 | 44% / 50.4 |

Five cases per task; packing uses three standard and two random cases. Native Policy executes 16 actions before replanning. Four valid receipts were reused and 21 collected using same-node orchestration. Eighteen pre-control infrastructure failures remain separately preserved, excluded from SR/Score.

Hybrid gains 12 percentage points SR and 12 Score overall, but regresses on packing. This small panel does not prove universal superiority, superiority over direct GPT, or dev-versus-v1 causal improvement. Timing is descriptive because historical hardware/transport differ.
