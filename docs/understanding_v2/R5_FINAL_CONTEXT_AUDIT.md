# R5 最终上下文与状态轴：源码审计与最小接线方案

日期：2026-11-22
范围：只读审计 R5 上下文链路。未调用模型、未修改代码、未运行测试、未使用生产私人数据、未重新审计 R4-07。

## 1. 实际调用链（CONFIRMED）

正常 chat-completions 路径：

1. `honeyos/agent/conversation_loop.py:1311` 调用 `build_turn_context()`。
2. `honeyos/agent/turn_context.py:1219-1239` 执行 Cognitive Memory 只读检索
   （`run_cognitive_memory_shadow`）并构造 `SilentMemoryContext`。
3. `honeyos/agent/turn_context.py:1258-1276` 在 **非** `codex_app_server` 时调用
   `inject_silent_memory_context()`，把 Cognitive 文本并入 `ext_prefetch_cache`。
4. `honeyos/agent/turn_context.py:1274-1278` 调用 `compose_user_api_content()`，
   将 `ext_prefetch_cache` 与 `plugin_user_context` 追加到当前用户消息的
   `api_content`（仅 API 副本，存储内容保持干净）。
5. `honeyos/agent/turn_context.py:1162-1177` 把 Gateway 暂存的
   profile/continuity/reset notes 并入 `plugin_user_context`。
6. `honeyos/gateway/run.py:16732-16754` 生成
   `companion_profile_note()` 与 `structured_memory_note()`；
   `17839-17840` 暂存，`4942-4944` 注入 agent。
7. `honeyos/agent/system_prompt.py:683-692` 把 `MEMORY.md` 与 `USER.md`
   放进 **system prompt**。
8. `honeyos/memory/runtime_context.py:598-640` 写入 F2.3 审计并返回合并文本；
   `runtime_shadow.py:395-407` 是 F1 入口。

`codex_app_server` 路径：

9. `conversation_loop.py:1407-1414` 直接返回 `_run_codex_app_server_turn()`。
10. `run_agent.py:7938-7949` → `agent/codex_runtime.py:618-698`；
    `698` 调用 `agent._codex_session.run_turn(user_input=user_message)`。
11. `agent/transports/codex_app_server_session.py:345-346`
    `thread/start` 仅发送 `{"cwd": ...}`；
    `517-527` `turn/start` 仅发送一个 `{"type":"text","text": user_input_text}`。

结论：**codex 路径不包含 system prompt、USER/MEMORY、Cognitive Memory、
companion profile、continuity note、U2 上下文**。该路径只收到干净的用户文本。

## 2. Honey 九项状态：真实接口与可用性

定义：`honeyos/companion/momentary_state.py:18-28`

| 轴 | 来源/稳定性 | 是否可合法用于记忆排序 |
|---|---|---|
| curiosity | 从 **assistant 回复文本** 正则命中；3h 半衰期、12h 过期 | 否：这是 Honey 的瞬时语气，不是用户关注度 |
| reflectiveness | 同上 | 否 |
| seriousness | 同上 | 否 |
| warmth | 同上 | 否 |
| energy | 同上 | 否 |
| playfulness | 同上 | 否 |
| tension | 同上 | 否 |
| positive_valence | 同上 | 否 |
| negative_valence | 同上 | 否 |

关键事实：

- `momentary_state.py:239-277` 从 `assistant_response` 更新，不读取用户长期状态。
- `199-236` 做半衰期衰减与 12h 硬过期；`_state_path` 写入
  `companion/momentary_state.json`。
- `306-320` 只生成一段“temporary companion state”语气提示，经
  `profile.py:312-328` 并入 `companion_profile_note()`，最终进入用户消息 sidecar。
- 排序侧 `understanding/retrieval.py:105-177` 接受
  `state_bias_by_label`，但全仓 **没有任何调用方传入该参数**；
  `understanding/u2_runtime.py:62-66` 的 `normalize_state_bias()` 也无调用方；
  `RuntimeResult.state_axis_verified` 从未被置为 `True`。

结论：**CONFIRMED，R5 的 state bias 实际恒为 0。**
九项状态是 Honey 的瞬时语气，不适合作为用户记忆相关性信号。最小合法接线是
**保持 0**；若未来需要状态信号，应新增“当前对话焦点”类用户侧信号，
而不是复用这九个 mood 轴。不要把 `momentary_state` 接进 `ThreeDimensionalRecallRanker`。

## 3. Cognitive Memory 正文与权限

