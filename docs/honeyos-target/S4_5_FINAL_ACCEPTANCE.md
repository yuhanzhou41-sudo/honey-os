# HoneyOS Phase S4.5 — 最终验收报告

**结论: DONE / FROZEN（本地冻结，未 push / merge / deploy）**

本报告是 `S4_5_USER_UNDERSTANDING_GRAPH.md` 的验收附录，记录从
`11081124` 开始的最终端到端验收、缺陷修复与冻结。

## 1. 基线与提交

| 项目 | 值 |
|---|---|
| 起始 HEAD | `11081124` |
| 本轮新增提交 | 见 §13（本地冻结提交） |
| S4 基线 | `dff89780` |
| 分支 | `feat/s4-5-user-understanding-graph` |
| push / merge / deploy | 均未执行 |

起始时 `git worktree list` / `git status` 确认工作树 clean。

## 2. 本轮实际修复的问题

**生产缺陷（P0）：emotion hook 丢弃异步 U2 同批次写入。**
`honeyos/companion/emotional_imprint.py::emotion_imprint_hook_factory` 的
hook 是同步函数，却调用（S4.5 已改为 async 的）
`GatewayRunner._honeyos_u2_post_completed` 且未 await，返回的协程被丢弃。
后果：真实 Gateway 路径（`_schedule_honeyos_memory_distillation` 先装 emotion
hook，再通过 `downstream_holder` 热接 U2）中，**U2 同批次写入被静默跳过**。
单测因直接注入 hook 而未暴露。

修复：hook 保持同步（兼容 `test_s4_emotional_imprint` 的既有契约），但把
downstream 的返回值原样返回；`MemoryDistiller` 已 `inspect.isawaitable` 后
await 该返回值，从而真正执行异步 U2 producer。同步 downstream（旧测试）返回
None，行为不变。新增回归测试
`test_s45_e2e_acceptance.py::test_scenario_1b_emotion_hook_forwards_to_async_u2`
覆盖真实 Gateway 组合（emotion hook → async U2）。

其余为新增测试，无其他生产代码改动。

## 3. 八个端到端场景（Task A）— 8/8 PASS

测试文件：`tests/honeyos/test_s45_e2e_acceptance.py`。全部在隔离临时
`HONEYOS_HOME` + 临时 SQLite + fake extractor 下运行，无真实模型、无网络、
无 `~/.honeyos`。链路为 MemoryDistiller → continuity.db → U2 解析 →
（真实）`_honeyos_u2_post_completed` → `apply_proposal` → understanding_v2.db →
图谱 API handler。

| # | 场景 | 关键断言 | 结果 |
|---|---|---|---|
| 1 | 完整自动整理 | 触发整理、模型调用=1、原生记忆落库、`operation_indices`→真实 memory_id、U2 经 apply_proposal 写入、API 可读 | PASS |
| 1b | 真实 hook 组合 | emotion hook 转发到 async U2，标签真正落库 | PASS |
| 2 | 共同经历更新已有理解 | 同义标签不重复、support 证据+1、来源 ID 正确、重放不再调用模型 | PASS |
| 3 | 一条记忆关联两标签 | 两标签均存在、记忆只存一次、双向可查 | PASS |
| 4 | 用户手动忘记 | status=forgotten、图谱不返回证据正文、召回不注入、生理不能复活、迟到 U2 被拒、重放不复活、标签忘记≠记忆忘记 | PASS |
| 5 | 待续完成 | 完成后从 list_active/召回消失、U2 不收 open_loop 证据、不新建 Study 计划 | PASS |
| 6 | 生理召回 + S4 印记 | 先准入、加权有界、known 进位、unknown 不伪装、遗忘/已完成不出现、无关高情绪不越门槛、印记标注「当时」、重复召回不强化 | PASS |
| 7 | DeepSeek + Study 外来历史 | 来源身份不变、纯相关、无当前生理、共享硬上限、无命中不注入、被禁来源不注入、不能成为 U2 证据 | PASS |
| 8 | 真实图谱数据流 | 节点/边合法、详情可读、时间字段/S4 印记、支持/反证区分、忘记标签隐藏正文、解除关系刷新正确、标签忘记不改记忆状态 | PASS |

运行结果：`9 passed`（含 1b）。

## 4. 真实浏览器验收（Task B）— PASS

环境：WSL 内以临时 `HONEYOS_HOME` 启动隔离服务器（独立端口，不影响任何在运行
服务），提供**真实构建产物 `react_dist`** + **真实 understanding 路由** + 真实
SQLite；仅补 `/api/companion/settings` 与 `/health` 两个桩以通过模型配置守卫。
浏览器：环境自带真实浏览器自动化（Windows 端，经 `localhost` 访问 WSL 服务，
已验证连通）。未在生产系统安装服务。

