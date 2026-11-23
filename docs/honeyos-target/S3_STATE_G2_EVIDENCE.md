# S3 — 现有 G2 人格与内部状态机制专项修复

日期：2026-11-23  
分支：`feat/s3-state-g2-evidence`  
基线：`a656a8b6310454e7efd12b538fa2360e9d4851d4`（S2 冻结）  
实现提交：`0284ac69b05b2b256a0b0a47adbc33d8bda0a25b`  
状态：DONE / FROZEN（本地提交，未 push / 未 merge / 未部署）

## A. 原有能力核对表

| 能力 | 结论 | 实际代码入口 |
| --- | --- | --- |
| 人格候选存储、支持/反证、状态、suppression | REUSED | `PersonalityCandidateStore.create_candidate / add_evidence / record_contradiction / suppress_candidate / reject_candidate` |
| 观察缓冲（pending observations） | REUSED | `PersonalityCandidateStore.capture_observation / list_pending_observations / mark_observations_processed` |
| 观察信号检测（模型无关） | FIX（归属边界） | `personality_observation.detect_observation_signals` |
| 正常保存回复 → 人格观察 | 不存在，且为当前冻结设计 | `turn_finalizer.finalize_turn` 只更新 momentary state；人格观察由点赞触发 |
| 点赞 → 观察 → 后台反思 | REUSED | `api_server._handle_message_feedback`（6936-6947）→ `capture_liked_reply` → `maybe_start_background_personality_reflection(liked_only=True)` |
| 撤回点赞后证据失效 | REUSED | `liked_observation_ids` 重新核对；`PersonalityReflectionRunner._discard_unliked_pending`；晋升 `missing_current_reply_approval` |
| 反思批次校验、原子应用、失败保留 pending | REUSED | `PersonalityReflectionRunner.run_once / _validate_operations / _preflight_operations / _apply_operations` |
| 反思并发与频率限制 | REUSED | `_reflection_process_lock`（线程锁 + fcntl）、`should_reflect` 的 12h 间隔与二次复核 |
| 晋升门槛（Relational/Stable）、跨批次/会话/时间跨度、反证上限 | REUSED（数值未改） | `personality_promotion.evaluate_candidate_for_promotion` |
| 人工编辑、删除、回滚、抑制 | REUSED | `edit_authoritative_trait / rollback_authoritative_trait / get_candidate suppression` |
| 晋升 → 模型上下文（IM / TurnRunner 通道） | REUSED | `gateway/run.py` 每轮 staging `companion_profile_note` |
| 晋升 → 模型上下文（API Server 浏览器 companion 通道） | CONNECT（真实缺失） | 此前无调用；现由 `turn_context` 在 `_companion_input_budget` 回合 staging |
| 观察去重（跨重试/重述） | FIX | `capture_observation` 按 `(session_id, 来源事件)` 去重 |
| 证据按来源事件计一次 | FIX | `_evidence_reference_exists`；`_evidence_metrics` 按事件聚合 |
| 两套九项状态分离 | REUSED | `momentary_state.py` 与 `physiology_shadow.py` 独立存储、独立衰减 |
| 非 companion 回合状态污染 | FIX | `turn_finalizer` 增加 companion 作用域门 |
| physiology 召回 boost 上限/关闭/过期 | REUSED（有界） | `runtime_shadow` 的 `attention * arousal`，`live_signals` 无库返回 `{}` |
| physiology 后台维护时钟 | REUSED（队列型，生产输入为 pre-reply 直写） | `api_server` 启动 `run_maintenance_clock`；实时输入走 `pre_reply_appraisal.apply_turn_appraisal` |

### 两份历史记录的差异裁定

M0 记录“`capture_completed_agent_turn_observation` 无生产调用方”与 2026-11-17 进度“正常保存回复已能捕捉人格观察”在当前 S3 基线上可以同时解释：

- 当前基线**确实没有** turn 级人格观察调用；`tests/honeyos/agent/test_personality_observation_runtime_hook.py` 明确断言 `turn_finalizer` 不包含该调用，`tests/honeyos/test_reply_style.py` 明确断言“点赞回复是唯一合格人格来源”。
- 11-17 进度中的“捕捉观察”对应的是同一保存回合写入的 **momentary state** 与 **physiology pre-reply appraisal**，不是 G2 候选观察。
- 因此不恢复 turn 级人格观察，避免把普通自述变回无审批的人格证据；该差异以本文件与测试固定。

## B. 修复内容

