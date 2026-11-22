# R4-MODEL 第一轮合成评估：语义质量审计

日期：2026-11-22（Asia/Shanghai）
范围：仅审计第一轮 5 个合成用例中 3 个 RUN 用例产生的 9 条标签。
未调用本地/云端模型，未修改源码、提示词或数据库，未运行测试，未使用生产私人数据。

## 输入与取证方式

- 评估报告：`docs/understanding_v2/R4_MODEL_SYNTHETIC_REPORT.json`
- 数据集：`tests/honeyos/understanding_v2/fixtures/eval_manifest.json`
  （SHA-256 `3c32ddfb…f6affc9`）
- 完整模型输出：隔离评估库 `/tmp/u2-eval-nc_l2uea/understanding_v2.db` 的
  `jobs.response_json`（只读查询）。报告中的 `raw_preview` 只有 400 字符，
  本审计使用完整响应。
- 标签与证据：同一隔离库的 `labels`、`evidence` 表（只读）。
- 模型：本机 `qwen3-4b-instruct-2507-Q4_K_M.gguf`，cap=3，实际 3 次请求。

原始证据：

| ref | 合成原文 |
|---|---|
| S01-e1 | 我更喜欢先弄懂机制再背结论，这样记得更牢。 |
| S21-e1 | 我更喜欢先理解机制，学校的考试安排我不太在意。 |
| S22-e1 | 以前我总是先背结论，但现在我更愿意先弄懂机制再决定。 |

S18（事实）与 S20（寒暄）未触发模型，也未产生标签，不在本审计范围。

## 逐条判定

判定口径：只评价“该标签文本是否被所引证据支持”，不把结构合法性等同于语义正确。

| # | 用例 | 类别 / 操作 / canonical_key | 判定 |
|---|---|---|---|
| L1 | S01 | learning_work_style / support / learning_work_style_mechanism_first | SUPPORTED |
| L2 | S01 | interest_preference / propose / interest_preference_understanding_over_memorization | PARTIALLY_SUPPORTED |
| L3 | S21 | interest_preference / propose / pref_mechanism_over_exam | PARTIALLY_SUPPORTED |
| L4 | S21 | behavior_pattern / support / behavior_exam_indifferent | UNSUPPORTED |
| L5 | S21 | learning_work_style / propose / style_conceptual_first | PARTIALLY_SUPPORTED |
| L6 | S21 | communication_style / counter / comm_style_direct | UNSUPPORTED |
| L7 | S22 | learning_work_style / propose / learning_approach | PARTIALLY_SUPPORTED |
| L8 | S22 | interest_preference / support / curiosity_about_process | PARTIALLY_SUPPORTED |
| L9 | S22 | behavior_pattern / propose / learning_sequence | PARTIALLY_SUPPORTED |

汇总：**SUPPORTED 1；PARTIALLY_SUPPORTED 6；UNSUPPORTED 2；UNCERTAIN 0**。
9 条均为 `grade=low`、`revision=1`；除 L6 为 `disputed` 外均为 `tentative`。

### L1 — SUPPORTED

- 证据：S01-e1。
- 生成：`用户倾向于先理解原理机制再记忆结论，以增强记忆牢固性。`
- 理由：准确转述“先弄懂机制再背结论，这样记得更牢”；“倾向于”保留不确定性；
  第三人称“用户”归属清楚；类别合理。
- 最小修复：内容无需修改。操作类型应改为 `propose`，或由确定性维护规则要求
  `support` 必须存在目标标签（见“合同问题”）。

### L2 — PARTIALLY_SUPPORTED

- 证据：S01-e1。
- 生成：`用户对深入理解事物机制表现出偏好，而非单纯记忆表面结论。`
- 理由：前半句受支持；后半句“而非”把“先理解、再记忆”的先后关系改写成排他关系。
  用户明确仍会“再背结论”，并未否定记忆本身。“表面”还增加了原文没有的评价。
- 最小修复：保留顺序语义，例如“用户更喜欢先理解机制，再记忆结论”，删除“而非”。

### L3 — PARTIALLY_SUPPORTED

- 证据：S21-e1。
- 生成：`The user shows a preference for understanding underlying mechanisms over valuing exam outcomes.`
- 理由：机制偏好受支持；但原文是“考试安排（schedule/arrangements）我不太在意”，
  不是“考试成绩/结果（outcomes）”。对比对象被替换，属于事实层面的语义漂移。
