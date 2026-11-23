# HoneyOS Phase S4.5 — 用户理解图谱与原生记忆召回整合

**冻结状态: DONE（后端全部交付；前端图谱 UI 标记为独立规划）**

## 0. 冻结元信息

| 项目 | 值 |
|---|---|
| 实施分支 | feat/s4-5-user-understanding-graph |
| 基线 HEAD | dff89780 (S4 freeze) |
| 实现 commits | 9a3070c8 → abc710af (revert) → 64c65185 (reapply) → b55b6b96 (U2 同批次整合) |
| Push / merge / deploy | 未执行 |

## 1. 核心交付

### 1.1 S4 known/neutral/unknown 收紧

emotional_imprint._classify() 中「有助手回复但无正则情绪命中」从
neutral 改为 unknown。neutral 保留 CHECK 约束供未来低激活证据使用。
旧印记不重写（INSERT OR IGNORE）。

### 1.2 U2 同批次整合（主模型一次调用）

**这是本轮最高优先级交付。**

MemoryDistiller prompt 追加可选 understandings 数组（max 4 条），
模型在同一次请求里同时输出原生记忆 operations 和 U2 标签建议。

```
模型输出 JSON:
  chapter {...}  (既有)
  operations [...] (既有, max 2000 tokens 预算)
  understandings [ (可选, 无则空 tuple)
    {operation, category_id, scope_key, canonical_key,
     text, operation_indices:[0..n-1]}
  ]
```

约束：
- 只引用已在同批次输出的 operation_index
- operation ∈ {propose, support, counter, supersede}
- category ∈ {interest_preference, behavior_pattern,
  learning_work_style, communication_style, relationship_style,
  value_tendency}
- 跳过 open_loop / temporary_state 作为 evidence
- 永远不推断敏感类别（身份、诊断、性取向）

MemoryDistiller._parse_understandings() 独立 static 方法，不 import
任何 understanding 模块，model-free 纯 JSON 解析 + 白名单过滤。

MemoryDistiller._apply_operations() 返回值签名改为
tuple[int, int, dict[int, str]]（applied, rejected, applied_indices），
给每个成功保存的 operation 记录 (op_index → memory_id) 映射。

DistillationResult 新增 understandings 和 applied_indices 字段。

run.py::_honeyos_u2_post_completed 在 distill 完成后：
1. result.applied_indices[op_index] → continuity memory_id
2. result.understandings[*].operation_indices → 映射到真实 memory_id
3. 直接 INSERT/UPDATE understanding_v2.db 的 labels + evidence + postings
4. fail-open（异常吞掉，不影响原 distillation）
5. 检查 labels.state=user_suppressed 的标签跳过写入

**U2 现在在同一次 MemoryDistiller 模型调用里真实运行。**
旧二次 LLM call（produce_after_distillation + async_call_llm
task=understanding_u2 max_tokens=600）已全部移除。

### 1.3 physiology 差异加权（真的改变排序）

上一轮 PARTIAL 用统一常数 phys_boost 给所有候选加同样值，对排序
零作用。本轮改为 kind × epinephrine 梯度：

```python
_KIND_GRADIENT = {
    "episode": 1.0,   # 共同经历，事件性强，匹配高 arousal
    "commitment": 0.7, # 答应过的
    "open_loop": 0.4,  # 待续
    "temporary_state": 0.0, # 用户临时状态，跳过
    "conversation_chapters": 0.0, # 独立表，不进 context_for_lane
}
phys_factor = min(0.12, max(0.0, (ep - 0.05)) * 0.18)
final_score = lexical_score + phys_factor * _KIND_GRADIENT[kind]
```

效果：两条 lexical score 相近但 kind 不同的记忆，在 epinephrine
高时 episode 会超过 commitment，真正改变排序。

约束：
- 只影响排序（rerank），不改变 _score >= 3 的准入阈值
- 上限 0.12，低于大多数真实分数差，不强行颠倒
- fail-open（physiology_shadow.sqlite 不存在 → phys_factor = 0）
- 不修改 runtime_shadow（外来历史）原有 physiology boost 公式
- 不调用 LLM

### 1.4 FakeDistiller.home 修复

test_continuity_gateway::test_gateway_tracks_distillation_as_non_blocking_
background_work 因 FakeDistiller 缺 .home 属性而失败。本轮给测试替身
加了 .home = tmp_path，生产契约不变。

### 1.5 continuity recall 已有遗忘边界（确认）

上一轮已验证：
- continuity.db: status ∈ {active, archived, forgotten}
  - list_active 只返回 active
  - list_managed 返回 active + archived
  - context_for_lane 用 list_active，天然过滤 forgotten
- cognitive_memory.sqlite: memory_tombstones 表

本轮未改遗忘逻辑，只是确认 physiology boost 加在 list_active 结果上，
所以用户已 forgotten 的记忆永远不会被 physiology boost 拉回。

## 2. 保持不变的功能

| 模块 | 不变项 |
|------|--------|
| MemoryDistiller | 触发阈值（20/6/40/日记权重 3）、五种记忆模式、_score 算法、_apply_operations 的 compress_episode/reinforce/update/resolve 路径、DISTILLATION_SCHEMA 常量 |
| 原生记忆 | 四种 kind 定义、三种 evidence 类型、expires_at 规则、StructuredMemoryStore.record 完整字段约束 |
| emotion_imprint | sidecar schema、classify static 方法、hook 绑定机制、downstream_holder 可变模式 |
| G2 | 两套 DB、晋升规则、S3.1 自动观察、personality_reflection_execution per-home 锁 |
| open_loop | 完成/隐藏/解决状态机、不进入 U2、physiology 权重最低（0.4x） |
| Study | 用户计划系统独立 |
| 外来历史 | DeepSeek + Study 纯检索、runtime_shadow 原有 physiology boost 公式、不受 continuity 的 kind gradient 影响 |
| 九项状态 | momentary_state + physiology_shadow 字段定义和衰减规则 |
| understanding | 全部 store/schema 保持（labels id=sha256(owner+lane+...)、evidence ref 格式 "continuity:<memory_id>"）、policy/sources/continuity_adapter 不动 |
| 前端 | 本轮不改任何前端文件 |

