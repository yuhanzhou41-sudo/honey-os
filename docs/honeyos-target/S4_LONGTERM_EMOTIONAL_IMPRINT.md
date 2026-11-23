# S4 — 原生长期记忆的情绪印记

日期：2026-11-23
分支：`feat/s4-longterm-memory-emotional-imprint`
基线：`df800e50196979028462792438281992b69549f9`（S3.1 冻结）
实现提交：`67bf658e`
状态：DONE / FROZEN（本地提交，未 push / 未 merge / 未部署）

## A. 当前记忆架构核对

### 顶层四个记忆类别

| 类别 | 存储 | 读取入口 | S4 覆盖 |
| --- | --- | --- | --- |
| 当前窗口聊天 | 进程内 messages 列表 | turn_context.build_turn_context | ❌ 不覆盖 |
| 原生聊天记忆 | continuity.db / StructuredMemoryStore | continuity.py + distillation.py | ✅ 覆盖 |
| 历史记忆（DeepSeek 导入） | cognitive_memory.sqlite | memory/repository.py | ❌ 不覆盖（外来身份） |
| 学习记忆（Study） | Study 自有存储 | Study 场景内按权限 | ❌ 不覆盖 |

### 原生聊天记忆五种子类与实际 kind 映射

MemoryDistiller 通过 DistillationModel 的 LLM operations 写入 continuity.db 的 `structured_memories` 表，`kind` 字段值为：

| kind 值 | 用户侧语义 | 长期保存 | 有 expires_at | S4 印记资格 |
| --- | --- | --- | --- | --- |
| `episode` | 共同经历 | ✅ 永久 | ❌ NULL | ✅ eligible |
| `commitment` | 答应过的 | ✅ 持久 | 视情况 | ✅ eligible |
| `open_loop` | 待续 | ✅ 持久 | 视情况 | ✅ eligible |
| `temporary_state` | 用户临时状态 | ❌ 短期 | ✅ 有 | ❌ → unknown |
| `conversation_chapters` | 最近章节 | ❌ 归档 | ✅ 有 | ❌ 不走 structured_memories 主表（独立表） |

生产调用链：

```
用户聊天 → gateway/run.py → active_honeyos_distiller()
  → distill_if_due(reason=new/session_switch/...)
    → DistillationModel.call(main_runtime)
    → MemoryDistiller._apply_operations(store=StructuredMemoryStore(continuity.db))
      → structured_memories.record(kind, content, source_message_ids, distillation_run_id)
      → post_completed_hook(job, result, main_runtime)
          ← S4 emotion_imprint_hook_factory 绑定的闭包（一次绑定，downstream 可变）
```

### 不确定项

1. **cognitive_memory.sqlite** —— 既存的另一套"长期记忆"库，MemoryDistiller **从不**写入它（只有 deepseek_v21 importer 和 Study 写）。本轮不触碰，不做印记。
2. **conversation_chapters 表** —— 最近章节是独立表，不是 structured_memories，distillation run_id 不关联。S4 天然跳过。

## B. 已复用功能

| 功能 | 来源 | 复用方式 |
| --- | --- | --- |
| continuity.db + StructuredMemoryStore | S1/S2 冻结 | 原地复用，不改 structured_memories schema |
| MemoryDistiller.post_completed_hook 机制 | distillation.py | CONNECT — 绑定 emotion hook 为 post_completed_hook（一次绑定，downstream holder 可变） |
| momentary_state._matched_axes | S3 | REUSED — 直接调用于 cited assistant text，判断 Honey 自身情绪/认知状态信号 |
| PersonalityReflectionRunner（per-home 锁模式） | S3 | 参考锁模式，emotion_imprint 自身不需要跨进程锁 |
| `sqlite3.connect(continuity.db, timeout=1.0)` | S1/S2 | REUSED — EmotionalImprintStore 继承相同超时/PRAGMA |
| INSERT OR IGNORE 去重语义 | StructuredMemoryStore 已有 | REUSED — EmotionalImprintStore 同样 INSERT OR IGNORE，同一 memory_id 不重复创建印记 |
| run.py 的 understanding → downstream_holder 绑定 | U2 既有模式 | REUSED — emotion hook 先跑，U2 作为 downstream（若 enabled） |

### 必须最小扩展的功能

| 功能 | 扩展 | 说明 |
| --- | --- | --- |
| `personality_reflection_execution._reflection_process_lock` | FIX（BUG） | 全局 `_THREAD_LOCK = threading.Lock()` → per-home `_HOME_LOCKS: dict[Path, threading.Lock]`。多 tmp_path 测试夹具不再互相阻塞。生产路径不变（一个 home 一把锁）。 |
| continuity.db schema | EXTEND（sidecar only） | 新增 `structured_memory_emotional_imprints` 表（CREATE TABLE IF NOT EXISTS）。**不改 structured_memories 的任何列** |

