# Third-party notices

starRoboHarness is an independent project. Its initial control contracts were
informed by the following open-source projects:

- [GPT-as-Policy](https://github.com/anonymous-report-421/GPT-as-Policy), MIT.
  starRoboHarness reimplements the general proposal-review and bounded-correction
  interfaces; it does not vendor the rollout scheduler, authentication code,
  simulator integration, reports, or experiment artifacts.
  The experimental live runner imports the separately installed upstream
  RoboDojo RPC client, simulator server, case identity helpers, and public
  task context. Users must obtain that upstream runtime separately.
  The optional persistent backend also imports upstream's app-server transport,
  dynamic-tool schemas, image packet builder, and RoboDojo execution/gate/IK
  clients. starRoboHarness supplies policy identity, QwenPI adaptation, scheduling,
  and its persistent-agent progress budgets; these imports are not vendored.
- [starVLA](https://github.com/starVLA/starVLA), MIT. starRoboHarness documents and
  validates the public QwenPI_v3 inference contract but does not redistribute
  model code or checkpoints.
- [RoboDojo](https://github.com/RoboDojo-Benchmark/RoboDojo). Simulator, task,
  asset, dataset, and benchmark rights remain with their respective owners.

Model weights, simulator assets, datasets, and evaluation videos are not part
of this repository.
