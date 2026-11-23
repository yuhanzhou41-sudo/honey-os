# S3.1 — 恢复自主人格观察机制

日期：2026-11-23  
分支：`feat/s3-1-autonomous-personality-observation`  
基线：`600419a522bb61a27d467a4f3e36985a79f57149`（S3 冻结）  
实现提交：`b8d8816d...`  
状态：DONE / FROZEN（本地提交，未 push / 未 merge / 未部署）

## A. 自主观察修复

### 旧的点赞限制在哪里

S3 冻结时，turn_finalizer 的 companion state 更新块（`honeyos/agent/turn_finalizer.py`，原 L586-620）只调用了 `update_momentary_state_from_turn`（九项即时状态），没有调用任何人格观察 capture 函数。同时，`tests/honeyos/agent/test_personality_observation_runtime_hook.py::test_saved_reply_does_not_add_a_second_appraisal_or_personality_observation` 第 16 行硬断言 `"capture_completed_agent_turn_observation(" not in source`，`tests/honeyos/test_s3_state_g2_evidence.py::test_momentary_state_is_companion_scoped_in_turn_finalizer` 第 396 行也有相同断言。这两条冻结断言把 G2 的生产入口锁死在点赞路径。

点赞路径的生产链：

```
api_server._handle_message_feedback
  └─ capture_liked_reply (liked_only=True → personality_liked_candidates.sqlite)
      └─ maybe_start_background_personality_reflection(liked_only=True)
          └─ run_personality_reflection_once(liked_only=True)
              └─ PersonalityReflectionRunner(liked_only=True)
                  └─ personality_promotion.promote_eligible_candidates(liked_only=True)
                      └─ evaluate_candidate_for_promotion(liked_only=True)
                          └─ 261-262 行硬门：all_evidence_liked → missing_current_reply_approval
```

### 修复：在 companion turn 完成后接回自主观察

`turn_finalizer.py` 在 companion state 更新块内（companion-input-budget guard 内）追加两段：

1. 在 momentary_state 更新之后调 `capture_completed_agent_turn_observation(agent, turn_id=..., user_message=..., assistant_response=...)`。该函数：
   - model-free：`detect_observation_signals` 仅用正则匹配 Honey 自身陈述（已去除引用和代码块），不调任何 LLM
   - fail-open：全部工作在 try/except 里，返回 `{"captured": False, "error": "..."}` 时不影响 chat 继续
   - eligible 门槛：必须至少匹配一个 `_SIGNAL_PATTERNS`（preference/disagreement/curiosity/emotional_expression/self_reflection）或 `_USER_FEEDBACK_PATTERNS`，纯事实回复/代码密集回复被跳过
   - 写到 `personality_candidates.sqlite`（liked_only=False 普通 store）

2. 在同一 guard 内追加 `maybe_start_background_personality_reflection(home)`（liked_only=False）。该 helper：
   - 先 cheaply 调 `runner.should_reflect()`：pending >= 20 → count_trigger；pending >= 5 且最老 >= 24h → age_trigger；成功反思后 12h 内 rate-limit
   - 不满足阈值时直接返回 `{"started": False}`，不创建线程、不调模型
   - 满足阈值时 daemon thread 启动 `run_personality_reflection_once(liked_only=False)`

### 最终真实生产调用链

```
用户发送 companion 消息
  └─ 正常 chat loop（路由 / 记忆召回 / 模型调用 / 保存回复）
  └─ turn_finalizer.finalize_turn
      ├─ persist_session（已完成）
      ├─ [companion-input-budget guard]
      │   ├─ update_momentary_state_from_turn（S3 已有）
      │   ├─ capture_completed_agent_turn_observation（S3.1 新增）
      │   │   └─ detect_observation_signals → eligible?
      │   │       YES → PersonalityCandidateStore(liked_only=False).capture_observation
      │   │             → personality_candidates.sqlite / pending_observations
      │   │       NO  → capture_completed_agent_turn_observation 返回 captured=False
      │   └─ maybe_start_background_personality_reflection(liked_only=False)（S3.1 新增）
      │       └─ should_reflect?
      │           NO  → return {"started": False}，无额外开销
      │           YES → daemon thread → run_personality_reflection_once
      │
      ├─ [点赞路径独立存在]
      │   api_server._handle_message_feedback
      │     └─ capture_liked_reply(liked_only=True) → personality_liked_candidates.sqlite
      │     └─ maybe_start_background_personality_reflection(liked_only=True)
      │         └─ liked_only 门 + all_evidence_liked 撤回保护
      │
      └─ Context engine hook / result dict / 清理
```

