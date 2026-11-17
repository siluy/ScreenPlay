# 剩余三款游戏的实验性文本接口

这次新增 Endgame: Singularity、OpenTTD、Enigma 的可运行原型，共覆盖原有 45 道任务的初始化入口。它们复用原生游戏、原任务和判分器。`text-symbolic` 继续作为条件名，另用 `experimental: true` 和 `interface_profile` 区分具体接口，避免把一个名称当作抽象程度的证明。

新增接口最初作为独立原型运行，原生验证、模型评测和人类研究分开记录。2026-11-03 的浏览器服务0.2.4已接入这45道文本题，并提供一键全选邀请；历史论文和旧45题配对统计不自动改写。

## 三种具体抽象

| 游戏 | 模型看到什么 | 模型选择什么 | 保留的流程与规则 |
|---|---|---|---|
| Singularity | 当前原生对话框的文字、按钮、可见列表行、滑条数值、输入框；禁用控件也明确标出 | `click(control)`、`set_value(control,value)`、`type_text(control,text)`、`wait` | 原窗口切换、滚动、行选择、确认、警告弹窗；原生 CPU 分配、研究、建造、资金、风险和时间推进 |
| OpenTTD | 当前受限面板；可移动的 25×13 地块地图、道路出口、车站与可见标牌；车辆或订单详情按面板提供 | 打开面板、选订单、进入前往模式并点车站、选 X/Y 建路工具并画一段路、启停或回库、等待 | 插入与删除逐条执行；建路按原生玩家命令收费并检查合法性；原车辆实际行驶、停靠、回库 |
| Enigma | 当前 20×13 盘面的地面和物体、小球位置、背包；翻开的石头才显示颜色 | `push(dx,dy)`、使用背包首项、轮换背包、等待 | 原生鼠标力、惯性、摩擦、碰撞、推箱、钥匙、开关、动画、死亡与配对判定 |

### Singularity：直接读取原生控件

初始盘面包含地区、研究、速度和资源显示。打开研究面板后，例如：

```text
Current panel: ResearchScreen.
[u2_1] button: BACK
[u2_6] row: Research Intrusion; selected=False; progress=0.0%
  Research Intrusion
  0
  [u2_7] slider: value=0, range=0..1
```

`set_value(u2_7, 1)` 只调整这个滑条，通过原生回调分配 CPU。模型仍要返回地图、选择速度、处理警告并等待。适配器没有新增自动补前置科技、建造整套设施或等待直到目标完成的动作。原游戏自带的 `Auto-build items` 按钮及其确认框保留；它本来就是原生 GUI 提供的较大粒度操作，不能将它描述为一次单设备购买。

控件 ID 每次观察更新，旧 ID 会被拒绝。列表只提供当前显示的行；滚动条与箭头仍需操作。文本输入一次替换一个字段，确认是另一步。菜单、保存、载入、退出、调试入口不开放。

边界：精确设置整数滑条值、精确读取文字和研究进度都是抽象增强。当前面板之外的背景窗口不一起序列化，因此也存在信息删减。此原型不是完整的桌面辅助功能树。

### OpenTTD：受限面板加地块对象

例如补一个缺口需要：

```json
{"type":"open_panel","panel":"road"}
{"type":"click","control":"build_x"}
{"type":"draw_road","x1":24,"y1":32,"x2":24,"y2":32}
```

补充订单需要先选择插入位置，再进入前往模式，最后点击一个当前地图内的车站：

```json
{"type":"open_panel","panel":"orders"}
{"type":"select_order","index":2}
{"type":"click","control":"go_to"}
{"type":"click_tile","x":32,"y":32}
```

执行走 OpenTTD 的玩家级 `Command::Post`，包含原生费用、资金检查和规则。没有使用仅供场景初始化的命令调用来代替玩家操作。道路每步可以是一段连续直线，类似一次拖动；模型负责选择端点和方向。订单每步只插入、删除或调整一条。

边界：面板由适配器定义，**不是原 GUI 窗口树的逐项序列化**。地图使用明确的可移动地块范围，不等于原截图的像素可见范围，也没有窗口遮挡。道路端点取整格，省去了原 GUI 的半格定位；没有地形编辑、购买车辆、建站、贷款、复杂订单与完整游戏菜单。这些删减和精度变化都必须纳入实验解释。

观察不包含判分器的道路缺口计数、历史停靠标志或目标完成度。道路上的“Repair road”来自原生可见标牌。模型可以观察当前停车或装载状态，但没有历史停靠查询工具。

### Enigma：文字盘面加原生推动

```text
Marble center: (9.50,6.50).
(2,6) oxyd: color hidden.
(17,6) oxyd: color hidden.
```

```json
{"type":"push","dx":-160,"dy":0}
{"type":"wait","duration_ms":1000}
```

