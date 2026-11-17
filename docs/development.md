# 开发与研究部署

## 一个版本，两种工作流

ScreenPlay 浏览器服务 0.2.4 的参与作答、研究管理和开发指南属于同一代码树与同一版本。角色权限用于保护会话与研究数据，不用于建立不同发行版。受试者浏览器无需安装游戏；开发者和研究负责人在同一源码工作区中运行服务。

## 主机准备

当前原生图片后端经过验证的平台是 **macOS**，需 Python 3.12、uv、Git、Xcode Command Line Tools 和 Homebrew。浏览器客户端不依赖 macOS。源码需以可编辑方式运行；当前发布物是源码包，未提供打包好六款原生游戏的独立桌面安装器。

```sh
uv sync --locked --extra native-games
uv run gameworld build tatham
# Tatham 的图片和文本题均已具备运行条件。
uv run screenplay-human serve --data runs/human-study --port 8790
```

服务默认只绑定 `127.0.0.1`。启动信息给出管理口令文件的位置，内容不会显示在页面或请求日志中。

构建其他项目所需的本机库与现有构建流程：

```sh
brew install sdl2_image sdl2_mixer sdl2_ttf xerces-c openal-soft pkgconf mad minizip libpng xz lzo
uv run gameworld build openttd
uv run gameworld build singularity
uv run gameworld build pysolfc
uv run gameworld build enigma
uv run gameworld build endless_sky
uv run python scripts/build_text_endless.py
uv run python scripts/build_text_remaining.py all
uv run gameworld doctor
```

`build` 会按 `game_packages/*/source.json` 获取固定上游版本，在独立准备目录应用适配补丁。Endless Sky 文本驱动复用原生构建对象，需要先完成其 GUI 构建。构建可能需要较长时间和较大的本地缓存；平台动态库由主机提供。所有上游许可随游戏包保存。

图片测试需为实际启动服务的终端开启屏幕录制与辅助功能。图片主机应保持桌面解锁，并专门用于当前作答；全局桌面锁确保一次只有一个图片任务使用原生桌面。程序不会自动解锁设备。每个作答进程存活期间使用临时 `caffeinate` 保护，进程结束即释放。

## 创建研究与分配任务

```sh
uv run screenplay-human serve --data runs/study-001 \
  --decisions 100 --wall-seconds 3600 --text-workers 4 --port 8790
```

1. 打开 `/admin`，使用 `runs/study-001/admin-token.txt` 中的管理口令登录。
2. 选择任务、图片／文本／混合条件，填写匿名编号如 `P001` 和顺序种子。
3. 本轮新增文本题可直接点击“全选新增 45 道文本题”；系统会切换到文本条件，选择 Singularity、OpenTTD、Enigma 各15题。原有45题仍可单独选择。
4. 保存生成的邀请码或链接，交给对应受试者。邀请链接的代码在 URL fragment 中，页面读取后会移除。
5. 从管理页查看进度并导出 CSV / JSON。导出不含邀请码、登录令牌、原生私有状态或图片二进制。

同一种子重现同一任务顺序。混合条件只使用支持两种接口的题目，以种子的奇偶性决定首种接口，然后逐题交替；同一个邀请不重复分配同一任务。它是分配工具，不替代研究者对样本、顺序和条件平衡的设计。

研究目录的原创建协议与任务定义固定，已有邀请码不会改写。0.2.4 对新分配的45道新增文本题，将原任务的100–360次决策上限逐题写入邀请计划（`assignment_protocol=new-text45-task-native-v1`）；旧邀请、原有文本题和图片题继续使用原研究上限。导出逐题包含 `max_decisions` 和 `assignment_protocol`，比较数据时保留这一差别。其他协议变更或任务定义变更仍应使用新研究目录。

## 让其他机器的浏览器访问

使用固定 Cloudflare 地址的逐步操作与 Windows 方案比较见 [远程作答说明](remote-access.md)。