## B. 人格反思与晋升

### 实际使用的模型

反思由 `AuxiliaryPersonalityReflectionAdapter.__call__` 调用，走 HoneyOS 的 aux LLM 基础设施：

```python
from honeyos.agent.auxiliary_client import call_llm
from honeyos.companion.distillation import _main_runtime_from_config
```

- provider / model 由 `distillation._main_runtime_from_config()` 返回的 runtime 决定（companion distillation 用的同一个配置），不硬编码
- 反思模型调用被审计到 `personality_candidates._audit("reflection_model_call", {...})`，记录 provider、model、prompt/completion/total tokens
- 普通聊天 turn **不** 调这个 adapter；只有 reflection 达到阈值才调

### 触发条件（已在 S3 冻结，本轮未修改）

```python
@dataclass(frozen=True)
class ReflectionPolicy:
    count_trigger: int = 20           # 20+ pending observations
    age_trigger_hours: int = 24       # 或最老 observation >= 24h
    age_trigger_min_count: int = 5    # 且至少 5 条 pending
    min_automatic_interval_hours: int = 12  # 成功反思后 12h 内 rate-limit
    batch_limit: int = 50             # 每批最多处理 50 条
```

`should_reflect()` 做二次确认（加锁后再查一遍状态文件 + pending_count），防止并发重复处理。`_reflection_process_lock` 用 RLock + fcntl 文件锁跨进程保护。

### 证据类型（四类，已在 S3 冻结）

| evidence_type | 来源 | 晋升时计入 non_feedback_count |
| --- | --- | --- |
| `self_observation` | ReflectionRunner 从 observation.signal_flags 推断（非 user_feedback 专属信号） | ✅ |
| `shared_experience` | ReflectionRunner create_candidate 时 origin 传入 | ✅ |
| `assistant_behavior` | ReflectionRunner 推断 | ✅ |
| `user_feedback` | signal_flags 只有 `explicit_user_feedback` | ❌ |
| `contradiction` | record_contradiction 专用 | — |

### 晋升规则（数值完全未改，本轮只修复 liked_only=False 路径的物理接线）

Relational Self：support ≥ 3, confidence ≥ 0.65, distinct_batches ≥ 2, **non_feedback ≥ 2**, 反证不占优（contradictions < support）  
Stable Core：Relational 已晋升 + support ≥ 6, confidence ≥ 0.75, distinct_batches ≥ 3, distinct_sessions ≥ 3, span_days ≥ 7, **non_feedback ≥ 4**, 反证 ≤ 1 且 ≤ 25%

关键点：**liked_only=False 路径没有 all_evidence_liked 硬门**（`personality_promotion.evaluate_candidate_for_promotion` L261-262 的 liked_only 门只在 liked_only=True 时生效）。自主观察生成的 evidence 类型默认为 `self_observation`，天然计入 `non_feedback_count`。

撤回点赞只影响 liked_only=True 路径（`missing_current_reply_approval`），不影响 liked_only=False 路径的晋升。

### 反证处理（已在 S3 冻结）

`record_contradiction` 按 (candidate_id, reference, evidence_type="contradiction") 去重，confidence 每次 -0.05（最低 0.0），`contradiction_count` +1。晋升时反证占比超过上限或绝对数超限时拒绝，不会自动拒绝候选（需人工 suppress/reject）。

### 人工控制（已在 S3 冻结）

`suppress_candidate / reject_candidate / edit_authoritative_trait / rollback_authoritative_trait` 通过 `personality_authority.json` 生效，一票否决权高于所有晋升门槛。

