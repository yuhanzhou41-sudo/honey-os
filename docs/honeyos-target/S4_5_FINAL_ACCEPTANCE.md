# HoneyOS Phase S4.5 — 最终验收报告

**结论: DONE / FROZEN（本地冻结，未 push / merge / deploy）**

本报告是 `S4_5_USER_UNDERSTANDING_GRAPH.md` 的验收附录，记录从
`11081124` 开始的最终端到端验收、缺陷修复与冻结。

## 1. 基线与提交

| 项目 | 值 |
|---|---|
| 起始 HEAD | `11081124` |
| 本轮新增提交 | `093b656f`（hook 修复 + 验收测试）→ `86a8110a`（验收文档冻结）→ `d22e7daf`（记录冻结哈希）→ `cded7b39`（Round 2 缺陷修复 + 功能补齐）→ 本提交（Round 2 文档冻结） |
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

## 2b. 本轮追加修复（d22e7daf 之后，Round 2）

在上一冻结 `d22e7daf` 基础上，针对 S4.5 全部已知缺陷与未完成原定功能逐项修复
与补齐。以下均为**真实缺陷或原定未交付项**，未为通过测试而放宽或删除断言。

### 2b.1 U2 标签证据与状态同步（Task 1）

解除关联、遗忘来源、反证变化、来源撤回后，标签 grade/state 必须随有效证据
变化重新评估，不得保留已失去依据的高可信状态；用户手动遗忘的标签不得自动
复活。

- `honeyos/understanding/u2_maintenance.py`
  - 新增 `recompute_label(store, label_id, continuity_db_path, actor)`：以
    `_valid_evidence_rows` 重新取**当前仍有效**的证据（指向已遗忘/归档/不
    存在 continuity 记忆的 `continuity:` 引用被判为孤儿并修剪），再用既有
    `_grade` 规则重算 grade/state；仅在确有变化时归档旧版本到
    `label_versions` 并 `revision+1`。`USER_SUPPRESSED` 标签直接跳过，绝不
    复活。
  - 新增 `recompute_labels_for_memory(...)`（actor=`source_withdrawal`）与
    `reconcile_store(...)`：覆盖「单条记忆变化」与「全量扫描兜底」两种入口。
  - `apply_proposal` 接受 `continuity_db_path`，写入后用同样的有效证据集合
    推导 grade/state 并修剪孤儿，使撤回的来源无法继续抬高置信度。
  - `_archive_current` 在 INSERT 前执行 `CREATE TABLE IF NOT EXISTS
    label_versions(...)`（schema 与 `u2_store.py` 一致），保证存量库/最小夹
    具缺表时重算永不失败。
- `honeyos/companion/continuity.py`：新增 `_recompute_u2_for_memory`
    （fail-open，U2 错误绝不阻塞 continuity 变更），在 `change_status` 把
    记忆置为 `forgotten`、以及后台 90 天自动归档低重要 episode 时触发
    `recompute_labels_for_memory`。用户遗忘的记忆所支撑的标签会随之失去该
    条证据并被重算，但 `user_suppressed` 标签不复活。
- `honeyos/gateway/run.py` 与 `honeyos/understanding/u2_pipeline.py`：同批
    U2 写入与 `recover_pending_jobs` / `recover_saved_response` 恢复路径均
    透传 `continuity_db_path`，使证据解析与重算始终针对真实 continuity 库。
- 复用既有 U2 policy 与状态规则，未新增第二套删除机制；解除关联只删
    evidence 关系行，随后调用 `recompute_label`（actor=`user_detach`）。

**本轮发现并修复的真实生产健壮性缺陷（P1）：`label_versions` 表在存量库缺失
时导致详情接口 500。** `label_versions` 由 `UnderstandingStore.initialize()`
创建（仅 `result.understandings` 非空时触发，`run.py`），但最小测试夹具与
S4.5 之前已升级的存量生产库都没有该表 → `recompute_label` 的 INSERT 与
`get_understanding_label` 的 SELECT 抛 `OperationalError: no such table`，
任何已存在 home 的标签详情都会 500。修复见上（写侧懒建表 + 读侧 try/except
降级为空时间轨迹）。

