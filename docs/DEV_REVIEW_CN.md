# starRoboHarness `dev` 分支审查说明（中文）

这是一份面向协作者的、去除内部机器与账户信息的开发版说明。它描述 harness 的设计边界、已完成的改进和发布前必须人工检查的项目；它不把未完成的实验当作性能结论。

## 当前开发重点

1. **类别完成优先级**：任务上下文要求 agent 维护可审计的类别 ledger。当前类别中的对象必须完成“抓取—抬升—运输—释放—重新观察确认”闭环后才能标记完成；未确认的对象保持 pending，不能仅因为物体曾经接近目标区域就切换类别。
2. **episode-local workspace**：每个 episode 都获得独立的 skill、gate、teacher context、EEF 安全约束、结构化 NOTES、task context、可写 scratch 和 hash manifest。这样 sub-policy 能看到稳定且可恢复的工作契约，而不是只依赖一段长 developer prompt。
3. **可恢复运行**：Codex 握手、启动前检查和清理阶段都有界重试；真实控制开始后，失败尝试必须保留原始 evidence，禁止静默重放或把基础设施失败计入 SR/Score。
4. **provider 故障隔离**：额度、429 和模型容量错误会被安全分类并写入 `error.json`。campaign 默认仍然 fail-closed；只有显式设置 `continue_after_provider_failure=true` 时，才会在保留该无效 case 的前提下继续独立 case，绝不重放已经进入物理控制的 episode。
5. **只读看板**：看板只读取 progress、公开 decision record、outcome、usage 和媒体，不会改变实验状态；`pending`、基础设施错误和未完成 outcome 不会被伪装成 0 分成功率。

## 运行结果的正确口径

只有同时满足以下条件的 episode 才能进入有效结果表：

- `complete=true`；
- `valid_for_success_rate=true`；
- 有 native RoboDojo terminal outcome；
- 原始 controller history、公开 decision record 和必要的媒体证据可追溯。

运行中的 `progress.json` 只能说明链路仍在推进，不能据此提前填写 SR 或 Score。不同 harness 版本、不同 layout、不同 seed 的结果也不能直接混平均。

## 发布前人工检查清单

1. `git status --short --branch` 干净，提交作者和变更范围正确。
2. 运行完整测试，并额外检查 workspace artifact hash、stale workspace、类别 ledger、握手超时、清理异常和精确 tmux 会话匹配。
3. 用一个离线/模拟 case 检查 category ledger：未完成类别不会提前切换，证据撤销会恢复 pending。
4. 随机抽查一个 episode 的 workspace，确认 skill、gate、teacher context、EEF 约束和 NOTES 均存在且没有内部路径、账户信息或集群细节。
5. 抽查看板的 `dashboard.html` 与 `state.json`，确认它们只读、能在运行中刷新，且 pending/基础设施错误不会被计作失败。
6. 只有目标任务都生成有效 native terminal outcome 后，才生成公开性能表；失败尝试和基础设施排除项应单独列出。

## provider 额度耗尽时的处理

一次真实运行可能在已经执行若干物理步后遇到 Codex `usageLimitExceeded`。这种 episode 必须保留为无效尝试，不能切换账户后从中间状态继续，也不能把它记成 0 分。更换账户或 provider 后，应使用新的 output root 和新的 case attempt；需要让同一批次继续其他独立 case 时，才在配置中显式打开 `continue_after_provider_failure`，并在最终报告中单独列出 provider 隔离项。

## 证据与隐私边界

公开仓库只保留通用代码、脱敏文档和可复现的接口契约。原始 RPC、账户额度、集群地址、私有 checkpoint、内部路径、人员信息和未审查的完整运行日志不应提交到公开仓库。需要协作时，应发布经过筛选的结果摘要、公开 decision record、媒体索引和 hash manifest。

## 看板使用

看板服务应在持久化终端会话中运行，浏览器通过受保护的端口转发访问。看板的状态是监控证据，不是实验控制入口；关闭浏览器不会停止实验，刷新页面也不会重放 episode。