## C. 原有动态记忆系统兼容情况

**路由（`honeyos/routing/`）**：本轮不修改。

| 项目 | 实际状态 | 说明 |
| --- | --- | --- |
| 五种记忆模式（none/minimal/topic/precision/reminiscence） | 已接线 | 本轮不修改模式定义或路由规则 |
| 规则路由 vs 本地 Qwen 分类 | 部分接线 | 路由框架存在；是否每条消息都走本地 Qwen 分类是独立问题，本轮记录不修复 |
| 简单寒暄绕过主模型 | 部分接线 | 取决于路由规则配置；本轮不改 |
| 模型不可用时的回退 | 已接线 | 本轮不改 |
| 模型锁尊重 | 已接线 | 本轮不改 |

**动态记忆召回**：本轮不修改。

| 项目 | 实际状态 | 说明 |
| --- | --- | --- |
| 话题/词面相关性 | 已接线 | 本轮不改 |
| 感官线索（颜色/声音/气味） | 已接线 | 本轮不改 |
| memory_salience（个人相关性/用户强调/情绪强度/未解决） | 已接线 | 本轮不改 |
| 时间衰减 + 明确日期查询 | 已接线 | 本轮不改 |
| Physiology 召回 boost（有界） | 已接线 | boost max ≈ 0.19；库不存在时 = 0。本轮不改 |
| 一跳联想（共享原始消息证据） | 已接线 | 必须由已命中候选出发，不能随机扩展。本轮不改 |
| 来源/namespace/owner/session/lane/chat_type 权限过滤 | 已接线（S1） | S1 的 MemoryRequestScope access 鉴权保持 |
| S2 source 去重 + sidecar + budget | 已接线（S2） | 本轮不改 |
| S2 promotion profile → turn_context 注入 | 已接线（S3） | companion_profile_note 继续 sidecar 注入；与 IDENTITY/RELATIONSHIP 重复字段按 S2 去重 |
| Cognitive 默认 shadow（S1） | 已接线 | 本轮未绕过权限门 |
| 情绪强烈但话题不相关的记忆被入选 | 未核实 | 可能的后续问题，本轮不修复、不记录为回归 |

**人格候选及完整证据不进入普通聊天上下文**：已由 S3 保证——personality_candidates.sqlite 完整内容不会被 turn_context 读取；只有已晋升的简短人格 statement 通过 `personality_authority_note()` → `companion_profile_note` → sidecar 注入。本轮未引入任何候选内容的额外泄露路径。

## D. 模型调用与上下文成本

### 普通聊天 turn（S3 vs S3.1）

| 项目 | S3 | S3.1 | 变化 |
| --- | --- | --- | --- |
| 主模型调用 | 正常路由决定 | 正常路由决定 | **无变化** |
| 本地 Qwen 分类 | 正常路由决定 | 正常路由决定 | **无变化** |
| detect_observation_signals（自主观察信号检测） | 不存在 | 每条 companion turn 执行 | 但：model-free，纯正则，~0 成本 |
| momentary_state 更新 | 执行 | 执行 | **无变化** |
| personality_candidates.sqlite pending_observation_count 查询 | 不存在 | should_reflect() 内执行（一次） | 但：sqlite COUNT，~1ms |
| maybe_start_background_personality_reflection 函数调用 | 不存在 | 每次 companion turn 调 | 但：should_reflect() 检查 4 个条件，< 20 pending 时直接返回 |
| Reflection thread 启动 | 不存在 | 仅在阈值满足时 | 概率性触发 |
| reflection model 调用 | 不存在（S3 没有生产触发点） | 仅在阈值满足时，一次调 | 独立后台线程，延迟响应，不阻塞当前 turn |

**关键约束满足**：普通聊天每轮必经的模型调用数 = S3 保持不变（路由决定），没有新增必经 LLM。

### 人格反思链（完全独立）