回归测试：`tests/honeyos/understanding_v2/test_s45_evidence_state_recompute.py`
（含 `test_label_detail_exposes_versions_and_masks_body_after_forget`：
`GET /labels/{id}` 返回 `versions`，forget 后正文与所有版本快照均遮罩为
`""`）。

### 2b.2 U2 是否真正参与后续聊天（Task 2）

核实结论：**合法标签目前不被注入普通聊天上下文（fail-closed，有意为之），
本轮不擅自启用。** 证据见 `docs/understanding_v2/R5_FINAL_CONTEXT_AUDIT.md`：

- 生产 `compose_user_api_content(content, ext_prefetch_cache, plugin_user_context)`
  为 3 参（第 4 个 U2 sidecar 参已在 S4.5 移除），生产调用点
  `turn_context.py` / `conversation_loop.py` 不传 U2。
- `wrap_understanding` + `build_memory_context_block` 仍保留「有限、可能不
  准确」标记，仅被测试与 `eval_understanding_v2.py` 使用，**从未进入生产聊
  天上下文**。
- 权限与 token：U2 上下文读取走 owner 作用域过滤；若未来启用需单独的产品+
  安全授权（token 预算、准确性边界、用户可见性），不在 S4.5 修复范围内擅
  自解除安全限制。
- 证明测试：`tests/honeyos/understanding_v2/test_s45_u2_not_injected_into_chat.py`
  断言生产上下文构建不包含 U2 标签。

### 2b.3 图谱原定交互补齐（Task 3）

记忆节点从展示态升级为可点击详情，并补独立「时间轨迹」。复用当前 React 页
面、API 与既有记忆管理操作，未创建第二套删除机制。

- `frontend/src/features/understanding/UnderstandingPage.tsx`：点击记忆节点 →
  右侧面板展示完整合法详情（正文、会话、发生时间、known 情绪印记）与
  「相关标签（N）」（被 ≥2 个标签引用的记忆可跨导航跳回对应标签详情）。标
  签详情新增独立**时间轨迹**：标签形成、获得支持、反证、以及每次修订
  （`actor` + 修订前 state/grade），按时间倒序。
- `frontend/src/api/understanding.ts`：`getLabel(id)` 读取 `versions` 字段。
- `honeyos/runtime/web_routers/understanding.py`：`GET /labels/{id}` 返回
  `versions`（来自 `label_versions`，forget 后正文遮罩为 `""`）；
  `DELETE .../evidence` 解除关联后调用 `recompute_label` 并在响应里返回
  `recomputed`。

### 2b.4 23 个历史失败逐项审计（Task 4）

基线 23 个失败全部 PRE-EXISTING（基线同源）。其中 5 个 `understanding_v2`
旧测试在本轮被审计并**更新断言（依据充分），未删除、未跳过**：

1. `test_transports.py` ×2：编码已废弃的 `compose_user_api_content()` 4 参
   签名（含 U2 sidecar）。S4.5 fail-closed 已移除第 4 参，生产签名为 3 参。
   重写为 3 参调用，保留传输往返不变式（accuracy 标记经
   `wrap_understanding`→`build_memory_context_block` 存活；多模态内容不被
   改写），并加注释引用 S4.5 决策。
2. `test_u2_engineering.py` ×3：编码 S4.5 冻结前「独立 U2 producer LLM 调
   用」旧设计（断言 `u2_calls==1`、`jobs==["completed"]`）。S4.5 把 U2 折
   叠进同批蒸馏（同一请求），故 `u2_calls` 应为 **0**，标签来自
   `result.understandings`（按 `operation_index` 解析，随后解析为
   `continuity:{id}` 引用）。
   - 更新 `_fake_extractor` 产出 `understandings` 数组；
   - 修正两处 `u2_calls` 断言 1→0；把已失效的 `jobs==["completed"]`（同批
     写入不建 job 行）替换为 `evidence==1` 计数断言；
   - 重写 `test_gateway_live_producer_failure_never_changes_distillation`
     → 改名 `..._u2_failure_...`，monkeypatch
     `u2_maintenance.apply_proposal` 抛错，断言蒸馏仍 `completed`
     （distiller `post_completed_hook` 外围 try/except 保证 fail-open）且零
     部分标签/证据行。

