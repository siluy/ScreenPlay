# 从作答走向开发

受试者、研究负责人和开发者使用同一个版本。请先完成正式分配的作答，再阅读题目中的参考轨迹或开始改题。

1. 按 [开发说明](docs/development.md) 克隆、安装并构建需要的原生项目。
2. 使用新的 `runs/` 目录加 `--validation` 验证更改；不要在正式研究目录修改任务、预算或结果。
3. 分支名建议使用 `codex/` 或团队约定的功能名。提交说明应交代行为变化和实际验证范围。
4. 涉及原生动作或判分的修改，检查成功、未完成、无效动作及中断；涉及浏览器的修改，还应在页面中完成真实操作。
5. 运行 `uv run pytest -q` 与 `node --check src/screenplay_human/static/app.js`。只有需要原生游戏的验证才需要构建缓存和桌面权限。
6. 提交前核对文件列表。口令、邀请码、模型配置密钥、受试者数据及本机路径不能进入仓库。

共享源码包含完整任务和原生接口；参与作答、管理和开发页面分别位于 `/`、`/admin` 与 `/developer`。新增公开观察字段时检查 `Study._public`，避免将参考解或私有判分状态传给受试者。

发布使用 `scripts/package_release.py`，只生成一个共享源码包，并记录每个文件的 SHA-256。已有输出目录不会被覆盖。

Original contributions are licensed under MIT; retain all upstream notices and licenses.