### 完全未修改的模块

- MemoryDistiller 的模型选择、min_tail_messages、trigger_messages、max_batch_messages
- 五类分类规则的 LLM system prompt
- CognitiveMemoryRepository / cognitive_memory.sqlite
- 五种记忆模式（none/minimal/topic/precision/reminiscence）
- memory_salience / 时间衰减 / 一跳联想 / 感官线索排序
- S1 权限门（off/shadow/active，默认 shadow）
- S2 source 去重 / sidecar / budget
- G2 两套 DB（liked_only + normal）、两套晋升门槛数值
- S3 momentary_state 九项 / physiology_shadow 九项
- 生理模拟算法、召回 boost
- U2 全部（理解标签）

## C. S4 情绪印记实现

### 数据契约

```text
structured_memory_emotional_imprints (continuity.db 里的 sidecar 表):
    memory_id TEXT PRIMARY KEY         — 外键，关联 structured_memories.id
    lane_key TEXT NOT NULL
    kind TEXT NOT NULL                 — 结构化记忆原始 kind
    status TEXT NOT NULL CHECK ('known','neutral','unknown')
    dominant_axis TEXT | NULL          — momentary_state._AXES 里的轴名
    dominant_label TEXT | NULL         — coarse 情绪标签（positive/warm/tense/...）
    basis_axes_json TEXT NOT NULL '[]'
    basis_turn_ids_json TEXT NOT NULL '[]'
    formed_at TEXT | NULL              — cited assistant reply 的最新 created_at ISO
    recorded_at TEXT NOT NULL          — 本次印记写入时间
    distillation_run_id TEXT
    evidence_summary TEXT NOT NULL
```

**绝不修改 structured_memories 表**。记忆正文、来源、版本、原始时间保持完全独立。

### known / neutral / unknown 判定（model-free）

在 distillation 完成后，hook：

1. 从 continuity.db 查 `distillation_run_id = job.run_id` 的所有 structured_memories（就是这次批次新写入的记录）
2. 每条结构化记忆的 `source_message_ids`（JSON 数组，是 DistillationJob.messages 里 message 的 `_row_id` 值）
3. 在 job.messages 里找到 role == "assistant" 的那些行
4. 对每条 assistant text 跑 `momentary_state._matched_axes(text)`（纯正则 regex）
5. 汇总所有 matched axes 作为 basis_axes

**判定规则**：

| 条件 | 状态 | 说明 |
| --- | --- | --- |
| basis_axes 非空 | known | Honey 自身回复里有明确情绪/认知信号（curiosity / positive_valence / tension / ...） |
| basis_axes 空但 basis_turn_ids 非空 | neutral | 有 assistant 回复可关联，但回复是事实性的，没有 Honey 情绪自我表达 |
| basis_turn_ids 空 | unknown | 无法找到可关联的 assistant 回复（只有用户消息引用，或者 source_message_ids 无效） |
| kind 是 temporary_state | unknown | 用户临时状态不是 Honey 的经历 |

**关键约束**：
- 不用 LLM 推断；完全由 _matched_axes 正则决定
- 用户转述情绪 → 不算（只有 role=assistant 的 Honey 自己回复才进判定）
- 状态匹配看 reply 原文（strip_quoted_evidence 已在 distillation 前处理引用）

### 修订规则

```sql
INSERT OR IGNORE INTO structured_memory_emotional_imprints ...
```

- 同一 memory_id 不会出现两条印记（memory_id 是 PRIMARY KEY，upsert 失败时被忽略）
- 重复 distillation（同一 source_hash + 同一 run_id）→ continuity.db 里 structured_memories 不重复写 → 印记不重复
- 不同 run_id 但引用相同事件 → continuity.db 里 structured_memories 用 upsert（DistillationModel 判重复），不新写 → 印记不重复
- 印记是 append-only，不做修订历史（S4 范围内足够）
- 记忆被 tombstone（遗忘）或抑制 → EmotionalImprintStore 不感知；下游 recall 按 tombstone 过滤后再读印记

### 旧数据兼容

- `structured_memory_emotional_imprints` 表不存在 → `_ensure_table` 创建（CREATE TABLE IF NOT EXISTS）
- 旧 structured_memories 行无对应印记 → `EmotionalImprintStore.get(memory_id)` 返回 None
- 不批量给旧记忆补印记（不调模型、不造数据）
- 表迁移是零成本的（第一次 upsert_for_distillation 时自动 CREATE TABLE）

## D. 回忆机制

### 已完成端到端：印记写入