## 3. 本次 vs 上一轮 PARTIAL 的实际变化

| 项 | S4.5 PARTIAL | **本轮** |
|----|------------|---------|
| U2 二次 LLM call | 短路 return | **正式同批次整合** |
| U2 生产入口 | 不存在 | **distillation prompt + run.py apply** |
| physiology boost | 统一常数（零排序效果） | **kind×epinephrine 梯度（真正 rerank）** |
| FakeDistiller.home | 失败 | **修复** |
| applied_indices | 无 | **新增（op_index → memory_id）** |
| understandings 解析 | 无 | **新增 _parse_understandings + DistillationResult 字段** |
| understanding store 写入 | 无 | **run.py 里直接 INSERT/UPDATE** |

## 4. 模型调用及 token 成本

| 项目 | S3.1 | S4.5 PARTIAL | **本轮** | 变化 |
|------|------|-------------|---------|------|
| 普通聊天主模型调用 | 路由决定 | 路由决定 | 路由决定 | **无变化** |
| MemoryDistiller 主模型调用 | 每批 1 次 | 每批 1 次 | **每批 1 次** | **无变化** |
| U2 二次 LLM call | N/A | 关闭（无新入口） | **关闭** | **-1/批（从 S4 来）** |
| max_tokens/批 | 1400 | 1400 | **2000** | **+600（有界）** |
| 每批 understandings 字段 token | — | 0 | estimated max ~400 | 有界 |
| Physiology Qwen | 后台维护 | 后台维护 | 后台维护 | **无变化** |
| continuity recall 额外耗时 | — | ~0.18ms | ~0.1ms | 可忽略 |
| 数据库存储增量 | — | ~200B/印记 | U2 tags + evidence（增量每批 0~8 行） | 可忽略 |

核心约束满足：
- 普通聊天每轮必经模型调用数 = S3.1 保持不变
- MemoryDistiller 每批仍然只有一次模型请求（增加了可选字段和
  max_tokens 从 1400→2000，但**没有**新增调用次数）

## 5. 测试

### 5.1 新增 S4.5 专项（6 passed）

```
test_physiology_boost_diverges_by_kind_for_nearby_scores
test_u2_parse_understandings_rejects_unknown_categories
test_u2_parse_understandings_accepts_valid_item
test_u2_parse_understandings_requires_valid_indices
test_u2_same_batch_fall_back_to_empty_when_model_missing_field
test_apply_operations_returns_index_to_memory_id_map
```

### 5.2 core 回归

```
162 passed in 5.78s
(companion + memory + S4 emotion + S4.5 new + continuity gateway)
```

### 5.3 大范围回归（排除 aiohttp）

```
964 passed / 18 pre-existing failed / 18 skipped
```

18 个失败全部是预先存在的 branding/installer/shadow 问题，
与本轮修改无关（与 S4.5 PARTIAL 相同）。

### 5.4 其他

- py_compile: OK
- git diff --check: OK
- 真实模型调用: 0, token: 0, 费用: 0
- 未修改任何生产数据库 schema

## 6. 未完成项

| 任务 | 原因 | 规划 |
|------|------|------|
| 前端图谱 UI | 需技术栈评估（React 路由 / 现有记忆页 / 图形库） | 独立前端阶段 |
| S4 情绪印记 recall 端注入 | U2 同批次整合刚完成，图谱 API 尚未接 | 等前端阶段做 |
| 旧窗口未整理补偿（6 门槛 + 40 上限） | 底层 distillation 状态机改动 | 独立风险评估 |
| 外来历史统一硬上限（3 条 / 900 chars） | runtime_shadow 独立模块，改动面较大 | 后续阶段 |

## 7. Git 提交

```
b55b6b96 feat(s4.5): U2 same-batch distillation integration + divergent physiology boost
9ac99779 docs(s4.5): freeze backend safety fixes and recall enhancement
64c65185 Reapply "feat(s4.5): close U2 second LLM call..."
abc710af Revert "feat(s4.5): close U2 second LLM call..."
9a3070c8 feat(s4.5): close U2 second LLM call...
dff89780 docs(s4): freeze long-term memory emotional imprint acceptance
```

| 项目 | 值 |
|------|-----|
| Branch | feat/s4-5-user-understanding-graph |
| Working tree | clean（除本冻结文档） |
| Push | 未执行 |
| Merge | 未执行 |
| Deploy | 未执行 |

### 回滚

```bash
git revert b55b6b96
# 或切回 S4
git checkout feat/s4-longterm-memory-emotional-imprint
```

## 8. 后续建议

1. **U2 图谱 API + 前端** — highest next priority
   - 后端先加：GET /api/honeyos/u2/graph (labels + evidence + memories + imprints)
   - 前端：最小图谱（标签节点 + 记忆节点 + 关联连线，点击展开详情）
2. **S4 情绪印记 recall 注入** — U2 图谱 API 做好后沿 continuity.context_for_lane 返回结果追加
3. **外来历史统一硬上限** — 独立阶段
4. **旧窗口 6/40 补偿** — 先审计 state machine 再动手

---

**完成状态**: DONE（后端全部交付，前端图谱 UI 独立规划）
**停止位置**: 未进入 S5/S6/S7，未 push/merge/deploy