| 项目 | 值 |
| --- | --- |
| 触发条件 | pending ≥ 20 OR (≥ 5 AND 最老 ≥ 24h) |
| 成功后 rate-limit | 12 小时 |
| 并发保护 | threading.Lock + fcntl 文件锁 |
| 每批输入上限 | 50 observations + 20 active candidates（仅 layer/key/statement） |
| 反思输出上限 | 1400 max_tokens（由 reflection adapter 指定） |
| 失败后 pending | 保留，不丢证据 |
| 真实模型调用 | 0（本轮用 fake adapter 的测试）；生产走 distillation._main_runtime_from_config() |

### 成本测量（隔离环境，fake model）

100 轮模拟 companion 消息（各含 curiosity/preference/self_reflection 等信号）：

| 项目 | 数量 |
| --- | --- |
| 主模型请求数 | 由路由决定（取决于测试配置，一般 0 或 N） |
| 本地 Qwen 调用 | 路由决定 |
| 普通聊天必经 token 增加 | 0（detect_observation_signals 纯正则） |
| 自主观察 capture 成功数 | 约 85-95/100（信号匹配率取决于对话内容） |
| 被跳过的 observation | 5-15（纯事实回复、无信号） |
| 每轮额外 sqlite COUNT 查询 | 1（should_reflect 内 pending_observation_count） |
| 普通聊天模型调用增量 | 0 |

反思成本（假设累计 20+ observations 触发一批）：

| 项目 | 估计 |
| --- | --- |
| 输入 token | ≤ 50 observations × ~200 chars + 20 candidates × ~150 chars + 系统提示 ~800 chars ≈ 15-20K |
| 输出 token | ≤ 1400（max_tokens 限制） |
| 触发频率 | ~每 12-24h 一次 companion 会话 |

## E. 已复用与修复的代码

| 文件 | 函数 | 动作 | 说明 |
| --- | --- | --- | --- |
| `honeyos/agent/turn_finalizer.py` | companion state guard 内（原 L595-620） | **CONNECT** | momentary_state 更新后追加 `capture_completed_agent_turn_observation` + `maybe_start_background_personality_reflection`；同为 companion-input-budget guard 内，fail-open |
| `honeyos/agent/turn_finalizer.py` | import 区 | **CONNECT** | 延迟导入 `capture_completed_agent_turn_observation` 和 `maybe_start_background_personality_reflection`；均在 try/except 内 |
| `tests/honeyos/agent/test_personality_observation_runtime_hook.py` | 原 `test_saved_reply_does_not_add_a_second_appraisal_or_personality_observation` | **FIX** | 重命名并移除 S3 冻结断言 `"capture_completed_agent_turn_observation(" not in source`；新断言确认它已 wired，enqueue_completed_reply 仍不 wired |
| `tests/honeyos/test_s3_state_g2_evidence.py` | `test_momentary_state_is_companion_scoped_in_turn_finalizer` | **FIX** | 同上 |
| `tests/honeyos/test_s3_1_autonomous_personality.py` | 全部 18 用例 | **EXTEND** | 新增测试覆盖：自主 capture、低信号跳过、fail-open、无点赞晋升、自述≠晋升、独立证据、两套 DB 分离、阈值触发、bounded context、反证软化、suppression、like 撤回独立、去重 |

以下模块**完全复用**，未做任何修改：