MemoryDistiller.post_completed_hook（S4 CONNECT）：
```
distill_if_due(reason=...)
  → 模型调用（既有，不修改）
  → structured_memories.record(...) × N
  → post_completed_hook(job, result)  ← S4 emotion_imprint_hook_factory
      → EmotionalImprintStore.upsert_for_distillation(run_id, job.messages, memory_ids)
          → SELECT structured_memories WHERE distillation_run_id = run_id
          → 每条 memory：infer_basis(job.messages) → _classify() → INSERT OR IGNORE
```

### PARTIAL：回忆时的有界影响

本轮 **只完成了印记的侧写和只读读取 API**（`EmotionalImprintStore.get(memory_id)`）。

以下行为 **不** 在 S4 端到端：
- ❌ turn_context 在组装时自动给长期记忆条目追加有界的 emotional imprint 行
- ❌ 历史情绪印记影响 physiology recall boost（当前 physiology boost 已冻结）
- ❌ 自动将 known 印记的情绪方向注入 momentary_state

原因：
1. `continuity.py` 的 `context_for_lane`（为 MemoryDistiller 和 MemoryManager 服务的上下文组装）目前是 DistillationModel 的**上游**——它写入 distillation transcript，不是注入到 chat prompt 的路径
2. 真正的 chat prompt 注入在 `turn_context.build_turn_context` 里，它组装 Cognitive memory + continuity 摘要 + personality_authority + momentary_state + physiology
3. continuity 的 emotional imprint 需要插在哪一层需要进一步审计——本轮只做 "B"（存储）和 "C"（形成），"D"（调用）作为 PARTIAL 单独列出

**本轮 recall 相关已验证**：
- `EmotionalImprintStore.get(memory_id)` 能正确解析 JSON 字段、返回 EmotionalImprint dataclass
- 对旧 memory_id（无 sidecar row）返回 None
- known / neutral / unknown 三种状态正确分类

**本轮 recall 相关明确不做**：
- 不修改 turn_context（影响 prompt 组装的主管道需要审慎审计）
- 不修改 physiology boost（S3 冻结）
- 不新增普通聊天必经 LLM 调用

## E. 成本

### S3.1 vs S4 对比

| 项目 | S3.1 | S4 | 变化 |
| --- | --- | --- | --- |
| 普通聊天主模型调用 | 路由决定 | 路由决定 | **无变化** |
| 普通聊天本地 Qwen | 路由决定 | 路由决定 | **无变化** |
| 记忆整理主模型调用 | 每 distill_if_due 一次 | 每 distill_if_due 一次 | **无变化** |
| Reflection runner 模型调用 | 阈值触发时 | 阈值触发时 | **无变化** |
| 新增长期记忆侧写调用 | 无 | 每次 distillation 批次完成后 | model-free（纯正则） |
| 新增长期记忆侧写耗时 | — | 每条 ~1-2ms（sqlite + 正则） | ~N × 1.5ms |
| 新增长期记忆侧写 token | — | 0（不调模型） | **0** |
| 回忆侧额外耗时 | — | EmotionalImprintStore.get 一次 SELECT ~1ms | 0（PARTIAL 阶段未接线） |
| 回忆侧额外 token | — | 0（PARTIAL 阶段未接线） | **0** |
| continuity.db 存储增量 | — | 每 known/neutral/unknown 一行 | ~200 bytes / 行 |

**硬性要求满足**：普通聊天每轮必经的模型调用数 = S3.1 保持不变。

### 额外修复成本

`personality_reflection_execution.py` 全局锁 → per-home 锁（7 行改动）。影响范围仅限测试隔离（多个 tmp_path 不互相阻塞），生产路径一个 home 一把锁，行为不变。

## F. 测试结果

### 新增 S4 专项（隔离 HONEYOS_HOME）

```bash
HONEYOS_HOME=/tmp/s4_tests_final \
PYTHONPATH=/home/zyh20/projects/honey-os-integration \
/home/zyh20/projects/honey-os/.venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/honeyos/test_s4_emotional_imprint.py
```

**19 passed, 0 failed**

覆盖场景：
- known 判定（assistant 有 curiosity/positive_valence 信号）
- neutral 判定（assistant 回复事实性）
- unknown 判定（无 assistant 引用 / kind=temporary_state / 无表）
- 四类 eligible kind 全部覆盖（episode/commitment/open_loop）
- hook factory 一次性绑定 + mutable downstream holder + downstream 热更新
- downstream error 被 swallow + emotion path 继续执行
- idempotency（INSERT OR IGNORE）
- EmotionalImprintStore.get 返回 None 给旧 memory
- EmotionalImprintStore.get 正确解析 JSON 字段为 tuple
- 缺失 continuity.db 时返回 0，不 raise
- `emotional_imprint.py` 不 import 任何 LLM caller

### S1/S2/S3/S3.1 + S4 合并回归

