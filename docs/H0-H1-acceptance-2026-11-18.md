# HoneyOS H0–H1 后续验收

验收基线为 `acceptance/h0-h1` 上的 `1385717`，包含 C1.3 气泡移植、Qwen 故障降级和 H1 事件台账。构建在 WSL 临时目录完成。

| 项目 | 结果 |
| --- | --- |
| 实际运行版 | 开机后 Gateway 进程引用 `g2-personality-fde3827b`。`GET /health` 与 `GET /` 均为 200，首页、`index-s3cB5R6v.js` 和 `index-CZ7vrEka.css` 与该发布目录一致。 |
| 数据恢复 | 从 `~/.honeyos/release-backups/g2-personality.zFAvhz` 以只读方式打开备份，通过 SQLite Backup API 恢复到私有临时目录。会话、响应、连续性、人格候选、Study 和附件索引六库的 `PRAGMA integrity_check` 全部为 `ok`。会话库有 23 个会话与 173 条消息可读，Study 备份有 1 条计划与 0 条任务。临时数据库副本已移除。 |
| 前端 | 复用本机 WSL 依赖，锁文件忽略 CRLF/LF 后一致。Vitest 16 个文件、55 项通过，其中 C1.3 分段 14 项。TypeScript 和 Vite 构建通过，产物为 `index-BXGhY9dh.js`。Vite 报告主 JS 包约 642 kB。 |
| 后端 | 事件台账、Qwen 降级、状态评估、路由、Study 与提醒组 139 项通过、9 项真实模型用例按默认条件跳过、2 个子测试通过。另跑了 Companion Web、会话连续性和模型意图组，96 项通过。 |
| 模型锁 | 临时会话库验证已确认的锁会在普通续聊中复用。显式单轮模型可覆盖当轮选择并保留持久锁，锁定路由不可用返回 409 `model_lock_unavailable`。 |
| 主模型传输 | 正式配置为 `openai-codex`，未选用 `model.openai_runtime: codex_app_server`。隔离 WSL 的 stdio 握手与真实模型回合均通过。HoneyOS 的 Codex 子进程收到合成请求并返回预期文本 `HONEYOS_CLI_OK`，全程 25.65 秒。临时配置与凭证副本已清理。 |

## Qwen3-4B 实机结果

以 Windows 的 `qwen3-4b-instruct-2507-Q4_K_M.gguf` 启动随机回环端口上的临时 llama-server，测试结束后停止该进程。输入和状态库均为合成资料。两轮原提示词中，日记唯一副本丢失与他人修复项目均触发预期状态。房间从灰色突然变成亮蓝色两轮都被误判为 `unexpected_progress`。

- 原提示词复测耗时分别为冷请求 12.96 秒、热惊讶 7.12 秒、热援助 7.95 秒。第一次测试分别为 17.57、9.06、7.43 秒。
- 停止 llama-server 后，降级返回耗时分别为 2.13 和 2.44 秒。
- 分类提示词的试改增加了房间变色示例，并将目标进展限定为既有目标的可衡量进展或完成。同一错误仍然出现，该轮还误分了项目援助和五分钟完成绘画。试改已撤回。

原分类句为 `surprise is an unexpected change to Honey's situation; unexpected_progress is faster or better progress toward Honey's goal;`。完整提示词和测试输入分别位于 [pre_reply_appraisal.py](../honeyos/companion/pre_reply_appraisal.py) 和 [test_pre_reply_appraisal.py](../tests/honeyos/test_pre_reply_appraisal.py)。

## 验收边界

本轮恢复演练覆盖六个 SQLite 数据库。附件实物、虚拟磁盘和完整应用级恢复另需演练。真实 Qwen 测量覆盖回复前评估阶段，9 项真实模型用例尚未全量执行。短句路由测试可得到 `model_tier=local`，当前这一路由信息用于工具和上下文选择，未确认 Gateway 会自动切换最终回复模型。浏览器真实断网后的重试仍待实机复现。H1 仍由受信任的本机代码显式调用，Gateway 的授权界面属于后续开发。

## 发布收尾

2026-11-18，Gateway 从 `fde3827` 切至 `a10dadfb2e441b3ee63bc0ece401486534db74c7`。发布目录为 `/home/zyh20/projects/honeyos-releases/h0-h1-a10dadfb`，从该 Git 提交导出并放入当次构建资源 `index-BXGhY9dh.js`。

- 发布前回归通过 55 项前端测试和 250 项后端测试，另有 2 项子测试通过、18 项需显式启用本地模型的参数化测试跳过。TypeScript 与 Vite 生产构建通过。
- 隔离 Gateway 的流式聊天确认第一轮先完成，后台评估随后写入，下一轮请求才携带更新后的状态。前后两轮使用模拟回复模型和受控评估结果。另用实际 Qwen 在独立临时库完成了丢失事件评估，提交后台队列低于 1 毫秒，模型评估 9.74 秒，状态写入成功。
- 隔离客户端读到首个 SSE 文本片段后主动关闭 TCP 连接。通过运行 ID 查询到同一轮成功完成，模型端只收到一次请求。
- 发布后 Gateway 服务为 `active`，Gateway 与 Qwen 健康检查均返回 `ok`。首页和 Study 引用新资产，实际 JS 响应 SHA-256 与发布文件一致。Companion 会话初始化、Study 摄像头策略、未确认模拟题生成请求返回 HTTP 400 均通过检查。
- 切换前保存了六个通过 SQLite `quick_check` 的数据库，以及人格候选审计和原始服务配置。备份目录为 `/home/zyh20/.honeyos/release-backups/h0-h1.yrwY38`。

回滚服务可从该备份目录取 `gateway-original.conf`，恢复至 `~/.config/systemd/user/honeyos-gateway.service.d/20-verified-study-release.conf`，再执行 `systemctl --user daemon-reload` 和 `systemctl --user restart honeyos-gateway.service`。数据快照可独立用于恢复演练。

本次上线范围覆盖 C1.3、H1.1–H1.2 底座及回复后状态评估。Qwen 的事件分类边界与此前记录一致，整盘恢复和 H1 用户授权界面属于后续工作。