- 检索入口：`memory/runtime_shadow.py:236-256` 直接查
  `memory_episodes`，条件为 `memory_origin='external'`、`status='active'`、
  无 active source tombstone；没有 lane、chat_type、owner、session 过滤。
- 排序/选择：`runtime_shadow.py:258-300` 纯词法打分（阈值 2.0/3.0），
  namespace 仅区分 general/roleplay/fiction。
- 构造上下文：`runtime_context.py:292-369` 使用 `summary`（最多 240 字符），
  不读取正文、provenance 或 `evidence_quote`。
- 注入权限：`runtime_context.py:598-640` 只检查 `would_inject`
  （`text` 与 `included` 非空），没有 DM/群聊、lane、owner 或用途复核。
- 正文读取：`memory/library.py:158-257` 的 `get_historical()` 可返回
  `summary`、provenance、`evidence_quote`、修订与 tombstone 信息，是现成的
  单条读取 API；但 schema（`memory/schema.py:13-30`）**没有**
  `chat_allowed`/`analysis_allowed` 字段，权限只有 status、origin、
  namespace 和 tombstone。
- 存储路径：`memory/repository.py:75-93` 使用 `get_honeyos_home()` 全局 home，
  不是 companionship lane 级路径。

结论：

- **CONFIRMED**：当前 R5 只注入摘要，未绑定“正文 reader”；`get_historical()`
  可复用，但不能直接复用 U2 的 `ContinuitySourceResolver`（表结构与语义不同）。
- **CONFIRMED**：Cognitive 没有“用途权限”标志，只有 namespace/status/tombstone。
- **LIKELY**：由于 home 是进程级且检索不按 lane/session/chat_type 过滤，
  在多 lane 或群聊场景存在跨会话记忆被注入的风险；取决于部署是否一 home 多 lane。

## 4. 重复注入、主体归属与权限绕过

### CONFIRMED

1. **U2 上下文从未注入**：`compose_user_api_content()` 的
   `understanding_context` 参数（`turn_context.py:57,84-85`）全仓无调用方传入非空值；
   `compose_memory_context()`（`understanding/u2_context.py:46-81`）与
   `ThreeDimensionalRecallRanker`（`retrieval.py:105`）也没有生产调用方。
   R5 当前实际注入的是 Cognitive Memory，不是 U2。
2. **Cognitive 注入默认开启**：`turn_context.py:1219-1239` 无条件执行（仅跳过
   trivial prompt）；`inject_silent_memory_context()` 只要
   `would_inject` 为真就追加。没有 `off/shadow/active` 配置门。
   注释中的 “shadow” 只描述 F1 检索，F2.3 已经是模型可见。
3. **codex 丢失全部上下文**：见第 1 节第 9–11 条。
4. **同一通道合并、无跨源去重**：`ext_prefetch_cache` 同时承载
   `memory_manager.prefetch_all()` 与 Cognitive 文本（`turn_context.py:1210-1215,1267`）；
   `build_silent_memory_context()` 只在 Cognitive 内部按条数/字符裁剪，
   不做跨 provider 去重。
5. **主体归属标签存在但不统一**：Cognitive 使用
   `[Background memory — use silently]`（`runtime_context.py:14-20`）；
   continuity 使用 `[HoneyOS 关系连续性记忆…]` 并禁止身份/关系/诊断推断
   （`continuity.py:677-701`）；`USER.md` 在 system prompt，codex 完全收不到。
6. **continuity 侧有 DM/runtime 门**：`continuity.py:902-911` 要求
   `HONEYOS_RUNTIME_ID` 以 `honeyos-companion-` 开头且 `chat_type=="dm"`；
   Cognitive 侧没有对应门。

### LIKELY

- `USER.md` 与 `companion_profile_note()` 可能重复姓名/昵称等身份字段；
  两者在不同通道（system vs user sidecar），代码无一致性检查。
- 外部 memory provider 的 prefetch 可能包含与 Cognitive 相同的历史事件；
  当前只按 provider 拼接，可能重复叙述同一件事。

### UNKNOWN

- codex app-server 是否支持 `thread/start` 的 `instructions`/`developerInstructions`
  字段；当前代码未使用，也未做 payload 验证。
- Cognitive 摘要的实际人称/主体（“用户…”还是伴侣第一人称）；未读取生产数据。
- 生产部署是否一 home 多 lane/群聊；决定 LIKELY 的跨会话风险是否成立。