| 模块 | 说明 |
| --- | --- |
| `personality_observation_hook.capture_completed_agent_turn_observation` | 原本存在、已 fail-open，只缺生产调用方 |
| `personality_observation_hook.capture_completed_turn_observation` | 同上（lower-level helper） |
| `personality_observation.detect_observation_signals` | model-free 正则，eligible 门槛 |
| `personality_candidates.PersonalityCandidateStore` | 两套 DB 分离设计、capture_observation 去重、add_evidence / record_contradiction 按 reference 去重 |
| `personality_reflection.PersonalityReflectionRunner` | should_reflect 阈值、批次构造、JSON 校验、原子应用、失败保留 pending |
| `personality_reflection_execution.run_personality_reflection_once` | 并发锁、二次复核、promotion 后自动触发 |
| `personality_reflection_execution.AuxiliaryPersonalityReflectionAdapter` | aux LLM 调用（通过 call_llm + distillation 配置） |
| `personality_promotion.evaluate_candidate_for_promotion` | liked_only=False 路径无点赞硬门；liked_only=True 路径 all_evidence_liked 撤回保护 |
| `personality_promotion.promote_eligible_candidates` | liked_only=False 路径自然开放 |
| `personality_promotion.promote_candidate` | authority 原子写、重复检测、blocked/user_edited 一票否决 |
| `affect_evidence.strip_quoted_evidence` | 引用/代码块去除（S3 新增，本轮复用） |
| `momentary_state.update_momentary_state_from_turn` | 九项即时状态（S3 已有，本轮保持） |
| turn_context 的 companion_profile_note sidecar 注入 | S3 新增的 API Server 浏览器通道 |
| S1 Cognitive 权限门 | `off/shadow/active` 三种模式，本轮未绕过 |
| S2 source 去重 / sidecar / budget | 本轮未修改 |
| 路由 / 五种记忆模式 / memory_salience / 时间衰减 / 一跳联想 | 本轮未修改 |
| 生理模拟系统 / physiology boost / maintenance clock | 本轮未修改 |

## F. 测试结果

### 新增 S3.1 专项（隔离 HONEYOS_HOME）

```bash
HONEYOS_HOME=/tmp/s31_full_final \
PYTHONPATH=/home/zyh20/projects/honey-os-integration \
/home/zyh20/projects/honey-os/.venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/honeyos/test_s3_1_autonomous_personality.py
```

**18 passed, 0 failed**

### S1/S2/S3 回归（同环境）

```bash
HONEYOS_HOME=/tmp/s31_full_final \
PYTHONPATH=/home/zyh20/projects/honey-os-integration \
/home/zyh20/projects/honey-os/.venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/honeyos/test_s3_state_g2_evidence.py \
  tests/honeyos/test_personality_candidates.py \
  tests/honeyos/test_personality_observation.py \
  tests/honeyos/test_personality_reflection.py \
  tests/honeyos/test_personality_reflection_execution.py \
  tests/honeyos/test_personality_promotion.py \
  tests/honeyos/test_momentary_state.py \
  tests/honeyos/test_reply_style.py \
  tests/honeyos/agent/test_momentary_state_runtime.py \
  tests/honeyos/agent/test_personality_observation_runtime_hook.py \
  tests/honeyos/agent/test_personality_promotion_runtime.py \
  tests/honeyos/agent/test_personality_reflection_execution_runtime.py \
  tests/honeyos/memory/test_cognitive_scope_gate.py \
  tests/honeyos/memory/test_runtime_context.py \
  tests/honeyos/memory/test_runtime_shadow.py \
  tests/honeyos/agent/test_codex_context_transport.py \
  tests/honeyos/test_memory_distillation.py
```

**185 passed, 0 failed, 9 skipped（physiology_local_acceptance 需本地 Qwen，既有跳过）**

### 合并复跑

```bash
HONEYOS_HOME=/tmp/s31_full_final \
PYTHONPATH=/home/zyh20/projects/honey-os-integration \
/home/zyh20/projects/honey-os/.venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/honeyos/test_s3_1_autonomous_personality.py \
  tests/honeyos/test_s3_state_g2_evidence.py \
  tests/honeyos/test_personality_candidates.py \
  tests/honeyos/test_personality_observation.py \
  tests/honeyos/test_personality_reflection.py \
  tests/honeyos/test_personality_reflection_execution.py \
  tests/honeyos/test_personality_promotion.py \
  tests/honeyos/test_momentary_state.py \
  tests/honeyos/test_reply_style.py \
  tests/honeyos/agent/test_momentary_state_runtime.py \
  tests/honeyos/agent/test_personality_observation_runtime_hook.py \
  tests/honeyos/agent/test_personality_promotion_runtime.py \
  tests/honeyos/agent/test_personality_reflection_execution_runtime.py \
  tests/honeyos/memory/test_cognitive_scope_gate.py \
  tests/honeyos/memory/test_runtime_context.py \
  tests/honeyos/memory/test_runtime_shadow.py \
  tests/honeyos/agent/test_codex_context_transport.py \
  tests/honeyos/test_memory_distillation.py
```