| 文件 | 函数 / 位置 | 修改 | 原因 |
| --- | --- | --- | --- |
| `honeyos/companion/personality_candidates.py` | `capture_observation` | 去重键改为 `(session_id, COALESCE(user_reference, assistant_reference))`；对非 liked store 同样生效；保留 liked 的 `feedback_unavailable` 复位 | 同一回复/同一用户事件被重试、重新措辞或重复点赞时不再生成第二条观察 |
| 同上 | `_evidence_reference_exists`（新增） | 同一候选 + 同一 observation id 已存在时跳过插入与计数 | 同一事件跨反思批次不重复累计独立支持 |
| 同上 | `create_candidate`（既有候选分支）、`add_evidence` | 重复 reference 时 `support_count` 不增、confidence 不虚增；审计 `evidence_duplicate_skipped` | 防止批次重放放大支持次数 |
| 同上 | `record_contradiction` | 同一 reference 的反证只计一次；审计 `contradiction_duplicate_skipped` | 防止重试重复削弱/重复累计 |
| `honeyos/companion/personality_promotion.py` | `_evidence_metrics` | 按来源事件聚合 evidence_count / feedback 分类 / batches / sessions / span；无 reference 的旧证据仍逐条计数 | 文本不同但同源不重复；真正不同事件不合并 |
| `honeyos/companion/affect_evidence.py` | `strip_quoted_evidence`（新增） | 复用既有 `_CITATION` 去除引号、引用行、代码片段 | 归属边界显式化 |
| `honeyos/companion/personality_observation.py` | `detect_observation_signals` | 自身信号只在去除引用后的文本上匹配 | 引用的用户原话/代码里的 “I prefer …” 不再算 Honey 的人格信号 |
| `honeyos/companion/personality_observation_hook.py` | `capture_liked_reply` | 额外写入 `user_reference=liked-user:<row>` | 观察获得稳定事件身份，供去重与晋升聚合 |
| `honeyos/agent/turn_finalizer.py` | momentary state 更新条件 | 增加 `getattr(agent, "_companion_input_budget", False) is True` | 非 companion / work / codex 回合不写 Honey 临时状态 |
| `honeyos/agent/turn_context.py` | `_gateway_notes` 消费前 | companion 回合把 `companion_profile_note`（已晋升人格 + 即时状态）并入既有 one-shot sidecar | 补齐 API Server 浏览器通道的“晋升 → 模型上下文”最后一环；已有档案字段仍由 S2 去重函数剔除 |
| `honeyos/companion/personality_reflection_execution.py` | `_REFLECTION_INSTRUCTIONS` | 增加“重复≠独立、换措辞/换模型仍是同一事件、意愿≠行为、用户指派≠自主兴趣” | 语义层减少错误归因；不改结构、不改阈值 |

未新增数据库、表、列或评分系统。`personality_pending_observations` 列集合由测试固定。

## C. G2 最终运行链

```text
用户点赞某条 assistant 回复
  └─ api_server._handle_message_feedback
       └─ capture_liked_reply
            ├─ 校验：assistant 行、active、非空、无 tool_calls、非 hidden/auto_continue/model_switch、已👍
            ├─ detect_observation_signals（只看 Honey 自己的陈述）
            └─ PersonalityCandidateStore(liked_only=True).capture_observation
                 → <home>/companion/personality_liked_candidates.sqlite
                   personality_pending_observations（按事件去重）

maybe_start_background_personality_reflection(liked_only=True)
  ├─ should_reflect（pending>=20，或 >=5 且最老>=24h；成功反思后 12h 限流）
  ├─ 后台线程 + 线程锁/文件锁 + 加锁后二次复核
  └─ PersonalityReflectionRunner.run_once
       ├─ 批次 = 最多 50 条 pending + 最多 20 个 active 候选（仅 layer/key/statement）
       ├─ aux LLM（personality_reflection，JSON only，记录 provider/model/token）
       ├─ 严格校验：action/layer/trait_key/statement/confidence/本批次 observation id
       ├─ 预检 create/support/contradict 的业务依赖
       ├─ 应用：create_candidate / add_evidence / record_contradiction（按 reference 去重）
       └─ 成功后 mark_observations_processed；失败保留 pending、不改候选

promote_eligible_candidates(liked_only=True)
  ├─ all_evidence_liked 复核（撤回即失格）
  ├─ Relational：support>=3、confidence>=0.65、distinct_batches>=2、non_feedback>=2、反证不占优
  ├─ Stable：需已有 Relational 权威、support>=6、confidence>=0.75、batches>=3、sessions>=3、span>=7d、non_feedback>=4、反证<=1 且 <=25%
  ├─ blocked_candidate_ids / user_deleted_traits / user_edited 一票否决
  └─ <home>/companion/personality_authority.json（原子写 + promotion audit jsonl）

模型上下文
  ├─ TurnRunner 通道：gateway/run.py staging companion_profile_note
  └─ API Server 浏览器 companion：turn_context staging companion_profile_note（本轮 CONNECT）
       → 与 IDENTITY.md / RELATIONSHIP.md 重复的字段按 S2 规则剔除
       → 只进入 api_content sidecar，不修改持久化用户消息

模型回复
  └─ turn_finalizer：仅当 companion 授权回合、成功保存、非中断、非失败
       └─ update_momentary_state_from_turn（九项即时状态，独立于人格证据）
```

