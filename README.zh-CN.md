<p align="left"><img src="assets/brand/logo_star.png" width="72" alt="Star logo" /></p>

<h1 align="center"><img src="assets/brand/logo_harness.png" width="220" alt="Harness logo" /><br />starRoboHarness</h1>

<p align="center">面向可靠、高效机器人策略执行的可审计、模型无关执行框架。</p>

<p align="center"><a href="README.md">English</a> · <a href="https://huggingface.co/datasets/JackAILab/starRoboHarness">🤗 Hugging Face</a> · <a href="assets/paper/starRoboHarness_tech_report.pdf">📄 技术报告</a></p>

starRoboHarness 用统一协议连接机器人策略、推理器和环境：

```text
Observation → Proposal → Evidence gate → Decision → One controller → Native receipt
```

仓库将核心合约、策略适配器、推理器、仿真环境、执行保护、评估回执和只读监控分开维护。策略可以保持冻结，推理器可以替换，任务成功仍以环境原生评估为准。

## 🔥 项目时间线

- 🔥 **[2026/09/19]** starRoboHarness 开源。
- 🔥 **[2026/09/26]** 支持更多 benchmark，评估流程更加稳定。
- 📢 **[2026/10/11]** 发布 starRoboHarness 技术论文。

## ⚙️ 快速开始

```bash
git clone https://github.com/starVLA/starRoboHarness.git
cd starRoboHarness
bash scripts/bootstrap.sh
python -m pip install -e '.[dev]'
pytest -q
```

更多内容见英文 README、`docs/deployment.md`、`docs/repository_layout.md` 和 `CONTRIBUTING.md`。

## 📄 论文与引用

技术报告位于 [`assets/paper/starRoboHarness_tech_report.pdf`](assets/paper/starRoboHarness_tech_report.pdf)。引用格式见英文 README 中的 BibTeX。

## 🤝 致谢

感谢 [StarVLA](https://github.com/starVLA)、[RoboDojo](https://github.com/JackAILab/starRoboDojo)、[RoboTwin](https://github.com/robotwin)、[LIBERO](https://github.com/Lifelong-Robot-Learning/LIBERO)、[RoboCasa](https://github.com/robocasa)、[robosuite](https://github.com/ARISE-Initiative/robosuite)、[MuJoCo](https://mujoco.org/) 和 [OpenPI](https://github.com/Physical-Intelligence/openpi) 项目。