| 检查项 | 结果 |
|---|---|
| 导航进入「Honey 对我的理解」 | PASS |
| 图谱加载真实 SQLite 数据（3 标签 / 4 记忆） | PASS |
| 标签与记忆节点可见 | PASS |
| 支持（实线）/反证（虚线） | PASS |
| 鼠标平移 / 滚轮缩放 / 重置视图 | PASS |
| 点击标签查看详情（类别/状态/支持·反证） | PASS |
| 分类筛选（价值取向仅留对应标签） | PASS |
| 时间筛选（近 30 天） | PASS |
| known 印记显示「历史情绪印记：温暖」 | PASS |
| unknown 显示「历史情绪印记：未知」（不伪装） | PASS |
| 忘记标签（确认后变「(已隐藏)」） | PASS |
| 解除一条关联（反证 1→0） | PASS |
| 页面刷新后数据仍正确（持久化） | PASS |
| 空状态（共 0 条 / 还没有形成任何用户理解标签） | PASS |
| API 错误状态（「图谱加载失败。请确认 HoneyOS 服务可用后重试。」，不崩溃） | PASS |
| 浏览器控制台错误 | 无 |
| 小窗口 ~800×600 布局 | 正常 |

数据库侧复核（非仅按钮）：忘记标签后 `labels.state='user_suppressed'` 且正文
不再由 API 返回；解除关系后 `evidence` 行确实删除（反证归零）；被忘记标签对应
的原生记忆仍为 `active`（标签忘记 ≠ 记忆忘记）。

**范围说明（非阻塞）：** 交付的最小图谱 UI（见冻结文档 Task F 范围）中，记忆
节点为展示态、不支持点击；「来源及关联」通过点击标签后的详情面板呈现（记忆
kind / 时间 / 印记 / 所属标签）。「时间轨迹」由时间筛选 + 每条记忆时间字段
体现，无独立时间轴控件。二者不属本轮交付范围，未额外扩建 UI。

## 5. 旧窗口 6 / 40 核对（Task C）— 无静默丢失，未改代码

只读审计 `MemoryDistiller`（`_prepare` / cursor / source_hash / pending /
fallback / daily cap / retry）。结论：**不存在已合格材料的静默丢失**。

- cursor 仅在完成后推进到本批最后一条已处理消息，绝不超过未处理区间。
- 不足 `min_tail_messages=6` 的尾部保持 pending，下次合法整理（窗口增长或
  重新进入该会话）时处理，先前消息不被跳过。
- 超过 `max_batch_messages=40` 的剩余部分，下次合法触发继续处理，不永久遗漏。
- 失败不推进 cursor，`source_hash` 幂等复用同一次 run，不重复生成记忆。
- 每日上限触发时 `_prepare` 返回 None（deferred），cursor 不动，次日可续。
- 后台 `record()` 对已 forgotten 匹配项返回 None，重试不复活用户忘记内容。

新增测试 `tests/honeyos/test_s45_old_window_thresholds.py`（9 个：1/5/6/20/40/
41/80、日限 deferred、失败重试不重复、忘记再审不复活）全部通过。未改动
20 / 6 / 40 任何原值，未改正常 20 条触发语义，未影响 U2 同批与待续。

## 6. DeepSeek + Study 外来历史共享硬上限（Task D）

审计结论：外来历史只有一个**来源无关**检索器
`CognitiveMemoryShadowRetriever`（对整池 external episodes 统一排序），因此
`max_results=3` / `char_budget=900` 天然是跨来源**共享**上限；最终上下文合并
`build_silent_memory_context` 再收敛到 3 条 / 700 字符 payload。全程不读取
Honey 当前生理状态（attention=0），无匹配返回空。

Study：**不存在**自动进入聊天上下文的外来历史检索入口——Study 只做两件事：
(a) 用户显式引用的学习资料阅读（`study/chat_reading.py`，用户主动，非静默
检索）；(b) 对相关 cognitive episodes 的 salience 加成，不改来源身份、不引入
生理。未伪造 Study 接入。若未来出现 Study 外部来源，会同处同一 source-agnostic
检索器与同一硬上限。

新增测试 `tests/honeyos/memory/test_s45_external_history_shared_budget.py`
（5 个：跨来源共享 3/900、跨来源去重、被禁来源不注入、无命中为空、上下文
3/700）全部通过。

## 7. 用户遗忘、待续、S4 印记回归

- 用户遗忘：continuity `status` / cognitive tombstone / U2 `user_suppressed`
  仍为权威；图谱、召回、后台重试均尊重（场景 4；浏览器忘记/解除复核）。
- 待续：完成/隐藏/解决状态机未改；完成后从 `list_active` 与召回消失；
  U2 不纳 open_loop（场景 5）。
- S4 印记：`context_for_lane` 仅对 known 追加「历史情绪印记 / 当时状态」提示，
  有界 boost 上限 0.12；unknown 无提示、不被当作已知（场景 6；浏览器印记显示）。

## 8. 历史失败基线对照（Task E）

在相同 Python 环境、相同依赖、相同 `pytest` 参数与 `--import-mode=importlib`
下，对比 `dff89780` 与当前 HEAD 全量 `pytest tests`：