存储位置：

- 观察/候选/证据/抑制：`<home>/companion/personality_candidates.sqlite`（普通 store）与 `personality_liked_candidates.sqlite`（生产点赞路径）。
- 反思状态：`<home>/companion/personality_reflection_state.json` / `personality_liked_reflection_state.json`。
- 晋升权威：`<home>/companion/personality_authority.json`；审计 `personality_candidate_audit.jsonl`、`personality_promotion_audit.jsonl`。
- 即时状态：`<home>/companion/momentary_state.json`。
- 生理模拟：`<home>/companion/physiology_shadow.sqlite`。

## D. 两套九项状态

| 项目 | Momentary State | Physiology Shadow |
| --- | --- | --- |
| 九项 | curiosity / reflectiveness / seriousness / warmth / energy / playfulness / tension / positive_valence / negative_valence | cortisol / epinephrine / oxytocin / vasopressin / melatonin / dopamine / pge2 / testosterone / estradiol |
| 更新者 | `turn_finalizer`（deterministic 正则，仅 companion 回合） | `pre_reply_appraisal.appraise_before_reply`（本地 Qwen，companion 回合、非 trivial 才排队）；`PhysiologyShadow.apply_turn_appraisal` 直写，按 `(session_id, turn_id)` 幂等 |
| 读取者 | `profile.companion_profile_note` → 系统/侧通道上下文 | `pre_reply_appraisal.current_state_note` → 当轮 user api_content；`runtime_shadow` 召回 boost；`proactive_initiative` / `web_initiative` |
| 衰减 | 半衰期 3h，12h 硬过期归零 | 每信号独立半衰期（epinephrine 0.15h 至 testosterone/estradiol 24h），回到 baseline；melatonin 按时辰 |
| 上限/关闭 | 阈值 0.20 才注入标签；无外部强化 | 召回 boost = `(epinephrine-0.05)*0.20 * arousal∈[0,1]`，最大 0.19；库不存在时 `live_signals={}` → boost 0 |
| 权限边界 | 仅 `_companion_input_budget` 回合写入与注入 | 仅 companion 回合排队；appraisal 取消时直接返回当前状态，不写事件 |
| 与人格关系 | 不创建/强化/晋升候选 | 不写候选或权威人格；仅作为内部状态与 initiative 输入 |

未合并、未互相覆盖、未重设数值体系。

## E. 测试与性能

命令（全部隔离 `HONEYOS_HOME`、临时 SQLite、`-p no:cacheprovider`）：

```bash
HONEYOS_HOME=/tmp/s3_final_verify \
PYTHONPATH=/home/zyh20/projects/honey-os-integration \
/home/zyh20/projects/honey-os/.venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/honeyos/test_s3_state_g2_evidence.py \
  tests/honeyos/test_personality_candidates.py \
  tests/honeyos/test_personality_observation.py \
  tests/honeyos/test_personality_reflection.py \
  tests/honeyos/test_personality_reflection_execution.py \
  tests/honeyos/test_personality_promotion.py \
  tests/honeyos/test_momentary_state.py \
  tests/honeyos/test_physiology_shadow.py \
  tests/honeyos/test_physiology_local_acceptance.py \
  tests/honeyos/test_reply_style.py \
  tests/honeyos/agent/test_momentary_state_runtime.py \
  tests/honeyos/agent/test_personality_observation_runtime_hook.py \
  tests/honeyos/agent/test_personality_promotion_runtime.py \
  tests/honeyos/agent/test_personality_reflection_execution_runtime.py \
  tests/honeyos/memory/test_cognitive_scope_gate.py \
  tests/honeyos/memory/test_runtime_context.py \
  tests/honeyos/memory/test_runtime_shadow.py \
  tests/honeyos/memory/test_codex_context.py \
  tests/honeyos/agent/test_codex_context_transport.py \
  tests/honeyos/test_memory_distillation.py
```

