# Enigma

原版 C++/SDL 物理解谜游戏，15个原生 XML/Lua 关卡，easy/medium/hard 各5题。保留原来的 Oxyd pair/memory ID，新增开关门、钥匙锁、可推箱、迷宫、冰面、沙地、水域及组合记忆。使用原版鼠标力、惯性、摩擦、碰撞和 Oxyd 完成信号；未放大界面、平滑输入或修改物理。

固定随机种子20260914。100个10ms更新完成开局动画；模型思考期间冻结。普通输入后6更新，等待按10ms配额推进。初始指针(400,292)，原生中键 Ignore Movement 用于重新放置指针。死亡即结束本次episode，即使原生备用生命仍可复活；这是明确公开的评测终止规则。每次运行保存并执行原内容的 private/level.xml 快照。

15关现均有当前XML快照对应的完整原生桌面成功轨迹，均在原有预算内。全部输入经 Episode/PyAutoGUI，保留截图、动作与私有状态。reference 标记 fixture-author；作者使用私有位置反馈规划，不属于自主模型成绩。真实入水死亡负例已触发 game_lost。

机制、难度估计和原生对象来源见 [CURRICULUM.md](CURRICULUM.md)；当前逐关成功记录见 current witnesses (historical local artifact; not distributed)，探索及负例见 desktop evidence (historical local artifact; not distributed)。topology-feasibility.json 仅证明抽象连通性，其范围与真实物理轨迹分开。难度仍待模型/人工校准。

源码版本与许可见 source.json 和 UPSTREAM-*。构建：`screenplay build enigma`；列表：`screenplay tasks`；重放：`screenplay run TASK --reference`。