其余 18 个失败（campus ×2、turn_router_shadow ×8、branding / cli_main /
config / distribution_contract ×2 / install_script / installer /
repository_surface）与 S4.5 无关，单独列为未解决（见 §14），不越界扩展。

### 2b.5 Study 外来历史剩余需求（Task 5）

核实结论：**Study 无自动聊天检索入口是有意的范围排除，非故障、非未开发遗
忘、非待授权开关。**

- `honeyos/study/chat_reading.py` 为「范围优先 + 显式引用」阅读（仅当用户
  显式引用某资料时读取），不是自动聊天历史检索/注入入口。
- `honeyos/study` 被 `companion/`、`events/`、`gateway/`、
  `memory/runtime_shadow.py` 引用，但**不**在 `honeyos/agent/turn_context.py`
  或 `conversation_loop.py`（聊天上下文构建器）中，故 Study 资料从不进入通
  用聊天上下文。
- 与 `S4_5_USER_UNDERSTANDING_GRAPH.md` §3、§9.4 一致：保持原访问边界，未
  接入本图谱，未伪造接入。任何未来的自动注入都是独立的产品+安全决策，不得
  为「修复 S4.5」而擅自把全部 Study 资料注入聊天。

### 2b.6 真实浏览器复验（Task 6）

在隔离临时 home（`/tmp`，不触碰生产）+ 真实 `react_dist` + 真实 understanding
路由 + 真实 SQLite 上，以真实浏览器复验新增交互：

- 图谱加载：3 标签 / 5 记忆（其中 m5 被 2 个标签引用，用于「相关标签」）；
  SVG 节点显示 known 印记（踏实/温暖）。
- 标签详情：2 张证据卡片（正文、kind、发生时间、印记、「查看记忆详情 →」、
  「解除此关联」）；**时间轨迹**含「标签形成 / 获得支持 ×2 / 修订 r3·你解
  除了关联 / 修订 r2·系统重算可信度 / 修订 r1·distillation」，含 actor 与
  状态变化，倒序。
- 记忆详情：点击共享记忆 m5 → 完整正文 + 会话 + 印记 + **「相关标签
  （2）」**，可跨导航跳回任一标签详情。
- 用户遗忘：`POST suppress` 后 `GET /labels/{id}` → `suppressed=True`、正文
  空、3 条版本历史 body 全部遮罩为 `""`（真实服务器 API 验证；浏览器按钮
  走同一路径）。
- 未调用真实付费模型；未触碰生产数据库；未 push/merge/deploy。

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

**范围说明（已更新）：** 上一版冻结中记忆节点为展示态、无独立时间轴控件。
本轮（§2b.3）已补齐：记忆节点可点击查看完整详情与「相关标签（N）」，标签详
情新增独立「时间轨迹」（形成/支持/反证/修订，含 actor 与状态变化）。未创建
第二套删除机制，复用现有记忆管理操作。

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

| | 基线 dff89780 | 上一冻结 d22e7daf | 本轮最终 |
|---|---|---|---|
| failed | 24 | 23 | 18 |
| passed | 1263 | 1298 | 1314 |
| skipped | 18 | 18 | 18 |

**本轮新增回归：0。** 修复了 5 个 `understanding_v2` 陈旧测试断言（见 §2b.4），
其余 18 个失败与基线同源、均在 S4.5 范围之外（见 §14）。

归因（剩余 18 个 PRE-EXISTING，基线同样失败且原因一致；5 个本轮已修复）：

| 组 | 用例 | 基线 | HEAD | 原因 | 归属 |
|---|---|---|---|---|---|
| campus | test_exams / test_timetable::test_refresh_imports_and_lists | FAIL | FAIL | 既有 | PRE-EXISTING |
| gateway shadow | test_turn_router_shadow_integration (5) / _v2 (3) | FAIL | FAIL | 既有 | PRE-EXISTING |
| branding/cli/config/install/distribution/surface | test_branding, test_cli_main, test_config, test_distribution_contract(2), test_install_script, test_installer, test_repository_surface | FAIL | FAIL | 既有 | PRE-EXISTING |
| understanding_v2 | test_transports(2)（`compose_user_api_content()` 签名漂移） | FAIL | 已修复（§2b.4） | 更新为 3 参生产契约，保留传输不变式 | FIXED |
| understanding_v2 | test_u2_engineering(3)（期望旧的独立 U2 producer LLM 调用 `u2_calls==1`） | FAIL | 已修复（§2b.4） | 更新为同批 U2 契约 `u2_calls==0`，未删除/跳过 | FIXED |
| 偶发 | test_continuity_gateway::test_gateway_tracks_distillation_as_non_blocking_background_work | FAIL（全量顺序相关） | PASS（本轮全量） | 顺序/隔离敏感 | FLAKY |