| 项目 | 结果 |
| --- | --- |
| 合并复跑（S3 新增 + G2 + 状态 + S1/S2 回归） | **211 passed, 9 skipped** |
| 新增 S3 专项文件 | 25 passed |
| 修改前同范围基线 | 79 passed, 9 skipped（不含 S3 新增文件） |
| `tests/honeyos/test_config.py` | 14 passed, 1 failed（既有 SOUL 失败，见下） |
| 修改文件 `py_compile` | `PY_COMPILE_DONE` |
| `git diff --check` | 通过 |
| 真实模型调用 | 0（反思/评估全部使用 fake adapter 或未触发） |
| token / 费用 | 0 / 0 |
| 9 skipped | `test_physiology_local_acceptance` 需要本地 Qwen 的用例，既有跳过，非本轮回归 |

新增覆盖对应条目：

- G2：保存回复只更新临时状态（1/14）、回复重复幂等（2）、跨批次同源只计一次（3）、自述/换模型/用户指派提示约束（4/6/13）、独立行为可累积（5/8）、用户反馈不能单独晋升（7）、反证延迟（9）、人工删除/抑制（10）、门槛常量（11）、反思无变化（12）。
- 状态：两套存储分离（2）、momentary 衰减与硬过期（3）、physiology 回 baseline 与无状态 boost=0（3/4）、boost 上限（5）、非 companion 门（6）、turn/message 幂等（7）。
- 既有九项生理专项：`test_physiology_shadow.py`、`test_physiology_local_acceptance.py`（Qwen 用例保持 skip）。

已知既有失败（非 S3 引入，单独列出）：

- `tests/honeyos/test_config.py::test_upgrade_companion_capabilities_is_idempotent_and_preserves_user_state`，断言 `first_soul.startswith("# My formed identity")`。S1 阶段已在冻结 HEAD `dba87b94` 的独立 worktree 证明同样失败；S3 未修改 `upgrade_companion_capabilities`、SOUL 或模板。

## F. 阶段冻结

| 项目 | 值 |
| --- | --- |
| 基线 commit | `a656a8b6310454e7efd12b538fa2360e9d4851d4` |
| S3 实现 commit | `0284ac69b05b2b256a0b0a47adbc33d8bda0a25b` |
| 冻结记录 commit | 本文件所在提交（`git log -1 --format=%H -- docs/honeyos-target/S3_STATE_G2_EVIDENCE.md`） |
| 分支 | `feat/s3-state-g2-evidence` |

diff stat（基线 → 实现提交）：

```text
 honeyos/agent/turn_context.py                      |  25 +++
 honeyos/agent/turn_finalizer.py                    |   3 +
 honeyos/companion/affect_evidence.py               |   9 ++
 honeyos/companion/personality_candidates.py        | 174 +++++++++++++++------
 honeyos/companion/personality_observation.py       |  13 +-
 honeyos/companion/personality_observation_hook.py  |   1 +
 honeyos/companion/personality_promotion.py         |  42 +++--
 .../companion/personality_reflection_execution.py  |   4 +
 8 files changed, 215 insertions(+), 56 deletions(-)
```

另有新增 `tests/honeyos/test_s3_state_g2_evidence.py`（25 用例）。

遗留风险：

1. 人格证据仍以“用户点赞”为唯一生产入口；这是当前冻结设计，不是本轮引入。
2. 已晋升人格现在会进入浏览器 companion 上下文。若模型随后重复该表述且被点赞，仍可能形成同源支持；已用“事件去重 + 反思提示 + 点赞审批 + 人工编辑/回滚”四层收敛，但语义级“复述”无法在无新增模型调用的情况下完全判定。
3. roleplay 没有独立会话模式开关，隔离依赖 companion 作用域门、记忆 namespace 与“只看 Honey 自身陈述”的归属边界；角色扮演文本若以第一人称直接陈述，仍可能被当作观察信号（不会被直接晋升）。
4. 生理 post-hoc 队列（`enqueue_completed_reply` + 维护时钟）无生产入队方；实时路径是 pre-reply appraisal。该队列保留为 CLI/兼容能力。
5. 撤回点赞只阻止后续强化；已晋升条目需要用户手动编辑/回滚，不做自动撤销。

回滚：

```bash
git revert 0284ac69b05b2b256a0b0a47adbc33d8bda0a25b
```

或直接切回 `feat/s2-context-transport`。不使用 `git reset --hard` / `git clean -fd`。

结论：**DONE / FROZEN**（本地）。

## G. 下一阶段

S4 具备开始条件：S1/S2 权限与上下文契约未变，S3 未新增数据库、未增加普通聊天必经模型调用、未污染原始用户消息。S4 未在本轮执行。