`push` 是一次有界相对鼠标位移产生的力，范围为每轴 −300 至 300，按原游戏鼠标灵敏度缩放。它不是目标坐标，也不是走到目标或自动刹车。模型必须自己决定力度、方向、后续观察和等待。

配对石关闭时颜色隐藏；原生打开动画开始后的前 0.5 秒继续保守遮蔽颜色。重新关闭时不提供颜色记忆。原生钥匙图案可见时才给出图案编号；不提供开关或钥匙到门的内部连接。墙体按当前关卡中可见的 a 风格石头描述，不输出其内部“假配对石”类别。

边界：小球位置提供到 0.01 格的数值精度；物体与地面类型已经识别。连续鼠标轨迹被限制为单次推动，速度设置和其他菜单被裁剪。没有提供引擎速度向量、自动路径或物体触发接口。该实现仅支持现有 20×13 关卡，不宣称支持任意 Enigma 关卡。

## 时间与预算

默认沿用各任务的原生决策预算；也可显式覆盖。OpenTTD 普通输入消耗 8 个更新机会，Singularity 和 Enigma 为 6 个；等待分别按 30、33、10 毫秒向上取整，最长单次 5000 毫秒，受剩余模拟预算限制。结束和被接口拒绝的输入不推进模拟，但均消耗一次决策。

等待不等于保证游戏时间增长。Singularity 在研究或建造对话框内不会推进游戏时间，地图速度为暂停时也不会推进；警告窗口需要处理。Enigma 保留原生动画和物理更新。模型思考期间原生进程阻塞在下一个请求上。

这些规则对应当前原型，不能直接沿用旧 45 题固定 100 次决策的实验统计。要比较新 GUI／文本条件，需要另行冻结双方预算、动作定义和信息范围。

## 本地试用

先具备仓库已有的三款原生构建；文本构建复用其编译对象，在独立目录链接新程序。Enigma 文本序列化还复用已固定版本的 OpenTTD 源码中随附的 JSON 头文件。

```sh
.venv/bin/python scripts/build_text_remaining.py all
.venv/bin/python scripts/run_text_remaining.py --task singularity-intrusion
.venv/bin/python scripts/run_text_remaining.py --task openttd-road-gap-1
.venv/bin/python scripts/run_text_remaining.py --task enigma-oxyd-pair
```

每次启动输出初始观察和动作定义；标准输入每行提交一个动作 JSON。输入结束会关闭游戏。交互证据保存在 `runs/text-prototype/`，私有引擎诊断保存在 `tmp/text-prototype-*`。当前入口使用无桌面窗口的驱动，关闭时等待子进程退出。

程序调用可使用 `gameworld_text.tatham.make_environment(task_id)`，与现有文本适配器共享 `observe()`、`step(action)`、`close()` 和 `build_request()`。浏览器服务0.2.4开放全部六项目的90道文本题，新增45题使用独立的邀请快捷选项；新邀请逐题保存原生决策预算，旧邀请不变。

## 已验证的范围

运行：

```sh
.venv/bin/python scripts/verify_text_remaining.py --phase all
```

证据位于 remaining-prototype-evidence/all.json (historical local artifact; not distributed)，每题初始观察、动作定义及验证轨迹在同目录。

- 三款全部 45 题：初始化未解、生成文本与工具请求、禁用解题动作被拒绝、零时长等待、未解结束。
- 18 条原生成功轨迹：OpenTTD 15 题全部覆盖，包括道路、加载策略、订单重建、三站停靠、停车与回库；Singularity 的 Intrusion 研究和欧洲基地建设；Enigma 的双石配对。
- 原生建路实际扣款，小球推动后继续滑行，研究面板等待不推进游戏时间。
- 原有 32 项回归测试通过。上述原生验证没有调用模型 API，也没有向桌面发送键鼠输入。
- 文本构建前后原 GUI 二进制哈希相同，记录在各自 `build/text_*/build_receipt.json`。

验证轨迹由作者编排，并在停止判断中读取私有原生状态。它们证明原型可执行和原生判分可达，**不是自主模型成绩，也不是三款全部任务的 GUI／文本轨迹等价证明**。Singularity 其余 13 题和 Enigma 其余 14 题尚未完成文本成功轨迹验证；这 27 题目前仅完成初始化等接口检查。

## 单独的模型连通性检查

`scripts/check_remaining_text_gateway.py` 使用此前保存的 Sankuai 配置，按模型并行、每个模型按游戏顺序检查。每款游戏只要求一个明确指定的动作，检查请求认证、工具格式、模型返回与原生执行；不测完整任务成功率。DeepSeek 和 Sonnet 沿用各自此前验证过的参数兼容处理。

```sh
.venv/bin/python scripts/check_remaining_text_gateway.py
```

请求与结果放在独立的 `research/text-ablation/remaining-connectivity-*` 目录。认证值从本机 `.env` 读取，仅用于原 endpoint 的认证请求头，不进入模型提示或报告。HTTP 429 等服务错误单独记录，不能计作游戏失败。