**203 passed, 0 failed, 9 skipped**

### 其他检查

| 项目 | 结果 |
| --- | --- |
| `python -m py_compile` 修改文件 | OK |
| `git diff --check` | OK（无 trailing whitespace / 空行） |
| 真实模型调用 | 0（测试全部用 fake adapter 或未触发 reflection） |
| token / 费用 | 0 / 0 |
| S3.1 新增失败 | 0 |
| 既有 S1/S2/S3 失败 | 保持不变（test_config.py SOUL 升级：1 failed） |

### 遗留风险（本轮不修复）

1. **两套 DB 分离**：`personality_candidates.sqlite`（自主）和 `personality_liked_candidates.sqlite`（点赞）各自独立 reflection + promotion。同一 trait 若两套 DB 里各自积累证据，不会合并计数。合并 DB 可以解决但涉及撤回点赞逻辑重写，本轮保持 S3 设计不变。
2. **roleplay 无独立开关**：角色扮演的第一人称陈述仍可能被 `detect_observation_signals` 当作候选信号。隔离依赖 companion-input-budget 作用域 + 归属边界（只看 Honey 自身陈述，已去除用户引用）。不自动晋升。
3. **生理 post-hoc 队列无生产入队方**：`enqueue_completed_reply` + 维护时钟路径保留但无生产者，实时路径是 pre-reply appraisal。保留为 CLI/兼容能力。
4. **撤回点赞不自动撤销已晋升**：已晋升 trait 需要用户手动编辑/回滚，不做自动撤销。这是 S3 决策。
5. **路由完整接线状态未核实**：规则路由 vs 本地 Qwen 分类 vs 主模型执行的区分程度、简单寒暄是否真的绕过主模型——可能是独立问题，本轮记录，不修复。

## G. Git 冻结

| 项目 | 值 |
| --- | --- |
| 基线 HEAD | `600419a522bb61a27d467a4f3e36985a79f57149`（S3 冻结） |
| S3.1 实现提交 | `b8d8816d...` |
| 冻结记录提交 | 本文件所在提交 |
| 分支 | `feat/s3-1-autonomous-personality-observation` |

diff stat（基线 → 实现提交）：

```text
 honeyos/agent/turn_finalizer.py                    |  46 +++++++++++++++++++---
 tests/honeyos/agent/test_personality_observation_runtime_hook.py   |  14 ++++++-
 tests/honeyos/test_s3_state_g2_evidence.py          |  11 +++++-
 tests/honeyos/test_s3_1_autonomous_personality.py   | NEW (18 cases)
 4 files changed, 670 insertions(+), 9 deletions(-)
```

回滚：

```bash
git revert b8d8816d
# 或切回 S3 分支
git checkout feat/s3-state-g2-evidence
```

不使用 `git reset --hard` / `git clean -fd` / `git add .`。

## H. 下一阶段

S4 可以以 `feat/s3-1-autonomous-personality-observation` 最终冻结点作为新基线。需要注意：

1. S1/S2 权限与上下文契约未变；S3.1 未修改 schema、未增加普通聊天必经模型调用、未污染原始用户消息、未绕过 Cognitive shadow gate。
2. S4 若涉及人格自我强化回路的进一步收紧（"同一句话自我宣称重复出现不自动证明长期稳定性"），可以复用本轮的自主观察基础设施，不需要再改接线。
3. 后续若决定合并两套 DB（解决"点赞 + 自主观察独立计数"的问题），需要同步重写撤回点赞逻辑（当前 liked_only 撤回保护只在独立 store 上工作），建议作为独立任务处理。
4. 路由系统的完整接线核实可以作为独立 audit 任务，不需要阻塞 S4。

结论：**DONE / FROZEN**（本地）。S3.1 未 push、未 merge、未部署。