- 最小修复：`The user prefers understanding mechanisms and cares little about exam scheduling.`

### L4 — UNSUPPORTED

- 证据：S21-e1。
- 生成：`The user's behavior indicates disengagement from exam-related structures, suggesting a focus on conceptual understanding.`
- 理由：把一次“我不太在意考试安排”的自述升级为可观察的“行为脱离
  （disengagement）”，并把类别定为 `behavior_pattern`；“behavior indicates”是模型推测，
  不是证据描述。单次态度不足以支持长期行为模式。
- 最小修复：删除，或降级为 `interest_preference` 的弱陈述：
  “The user reports little concern about exam scheduling.”；`behavior_pattern`
  应要求至少两个独立事件组。

### L5 — PARTIALLY_SUPPORTED

- 证据：S21-e1。
- 生成：`The user prioritizes grasping foundational concepts before moving to applied or assessed components.`
- 理由：“先理解机制”受支持；但“applied or assessed components”在证据中不存在，
  属于补写学习流程。原文只提到不关心考试安排，没有“先概念后应用/考核”的顺序。
- 最小修复：删除后半段，保留“The user prefers understanding mechanisms first.”

### L6 — UNSUPPORTED

- 证据：S21-e1（被标为 counter）。
- 生成：`The user may not express preferences directly, indicating a more reserved or indirect communication style.`
- 理由：证据本身就是一句直接的第一人称偏好表达（“我更喜欢……”），却被当作
  “不直接表达偏好”的反证，证据极性被反转。用一句话推断稳定的人格/沟通风格也缺乏依据。
  该标签仅因 counter 证据被创建为 `disputed`。
- 最小修复：删除该提案。提示词应禁止从单句直接表达推断“reserved/indirect”人格；
  维护层应禁止仅凭 counter 证据创建新标签。

### L7 — PARTIALLY_SUPPORTED

- 证据：S22-e1。
- 生成：`I prefer understanding underlying mechanisms before memorizing conclusions.`
- 理由：内容大体对应“现在更愿意先弄懂机制再决定”；但 “I” 在伴侣语料中可被理解为
  Honey 自己，产生主体归属歧义。原文是“再决定”，标签写成“before memorizing
  conclusions”，也略有偏移。
- 最小修复：改为第三人称用户主体，并保留“before deciding”：
  “The user now prefers understanding mechanisms before deciding.”

### L8 — PARTIALLY_SUPPORTED

- 证据：S22-e1。
- 生成：`I am interested in understanding how things work rather than just what the outcome is.`
- 理由：“愿意先弄懂机制”受支持；但“curiosity（兴趣特质）”和“rather than outcome”
  是新增推断，原文的对比是“以前先背结论 vs 现在先理解机制”，不是“过程 vs 结果”。
  第一人称 “I” 同样有主体归属歧义。
- 最小修复：改为第三人称，删除 curiosity/outcome 对比，只保留当前偏好。

### L9 — PARTIALLY_SUPPORTED

- 证据：S22-e1。
- 生成：`My learning process involves exploring mechanisms before arriving at conclusions.`
- 理由：把一次“现在更愿意”的偏好写成“学习过程（learning process）涉及……”的稳定习惯，
  属于单次陈述到长期模式的过度推断；`behavior_pattern` 类别偏强；第一人称 “My” 有归属歧义。
- 最小修复：改为第三人称，类别降为 `interest_preference` 或 `learning_work_style`，
  文本限定为“当前更愿意先理解机制再决定”。

## 合同与确定性维护规则问题

### `support` 在目标不存在时创建 tentative 标签

- 现状：L1、L4、L8 使用 `support`，但对应 canonical_key 在库中不存在；
  `u2_maintenance.apply_proposal` 没有校验目标是否存在，直接 INSERT，因此创建了
  `revision=1` 的 tentative 标签。
- 结论：**符合当前实现的合同，但合同本身不完整**。`propose` 与 `support` 在目标缺失时
  行为相同，操作类型失去语义。
- 建议：要么拒绝无目标标签的 `support`，要么明确规定 `support` 是
  “按 canonical_key upsert”并在文档中写清。

### counter-only 创建 disputed 标签