| | 基线 dff89780 | 当前 HEAD |
|---|---|---|
| failed | 24 | 23 |
| passed | 1263 | 1297 |
| skipped | 18 | 18 |

**新增回归：0。**

归因（全部 PRE-EXISTING，基线同样失败且原因一致）：

| 组 | 用例 | 基线 | HEAD | 原因 | 归属 |
|---|---|---|---|---|---|
| campus | test_exams / test_timetable::test_refresh_imports_and_lists | FAIL | FAIL | 既有 | PRE-EXISTING |
| gateway shadow | test_turn_router_shadow_integration (5) / _v2 (3) | FAIL | FAIL | 既有 | PRE-EXISTING |
| branding/cli/config/install/distribution/surface | test_branding, test_cli_main, test_config, test_distribution_contract(2), test_install_script, test_installer, test_repository_surface | FAIL | FAIL | 既有 | PRE-EXISTING |
| understanding_v2 | test_transports(2)（`compose_user_api_content()` 签名漂移） | FAIL | FAIL | 既有 API 漂移 | PRE-EXISTING |
| understanding_v2 | test_u2_engineering(3)（期望旧的独立 U2 producer LLM 调用 `u2_calls==1`，与已冻结的「U2 二次调用=0」冲突；且未初始化 labels 表） | FAIL | FAIL | 冻结设计前的陈旧测试 | PRE-EXISTING |
| 偶发 | test_continuity_gateway::test_gateway_tracks_distillation_as_non_blocking_background_work | FAIL（全量顺序相关） | PASS（本轮全量） | 顺序/隔离敏感 | FLAKY |

说明：上一轮「899 passed / 18 failed」是排除了 `understanding_v2` 重依赖目录的
子集；本次全量运行首次暴露上述 5 个 pre-existing 失败（基线亦然）。未删除测试、
未放宽断言以绕过。

## 9. 前端检查

`export PATH=$HOME/.nvm/.../v22.23.2/bin` 后：

- `npm run typecheck`：通过
- `npx vitest run`：**94 passed**（26 文件）
- `npm run build`：通过（产物与已提交 `react_dist` 一致，无 diff）

## 10. 模型调用 / token 成本

无真实付费模型调用；以下为**测试模型测量 + 静态推导**：

| 项目 | 结果 |
|---|---|
| 普通聊天新增必经 LLM 调用 | 0 |
| MemoryDistiller 每批调用 | 1（场景 1/2 实测 extractor 计数） |
| U2 二次 LLM 调用 | 0（同批次解析，场景 2 重放实测 0 次） |
| 打开图谱 | 0（纯 SQLite） |
| 外来历史检索 | 0（无生成式摘要） |
| 旧窗口补偿 | 未新增调用路径，沿用原每日预算 |
| 本轮真实 token 消耗 | 0（`max_tokens=2000` 仅为输出上限，非实际消耗） |

## 11. 实际修改文件

```
honeyos/companion/emotional_imprint.py                     # 生产修复：转发 async downstream
tests/honeyos/test_s45_e2e_acceptance.py                   # 新增：8 场景 + hook 组合（9）
tests/honeyos/test_s45_old_window_thresholds.py            # 新增：6/40 边界（9）
tests/honeyos/memory/test_s45_external_history_shared_budget.py  # 新增：共享上限（5）
docs/honeyos-target/S4_5_FINAL_ACCEPTANCE.md               # 新增：本报告
docs/honeyos-target/S4_5_USER_UNDERSTANDING_GRAPH.md       # 更新：冻结状态
```

## 12. 数据库兼容与回滚

- 无 schema 变更；理解库沿用 `understanding_v2.db`，continuity 沿用既有表 +
  S4 sidecar（CREATE IF NOT EXISTS）。无需迁移。
- 回滚：`git revert <freeze> [<freeze2>]`；或
  `git checkout feat/s4-longterm-memory-emotional-imprint` 回到 S4。本次修复仅
  改变 hook 返回值语义，可独立 revert。

## 13. Git 最终状态

| 项目 | 值 |
|---|---|
| 分支 | `feat/s4-5-user-understanding-graph` |
| 冻结提交 | 见本轮 `docs(s4.5): final acceptance + hook fix` 提交 |
| 工作树 | clean |
| push / merge / deploy | 未执行 |

## 14. 仍未完成的非阻塞限制

1. 23 个历史失败维持 PRE-EXISTING（基线同源）；其中 5 个 `understanding_v2`
   测试编码的是 S4.5 冻结前已被替换的旧 U2 producer 设计，未改写它们以免
   重建 U2 / 扩大范围。
2. 图谱记忆节点为展示态；无独立「时间轨迹」控件（见 §4 范围说明）。
3. `DELETE .../evidence` 只删除关系行，不重算标签 grade/state（显示反证 0 时
   状态可能仍为 disputed）。属既有轻量行为，非安全问题，未扩展。

> 以上限制均不涉及用户遗忘、来源权限、U2 二次调用、待续状态机或模型预算，
> 不阻塞冻结。