说明：上一轮「899 passed / 18 failed」是排除了 `understanding_v2` 重依赖目录的
子集；本次全量运行首次暴露上述 5 个 pre-existing 失败（基线亦然）。未删除测试、
未放宽断言以绕过。

## 9. 前端检查

`export PATH=$HOME/.nvm/.../v22.23.2/bin` 后：

- `npm run typecheck`：通过
- `npx vitest run`：**94 passed**（26 文件）
- `npm run build`：通过（本轮补齐记忆详情/时间轨迹后重新生成 `react_dist`，新产物已随提交更新）

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
# —— Round 2（本轮：缺陷修复 + 原定功能补齐，提交 cded7b39）——
honeyos/understanding/u2_maintenance.py                    # 重算 grade/state；孤儿证据修剪；label_versions 懒创建
honeyos/runtime/web_routers/understanding.py               # GET /labels/{id} 返回 versions（forget 遮罩正文）+ 缺表容错；detach 后重算
honeyos/companion/continuity.py                            # 记忆被遗忘/自动归档后触发 U2 重算（fail-open，不复活 user_suppressed）
honeyos/understanding/u2_pipeline.py                       # recover_* 转发 continuity_db_path 给 apply_proposal
honeyos/gateway/run.py                                     # 同批 U2 写入与恢复路径透传 continuity_db_path
frontend/src/features/understanding/UnderstandingPage.tsx  # 记忆节点可点击详情 + 相关标签 + 独立时间轨迹
frontend/src/api/understanding.ts                          # getLabel 读取 versions 字段
honeyos/companion/react_dist/*                             # 重新构建产物（新 hash）
tests/honeyos/understanding_v2/test_s45_evidence_state_recompute.py  # 新增：重算 + versions 遮罩回归
tests/honeyos/understanding_v2/test_s45_u2_not_injected_into_chat.py # 新增：U2 不注入聊天证明
tests/honeyos/understanding_v2/test_transports.py          # 更新：3 参 compose_user_api_content 契约
tests/honeyos/understanding_v2/test_u2_engineering.py      # 更新：同批 U2（u2_calls=0）契约
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
| 冻结提交 | 本轮：`cded7b39`（生产+测试）→ 本提交（文档，最终冻结）；历史：`093b656f`→`86a8110a`→`d22e7daf` |
| 工作树 | clean |
| push / merge / deploy | 未执行 |

## 14. 未解决问题（均在 S4.5 范围之外）

上一版 §14 列出的 3 项非阻塞限制，本轮已全部关闭：

1. ✅ 5 个 `understanding_v2` 陈旧测试已更新断言（见 §2b.4），未删除/跳过。
2. ✅ 图谱记忆节点可点击查看完整详情 + 相关标签；独立「时间轨迹」控件已补齐（见 §2b.3）。
3. ✅ 解除关联后重算标签 grade/state，并扩展到来源撤回/用户遗忘/反证变化（见 §2b.1）。

剩余 18 个失败全部 PRE-EXISTING 且与 S4.5 无关，单独列出，不越界扩展 S4.5：

- campus：`test_exams` ×1、`test_timetable` ×1
- gateway shadow：`test_turn_router_shadow_integration` ×5、`test_turn_router_shadow_v2` ×3
- 其他：`test_branding` ×1、`test_cli_main` ×1、`test_config` ×1、
  `test_distribution_contract` ×2、`test_install_script` ×1、
  `test_installer` ×1、`test_repository_surface` ×1

> 以上不涉及用户遗忘、来源权限、U2 二次调用、待续状态机或模型预算。S4.5
> 范围内功能缺陷已全部处理，可重新标记 DONE / FROZEN。