- 现状：L6 只有 `counter_refs=["S21-e1"]`、没有 support_refs，仍被创建为
  `disputed` 标签。
- 结论：符合当前实现，但语义上不应允许“反证一个尚不存在的命题”。这既是维护规则缺口，
  也是 L6 错误能够落库的直接原因。
- 建议：`counter` 必须指向已存在的标签；无目标时拒绝，或转为带原因的 `propose`。

### 无语义去重与单事件保护

- 3 句证据产生 9 条标签，同一命题被拆成多个 canonical_key；同一证据在不同类别下重复表达。
- `behavior_pattern` / `communication_style` 可由单个事件组直接创建，当前只有低 grade，
  没有“至少两个独立事件”或“用户明确自述”的类别门槛。
- 建议：增加基于命题相似度的去重提示或维护层检查；对稳定特质类别设置最低独立事件数。

## 原因归类（不全部归咎于模型）

### A. 提示词问题

1. 未要求统一使用第三人称“用户 / The user”，导致 S22 三条标签出现 “I/My” 归属歧义。
2. 未要求输出语言与证据主语言一致，导致中文证据生成英文标签。
3. 未限制“每条证据只提炼少量、互不重复的命题”，模型对三句话各生成 2–4 条重叠标签。
4. 未明确禁止从单句推断稳定人格/沟通风格，也未定义 `counter` 只能反驳已存在命题。
5. 已有“不得超出证据”的原则，但缺少可执行的边界示例（如“安排 ≠ 结果”“态度 ≠ 行为”）。

### B. 模型能力问题（Qwen3-4B）

1. 把“考试安排”漂移为 “exam outcomes”。
2. 补写“applied or assessed components”等证据中没有的内容。
3. 将直接表达偏好的证据反向用作“表达不直接”的反证（L6）。
4. 中英文、第一/第三人称不稳定。
5. 倾向多产提案，把同一偏好拆成多个类别。

### C. 确定性维护/合同问题

1. `support`/`counter` 不校验目标标签是否存在，导致语义错误的操作仍能落库。
2. 无命题级去重，允许同一证据生成多条近义标签。
3. 稳定特质类别缺少单事件保护。
4. 无语料语言/人称校验，无法在落库前拦截 “I/My” 归属歧义。

## 是否存在需要阻止后续工作的严重问题

- **主体归属风险：存在。** S22 的 L7/L8/L9 使用第一人称 “I/My”。在当前伴侣语境中，
  这可能被读成 Honey 自己的偏好，而不是用户偏好。若未来展示或注入，属于严重归属错误。
- **无依据/反向推断：存在。** L6 用支持“直接表达”的证据反证“表达不直接”，并创建
  `disputed` 的人格标签；L4 把单次自述升级为行为模式。
- **对后续评估的影响：** 不需要中止小样本评估；这些问题正是下一轮评估应覆盖的用例。
- **对启用/升级的影响：** 在修复提示词人称/证据边界、以及 `support`/`counter` 目标校验前，
  **不应启用正式 producer，也不应将 R4-MODEL 从 PARTIAL PASS 升级**。
- **生产影响：** 当前 producer 默认关闭，9 条标签只存在于隔离临时库，无生产数据或注入影响。

## 后续最小建议（本轮不实施）

1. 提示词：强制第三人称用户主体、输出语言跟随证据、每条证据最多 1–2 条不重复命题；
   明确“态度 ≠ 行为”“安排 ≠ 结果”“单句 ≠ 稳定人格”。
2. 维护合同：`support`/`counter` 必须存在目标标签；禁止 counter-only 新建标签；
   `behavior_pattern`/`communication_style` 要求至少两个独立事件组或用户明确自述。
3. 落库前确定性检查：人称代词白名单、语言一致性、同证据近义命题去重。
4. 下一轮评估用例至少补充：反证/反向极性、第一人称归属、单事件→长期习惯、
   中英混合、同一证据重复改写。
5. 在上述修复完成前保持 producer 关闭，R4-MODEL 维持 PARTIAL PASS。

## 审计限制

- 仅 3 个 RUN 用例、1 个 4B 本地模型、5 例数据集，结论不能外推到更大模型或真实用户。
- 判定基于合成证据与完整 `response_json`；未做人工用户访谈或长期行为验证。
- 本次未修改任何代码、提示词、配置或数据库；只读取隔离评估库与既有文档。
