# 人类入口 HTTP 接口

所有写请求使用 JSON、`X-Study-Request: 1`，且 Origin / Host 必须匹配配置。登录后由 HttpOnly、SameSite=Strict cookie 鉴权；不通过 URL query 传令牌。接口不提供工作区文件浏览、模型 API 或任意代码执行。

| 方法与路径 | 权限 | 内容 |
|---|---|---|
| `GET /api/about` | 公开 | 版本与支持任务数 |
| `POST /api/login` | 公开，限速 | `{kind: participant或admin, code}` |
| `POST /api/logout` | 会话 | 注销当前登录，不暂停当前任务 |
| `GET /api/session` | 会话 | 受试者进度及当前公开观察，或管理员角色 |
| `POST /api/consent` | 受试者 | `{accepted: true}` 阅读确认 |
| `POST /api/attempts` | 受试者 | 显式开始下一未评分题；已有当前题时返回它 |
| `POST /api/attempts/<id>/actions` | 该次作答所属受试者 | 单个动作与幂等编号 |
| `GET /api/attempts/<id>/history` | 该次作答所属受试者 | 最近5个盘面与全部动作文本 |
| `POST /api/pause` | 受试者 | 暂离；保留当前盘面、步数和剩余时间 |
| `POST /api/resume` | 受试者 | 继续暂离；已退出者须 accepted=true 明确重新参与 |
| `POST /api/withdraw` | 受试者 | accepted=true 结束参与；旧空请求兼容为暂离 |
| `GET /api/admin/catalog` | 管理员 | 90题公开目录、文本分组及邀请预设，不含参考解 |
| `POST /api/admin/invitations` | 管理员 | 编号、任务ID列表、界面条件和顺序种子 |
| `GET /api/admin/overview` | 管理员 | 参与进度、逐题正误／秒数／步数，以及单人／全部、项目／游戏／难度统计 |
| `GET /api/admin/results.csv` | 管理员 | 每位受试者的每道分配题一行，含未评分状态 |
| `GET /api/admin/summary.csv` | 管理员 | 分类与全部均值、正确率及各项有效样本数 |
| `GET /api/admin/export.csv` | 管理员 | 每次attempt的表格结果 |
| `GET /api/admin/export.json` | 管理员 | 协议、分配、attempt和动作时间记录 |

统计的计时、正误、重试和缺失值定义见 [人类作答数据说明](human-data.md)。

动作请求示例：

```json
{
  "request_id": "browser-generated-unique-id",
  "observation_id": 0,
  "action": {"type": "slide", "row": 3, "column": 3}
}
```

网络结果不确定时重传完全相同的请求。不得生成新编号重放同一个点击。服务端在原生输入前持久化动作意图；同编号不同内容返回409，旧观察返回409，非本人的attempt返回404。未知原生执行结果会终止为未评分中断。

浏览器只可使用返回的动作schema。图片动作复用 `gameworld.protocol`，文本动作复用 `gameworld_text` 的各原生适配器。最终是否成功由原生规则判定；前端的“结束”不是成功声明。

参与状态请求包含 `request_id`、`attempt_id`（题间为null）、`revision`（来自participant.control_revision）以及可选 `accepted`。同编号同内容重传返回当前状态，不重复操作；旧版本号拒绝，防止延迟请求覆盖新的参与选择。永久评分不受暂离／恢复影响。
