# HoneyOS Phase S4.5 — 用户理解图谱与原生记忆召回整合

**冻结状态: PARTIAL** — 后端安全项全部交付；同批次 U2 标签整合和
前端图谱 UI 未在本轮实施（单独规划）。

## 0. 冻结元信息

| 项目 | 值 |
|---|---|
| 实施分支 | feat/s4-5-user-understanding-graph |
| 基线 HEAD | dff89780 (S4 freeze) |
| 实现 commits | 9a3070c8 + 64c65185 (中间有一次意外 revert abc710af 被再次 revert) |
| Push / merge / deploy | 未执行 |

## 1. 交付内容（后端安全）

1. **S4 known/neutral/unknown 收紧**: emotional_imprint._classify()
   中「有助手回复但无正则情绪命中」从 neutral 改为 unknown。
   neutral 保留 CHECK 约束供未来使用。旧印记不重写（INSERT OR IGNORE）。

2. **关闭 U2 二次 LLM 调用**: run.py::_honeyos_u2_post_completed
   立即 return。每批 MemoryDistiller 节省 1 次 async_call_llm
   (task=understanding_u2, max_tokens=600)。hook 绑定保持不变。

3. **continuity recall 生理学加权**: continuity.context_for_lane()
   在 _score >= 3 通过后，追加 epinephrine 派生的有界 boost
   (max 0.18)。只影响排序，不改变准入阈值，fail-open。

4. **遗忘边界确认**: continuity.db status 字段 active/archived/
   forgotten 正确区分自动归档与用户遗忘；cognitive_memory.sqlite
   用 memory_tombstones 实现 suppression。两条路径在本轮验证无冲突。

## 2. 未交付（PARTIAL）

- U2 同批次 distillation 整合（改 prompt + JSON schema）
- 前端图谱 UI（标签节点 + 记忆节点 + 时间轨迹）
- S4 情绪印记 recall 端注入（等 U2 整合后做）
- 旧窗口未整理补偿（6 门槛 + 40 上限）

## 3. 保持不变

- MemoryDistiller 阈值、prompt、schema、五类分类
- G2 两套 DB 与晋升规则
- open_loop 完成/隐藏/解决状态机
- Study 用户计划系统
- 全部 honeyos/understanding/ 模块代码（旧 store/schema/policy 不动）
- emotion hook downstream_holder 可变模式（保留给未来 U2）
- 九项 momentary_state / 九项 physiology_shadow
- memory_salience 持久强化规则

## 4. 模型成本

| 项目 | S3.1 | S4.5 | 变化 |
|---|---|---|---|
| 普通聊天主模型 | 每轮 1 次 | 每轮 1 次 | 无变化 |
| MemoryDistiller 主模型 | 每批 1 次 | 每批 1 次 | 无变化 |
| U2 二次 LLM call | 每批 1 次 | 0 | **-1/批** |
| Physiology Qwen | 后台维护 | 后台维护 | 无变化 |
| continuity phys boost | — | 每 recall ~0.18ms | 可忽略 |
| max_tokens/批 | — | -600 | **-600/批** |
| 上下文字符增量 | — | 0 | 无变化 |

## 5. 测试

- S4 专项: 19 passed（test_neutral 期望值已更新为 unknown）
- 核心回归（companion + memory + emotion + distillation）:
  153 passed
- 全量排除 aiohttp: 887 passed / 19 pre-existing failed / 18 skipped
- py_compile: OK
- git diff --check: OK
- 真实模型调用: 0, token: 0, 费用: 0

## 6. 回滚

    git revert 64c65185
    git revert 9a3070c8
    # 或切回
    git checkout feat/s4-longterm-memory-emotional-imprint

## 7. 后续

1. **U2 同批次 distillation 整合** 优先级最高 — 关闭二调后必须
   给 distillation prompt 追加 user_understandings 字段。
2. 修复 FakeDistiller.home mock（可跟 1 一起）
3. 前端图谱（需独立技术栈评估）
4. S4 recall 端 emotion_imprint 注入（等 U2 后）

完成状态: PARTIAL（后端安全项全部交付）
停止位置: 未进入 S5/S6/S7，未 push/merge/deploy
