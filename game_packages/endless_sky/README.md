# Endless Sky

使用原版 Endless Sky C++/SDL/OpenGL、原生 StartConditions、Shuttle 和 New Boston 港口。版本与素材许可见 source.json 和 UPSTREAM-*。保留原生 20 吨货舱、6 个床位、最低 1 名必需船员和原版交易价格；不改变原生交易、雇佣、资金或容量规则。

## 15 题课程

每级 5 题（easy / medium / hard），`parameters.curriculum` 说明机制和作者难度预估，仍待人类/模型校准。保留原 manifest、rebalance ID。其他任务涉及清仓、选择性保留货物、满舱换货、先出售以筹资、精确三类配货、现金限制下的多解货类分配、船员增减及跨面板组合。不是 15 组采购数量的变体；尚未覆盖飞行、战斗或跨星系贸易。

每题公开说明最终货类/数量或集合最低配额、现金储备、原船保留、不借贷和停留星球；涉及船员时明确总人数包括飞行员。日期与随机种子固定；思考时间不流逝。没有规定额外船员目标的题目不隐含人员判分。

`parameters.native_fixture` 是唯一规范化初始化/目标文本，由可信 backend 原样写入私有 `fixture.txt`，原生 DataFile 解析。token 包括 `credits`, `mincash`, `crew`, `goalcrew`, `cargo "name" quantity`, `goal "name" quantity`, `basket "name" minimum`, `baskettotal quantity`。`goal` 的精确数量与 basket 货类不重叠；清仓由空目标表达。初始化货物是任务禀赋。原生 CargoHold 限制装载容量，Ship 限制床位。

模型仅操作原版 TradingPanel/HiringPanel。判分检查全部商品总量及各目标商品、实际账户余额、全过程贷款、同一原船、星球和指定船员数。私有遥测额外记录实时价格与货舱容量，用于作者验证；不提供给模型。

已完成 macOS 原生增量编译和完整 15/15 题真实桌面通关，最终运行目录统一以 `-author-outfits` 结尾；每题终态原生记录均有 `outfits_kept=true` 与相同的原始/最终设备 map。每条 reference 指向对应成功运行。固定版本 Rutilicus 价格已与原生实时价格及最终账户余额核对。私有作者工具 `scripts/author_transport_gui.py` 通过统一 Episode 与 PyAutoGUI 录制，逐帧保留截图、状态和结果；这是作者可行性证据，不是自主模型成绩。汇总见 `artifacts/v1-transport-desktop.json`，此前候选失败与旧判分记录保留。

构建：`gameworld build endless_sky`。列题：`gameworld tasks`。执行：`gameworld run TASK --reference`（仅已提供轨迹的任务）或 `gameworld serve TASK`。配置和存档分别放入每次运行的 private 目录；窗口为 1100×720 内容区。

v1 判分进一步要求最终已安装设备与起始 Shuttle 的原装配置完全一致（公开 instruction 同步说明），避免出售推进器等设备资助原本超预算的商品组合。原生桥在初始化缓存 `Ship::Outfits()`，终态比较完整 map，并输出私有 `outfits_kept`、原始和最终安装列表。GUI 改装功能仍保持原样，可调整后恢复。原有两题 ID 保留，但这项新增 v1 设备约束与早期历史运行明确区分，不修改历史记录；扩展后的完整 15 题另以新终态字段重放验证。
