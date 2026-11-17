# pysolfc

原版 PySolFC/Tk FreeCell。使用官方 cardset-2000（牌面 GPL-2.0-or-later）及原版牌对象、拖拽、撤销与完成判断。12 张残局基础牌堆各 10 张，16 张残局各 9 张，全部 52 张牌都存在。需要先移走阻挡的国王，再把同花色牌升序放入基础牌堆。

初态是作者设计的残局，不宣称是原版随机牌局的完整通关。运行中不自动移动牌；提示、演示、换局和读档入口被禁止。界面缩放、默认牌面与个人目录固定。使用原生 Z 键撤销。仅跳过与本包 French-card 任务无关的牌类缺失提示，保留原生游戏画面。

源码版本与素材许可见 source.json 和 UPSTREAM-*。实际桌面验证总览见 ../../六款游戏接入.md。

构建：`gameworld build pysolfc`。使用 `gameworld tasks` 查看任务 ID，再运行 `gameworld run TASK --reference` 或 `gameworld serve TASK`。

第一版现含15道FreeCell作者局面，easy/medium/hard各5题；旧12/16张题ID保留。显式布局支持不同花色基础堆进度、自由格预占、无空列、多层阻挡与合法序列转移。逐题结构与证据边界见 [AUTHORING.md](AUTHORING.md)。难度是作者预估，尚待模型/人类标定。

15题均已完成真实桌面参考重放，包括三道多牌序列转移题；全程沿用原生移动规则与 isGameWon 判定。当前逐题记录见 ../../artifacts/v1-acceptance.json。