```bash
HONEYOS_HOME=/tmp/s4_final_reg \
PYTHONPATH=/home/zyh20/projects/honey-os-integration \
/home/zyh20/projects/honey-os/.venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/honeyos/test_s4_emotional_imprint.py \
  tests/honeyos/test_s3_1_autonomous_personality.py \
  tests/honeyos/test_s3_state_g2_evidence.py \
  tests/honeyos/test_personality_candidates.py \
  tests/honeyos/test_personality_observation.py \
  tests/honeyos/test_personality_reflection.py \
  tests/honeyos/test_personality_reflection_execution.py \
  tests/honeyos/test_personality_promotion.py \
  tests/honeyos/test_momentary_state.py \
  tests/honeyos/test_reply_style.py \
  tests/honeyos/test_memory_distillation.py \
  tests/honeyos/agent/test_momentary_state_runtime.py \
  tests/honeyos/agent/test_personality_observation_runtime_hook.py \
  tests/honeyos/agent/test_personality_promotion_runtime.py \
  tests/honeyos/agent/test_personality_reflection_execution_runtime.py \
  tests/honeyos/memory/test_cognitive_scope_gate.py \
  tests/honeyos/memory/test_runtime_context.py \
  tests/honeyos/memory/test_runtime_shadow.py \
  tests/honeyos/agent/test_codex_context_transport.py
```

**222 passed, 0 failed, 9 skipped**

9 skipped：`test_physiology_local_acceptance` 需本地 Qwen —— 既有跳过。

### 既有失败保持不变

- `tests/honeyos/test_config.py` SOUL 升级路径：1 failed —— 既有，本轮不触碰
- **S4 未引入任何新失败**

### 其他检查

| 项目 | 结果 |
| --- | --- |
| `python -m py_compile` 所有修改文件 | OK |
| `git diff --check` | OK |
| 真实模型调用 | **0** |
| token / 费用 | **0 / 0** |

### 额外修复说明

`personality_reflection_execution._reflection_process_lock` 全局锁 → per-home 锁是既有 bug（`_THREAD_LOCK = threading.Lock()` 模块级单例跨所有 home 竞争），在 S3.1 L388 调 `maybe_start_background_personality_reflection(tmp_path)` 启 daemon thread 后暴露。修复仅影响测试隔离（多个 tmp_path fixture 不互相阻塞），生产路径一个 home 一把锁，语义不变。

## G. Git 冻结

| 项目 | 值 |
| --- | --- |
| 基线 HEAD | `df800e50196979028462792438281992b69549f9` |
| S4 实现 commit | `67bf658e` |
| 分支 | `feat/s4-longterm-memory-emotional-imprint` |
| 工作树 | clean |

diff stat（基线 → 实现提交）：

```text
 honeyos/companion/emotional_imprint.py               | NEW
 honeyos/companion/personality_reflection_execution.py | 全局锁→per-home 锁
 honeyos/gateway/run.py                                 | emotion hook 绑定 + downstream_holder
 tests/honeyos/test_s4_emotional_imprint.py             | NEW (19 cases)
```

回滚：

```bash
git revert 67bf658e
# 或切回 S3.1
git checkout feat/s3-1-autonomous-personality-observation
```

## H. 后续阶段

S4 后可以开始 U2（原生长期记忆的用户理解标签组织机制），但需要注意：

1. **emotion hook 的 downstream holder 设计就是为 U2 准备的**：U2 在 understanding.enabled 时写入 `downstream_holder[0]`，emotion hook 自动先跑再调 U2 producer。不需要重建 hook。
2. U2 的标签应该标注在 **structured_memories** 上（与 S4 emotion_imprint 的 sidecar 平行），不要覆盖 emotion_imprint 的 evidence_summary 或 formed_at。
3. `cognitive_memory.sqlite` 的五类长期记忆 vs continuity.db 的 structured_memories 分类映射需要在 U2 前做完整审计——两者当前完全独立。
4. **continuity.context_for_lane → turn_context 组装** 的完整路径需要在 recall 端（PARTIAL 部分）接线才能让 U2 标签和 emotion imprint 都有界地注入到 chat prompt。

S4 未完成的 recall 部分（D 节 PARTIAL）：emotion imprint → chat prompt 有界注入，不是独立阶段可以修复的，需要等 U2 把 continuity 上下文完整接到 memory recall 管道上后再一起做。

**已知独立问题（后续处理）**：
1. 全局 `physiology boost` 逻辑与 momentary_state 历史快照对齐
2. cognitive_memory.sqlite 与 continuity.db 的分类映射
3. 路由系统完整接线审计（S3.1 遗留）
4. DeepSeek 历史记忆迁移
5. S5 自主预算与工具权限

**S4 结论：DONE / FROZEN**（本地）。未 push、未 merge、未部署。