使用专用 macOS 主机运行原生游戏，浏览器连接应用。显式指定客户端实际使用的 origin：

```sh
uv run screenplay-human serve --data runs/study-001 \
  --host 0.0.0.0 --port 8790 --public-origin https://study.example.org
```

在可信实验室网络或由负责人管理的 HTTPS 反向代理后部署，代理保留公开的 Host。应用检查精确 Host 和 Origin，不开放任意 CORS；HTTPS origin 会使用 Secure cookie。路径保持根路径 `/`，不支持未配置的路径前缀。原生主机具备本地桌面权限，浏览器不会获得任意文件或执行命令接口。

## 数据与恢复

```text
runs/study-001/
  admin-token.txt             管理口令，权限600
  study.sqlite3              邀请摘要、会话摘要、任务、动作意图与结果
  task-catalog.snapshot.json  研究固定题目快照（主机私有）
  attempts/<attempt-id>/
    observations/            HTTP公开观察的不可变快照
    native/                   原生截图、执行轨迹和私有判分
    human_result.json         本入口的最终结果与终止原因
```

管理员数据目录默认权限700，参与者只访问自己的会话。动作意图先持久化再送入原生进程；操作编号相同但内容不同会拒绝，基于旧观察的新动作也会拒绝。服务重启不会重放不确定动作，而是保留旧 attempt 为未评分，等待显式重新开始。退出研究属于未评分中断；目标、原生规则、动作预算及时间预算形成正式结果。

计时由服务端单调时钟维护，从首个盘面就绪开始；思考、断线和页面关闭都计入时间。已在时限内接收的原生动作会先取得回执，再检查下一步是否超时。任务之间不计时。GUI 和文本的状态表达与动作词表不同，比较时应记录界面条件，不能解释为纯智力因果差异。

## 开发结构

| 路径 | 职责 |
|---|---|
| `src/screenplay_human/static` | 同版本的参与、管理和开发页面 |
| `src/screenplay_human/study.py` | 分配、持久化、权限、动作去重、预算、退出 |
| `src/screenplay_human/runtime.py` / `worker.py` | 每次 attempt 的独立原生进程与有界 IPC |
| `src/gameworld` | 现有图片执行与原生判分 |
| `src/gameworld_text` | 现有文本观察和受限语义动作 |
| `game_packages` | 固定源版本、90道任务、适配补丁、参考轨迹、上游许可 |

新增游戏需要定义公开目标与规则、可信原生判分以及有限动作。浏览器端不得直接执行原生命令、修改结果或提供参考解。`Study._public` 是明确的公开字段白名单；新增观察字段需确认它属于被试可见信息。

## 验证流程

```sh
uv run pytest -q
uv run screenplay-human serve --data runs/human-validation --validation
uv run python scripts/verify_human_portal.py \
  --admin-token-file runs/human-validation/admin-token.txt \
  --output runs/human-validation/native-text-verification.json
```

`--validation` 将操作者验证与正式人类研究数据分开标记。验证脚本只接受该模式，默认覆盖八类文本玩法的原生操作、未解完成、重复请求和公开字段边界；加 `--all-new-text` 可逐一验证全部45道新增文本题。图片作答还应从浏览器实际点击／拖动，核对原生窗口截图与结果。已有回归测试覆盖跨受试者隔离、管理员权限、Host/Origin、动作去重、断线恢复、闲置超时与桌面容量。

本机发布前验证范围见 [validation.md](validation.md)。这些是软件验证，不是正式受试者成绩。

## 发布同一版本

```sh
uv run python scripts/package_release.py --output dist/screenplay-bench-0.2.3
```

发布脚本使用文件允许列表，生成一个源码目录及一个 zip，参与者与开发者使用相同版本。包中保留原生执行器、任务和开发测试，不包含本机环境文件、密钥、构建缓存、研究数据、模型原始轨迹或私人杂项。生成的 `RELEASE-MANIFEST.json` 列出文件与版本。开发工作区的现有论文和历史结果保持在原位置。
