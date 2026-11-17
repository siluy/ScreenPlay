# Endgame: Singularity

原版 Python/Pygame 桌面游戏，15题，easy/medium/hard 各5题。保留最初两个任务ID；新增任务覆盖基地建设、地域分布、收入储备、设备配置、研究依赖和安全等级。中期初态只装载公开任务已声明的原生科技与资产，后续价格、研究、施工、维护与发现风险均由原版引擎处理。

固定种子20260914，very-easy，暂停开始。原生速度与暂停规则保留，模型思考期间模拟冻结；操作与等待按统一更新配额推进。偏好、存档与判分状态位于独立私有目录；换局和读档被禁止。

15题现均有完整原生桌面成功轨迹：实际输入全部经过 Episode/PyAutoGUI，保留截图、动作和私有状态，且原有预算未增加。reference 明确标为 fixture-author；作者可使用私有状态规划，不能当作自主模型成绩。难度仍为作者估计，待模型/人工校准。

机制与证据范围见 [CURRICULUM.md](CURRICULUM.md)，当前逐题结果见 current witnesses (historical local artifact; not distributed)，包含探索与负例的完整记录见 desktop evidence (historical local artifact; not distributed)。离线原生资源轨迹另见 native-feasibility.json；其范围与桌面记录分开。

源码版本与许可见 source.json 和 UPSTREAM-*。构建：`screenplay build singularity`；列表：`screenplay tasks`；重放：`screenplay run TASK --reference`。