## 5. 最小修复方案（按优先级）

### P0 — codex 最终 payload（R5 的关键缺口）

- 在 `agent/transports/codex_app_server_session.py:490-527` 的 `run_turn()` 增加
  可选 `context_text: str = ""`；`turn/start` 仍只发一个 text item，但把
  `context_text` 以明确分隔符放在用户文本前（或先验证并使用
  `thread/start` 的 instructions 字段）。
- 在 `agent/codex_runtime.py:618-698` 透传；在 `conversation_loop.py:1407-1414`
  由 `build_turn_context` 产出一个有界的 `codex_context_text`。
- 新增显式门 `memory.cognitive.codex_app_server_context`，默认关闭；
  开启前只用一段 “Background memory” 包装，不发送完整 system prompt。
- 必须用 fake client 断言 `turn/start` 的精确 JSON，再考虑真实 codex 手测。

### P1 — 状态轴

- 保持 `state_bias_by_label` 为空，不把 `momentary_state` 九个 mood 轴接入排序。
- 在 `retrieval.py:162-166` 加断言/测试：无验证状态时 `state` 分量必须为 0；
  `u2_runtime.expose()` 不设置 `state_axis_verified=True`。

### P2 — Cognitive 权限与作用域

- `runtime_shadow.py:236-256` 的查询增加 `session_id`/`lane_key`/`chat_type`
  过滤（可通过 `memory_provenance.session_id` 关联）；当前 `session_id`
  只用于审计。
- 在 `runtime_context.py:598-640` 注入前复核：`status='active'`、无 tombstone、
  namespace 允许、DM 场景（对齐 `continuity._active_honeyos_home`）。
- 在完成上述前，建议给 F2.3 注入加显式开关并默认关闭；当前是默认开启。

### P3 — 去重与归属

- 在 `turn_context.py:1267-1276` 之前，把 provider prefetch、Cognitive、
  profile、continuity 统一成带 `source_ref/revision` 的段列表，复用
  `u2_context.compose_memory_context()` 做精确去重（它已有该逻辑，只是未被调用）。
- 对同一 `source_ref/revision` 只保留一份；语义近似去重不在本轮范围。
- 在组装处打印/测试最终注入块的来源标签，避免 USER/MEMORY 与伴侣 profile
  重复身份字段。

### P4 — Cognitive 正文 reader（仅在未来需要时）

- 复用 `memory/library.py:158-257` 的 `get_historical()`，外面包一层
  `authorized_cognitive_body(memory_id, expected_status, namespace)`，
  校验 active/tombstone/namespace 后再读取，并限制字符数。
- 不要复用 `u2_sources.ContinuitySourceResolver`：表、权限标志和 lane 语义不同。

## 6. 所需隔离测试（本轮不运行）

1. `tests/honeyos/test_codex_app_server_context_payload.py`
   - fake client；门关闭时 `turn/start.input` 只有用户文本；
   - 门开启时只有一个 text item，含固定包装、长度有界、无 system prompt 重复。
2. `tests/honeyos/memory/test_cognitive_permission.py`
   - 临时 cognitive DB；跨 session/lane 不返回；DM vs 群聊；tombstone/status；
   - 注入前复核拒绝已撤回来源。
3. `tests/honeyos/understanding/test_r5_state_bias.py`
   - 空 bias 时 `state` 分量为 0；`momentary_state` 不进入 ranker；
   - `expose()` 不产生 `state_axis_verified=True`。
4. `tests/honeyos/test_r5_duplicate_injection.py`
   - provider prefetch 与 Cognitive 返回同一文本时只保留一份；
   - `USER.md` 与 profile note 的身份字段重复检测（渲染字符串级）。
5. `tests/honeyos/test_r5_u2_not_injected.py`
   - 正常路径与 codex 路径都不出现 `UNDERSTANDING_BEGIN`，直到显式接线。

## 7. 下一次实施任务清单

1. 先加 codex context 的可选参数与默认关闭的配置门；用 fake client 固化 payload 测试。
2. 给 Cognitive F2.3 注入加显式开关，补 DM/lane/session 权限过滤与注入前复核。
3. 状态轴保持 0，补回归测试防止误接 mood 轴。
4. 引入统一段列表 + 精确去重，消除 provider/Cognitive/profile 重复。
5. 以上完成后再决定是否需要 Cognitive 正文 reader；U2 注入继续留待 R4-MODEL 修复。
6. 不启用正式 producer，不开展 R5-REAL/R6/R7。
