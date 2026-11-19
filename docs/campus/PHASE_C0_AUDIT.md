# C0 校园抽屉审计与阶段报告

2026-11-19。离线审计和已登录门户首页观察完成，子系统现场核查待完成。本轮交付本报告、[模块覆盖矩阵](MODULE_COVERAGE.md)、[架构草案](ARCHITECTURE.md)和[安全边界](SECURITY_BOUNDARIES.md)四份文档。

## 基线和复用清单

| 范围 | 核验结果 |
| --- | --- |
| Windows 开发检出 | `HoneyOS-development`，`feature/honeyos-integration`，基线 `ef2b8c5df853ed9720c87cf62be29a42d4c3ddb3`。已有四个修改及三个未跟踪文件，见下文。 |
| WSL 历史仓库 | Ubuntu 24.04 的 `~/projects/honey-os`，`feature/chat-message-batching`，HEAD `1b3caa6e`，存在本地改动。 |
| WSL 运行服务 | 用户级 `honeyos-gateway.service` 为 active，工作目录为 `~/.honeyos`。活动进程的 `PYTHONPATH` 指向 `~/projects/honeyos-releases/campus-ef2b8c5.o3GYgq`。发布目录无可读的 Git HEAD，名称提示来源提交，已核对课表模块存在且文件指纹与开发工作区不同。 |
| Study UI 与 HTTP | 复用 `StudyPage` 的校园抽屉、`StudyCampusPanel` 和已有的 Gateway 事件控制鉴权。日历 POST 是读取入口，按日返回课表。 |
| 浏览器和会话 | CQMU 适配器已有专用 Edge 配置、脚本超时与交互登录路径。核对 Profile 隔离、持久化和清除前，现有链路只能作为 C1 基线。通用浏览器工具只参考本机进程管理等实现。 |
| Honey 工具与权限 | 工作工具已有 `read_cqmu_timetable` 动作，调用同一来源适配器并返回节次占用。后续复用工具注册及权限校验方式，将校园能力收敛到统一服务。 |
| 存储与调度 | `StudyRepository` 提供 SQLite 事务、表初始化与记录版本字段。`study.storage` 提供独立的资料库清单。`study.reminders` 使用已有调度任务创建、更新和删除接口。这些可供 Campus 参考，数据及授权保持独立。 |

原工作区修改为 `frontend/src/api/client.ts`、`frontend/src/features/study/StudyCampusPanel.tsx`、`honeyos/tools/cqmu_timetable.py`、`honeyos/tools/cqmu_timetable_reader.js`。原未跟踪文件为 `frontend/src/features/study/StudyCampusPanel.test.tsx`、`honeyos/tools/cqmu_exams.js`、`honeyos/tools/cqmu_semesters.js`。当前课表适配器依赖未跟踪的学期脚本，是开发工作区与可复现检出需要区分的一处依赖。考试脚本单独存在，校园日历路由未接入考试返回。

## 验证结果

| 核验 | 实际结果 |
| --- | --- |
| `python -m pytest -q -p no:cacheprovider tests/honeyos/study/test_campus_calendar.py` | 1 项通过，验证详细视图和已确认的空课日期。 |
| 在前端运行 `npm.cmd test -- src/features/study/StudyCampusPanel.test.tsx src/features/study/StudyPage.test.tsx` | 2 个文件共 8 项通过。 |
| 对课表、学期、考试脚本分别运行 `node --check` | 三项语法检查通过。 |
| `python -m pytest -q -p no:cacheprovider tests/honeyos/study --disable-warnings` | Windows 上观察到失败，交付核查时未获得完整汇总。另用 `-x --tb=short` 复跑，5 项通过后停在跨盘引用测试，实际异常为无法读取原文件，与预期的重复引用提示不匹配。原因尚未定位。 |
| 校方现场与截图 | 用户自行登录并打开门户首页及图书馆。通过 Windows 无障碍视图核对两个站点及图书馆首页的「座位预约」链接。链接的输入位置不可用，预约子系统未验证。门户「服务大厅」由用户指出，目录待核对。未采集截图或响应样本。 |

## C1 最小变更与验收

将现有本机专用 Edge 链路收敛成可管理的 Campus 会话。C1 首先验证专用 Profile 的归属、权限和浏览器调试通道隔离。能复用 Windows Edge 时沿用，在受控链路不适用时评估 WSLg Playwright。新增最小会话状态、打开官方登录和退出或清除专用会话能力，复用当前 Gateway 鉴权及 Study 登录入口，保持旧日历契约。

验收包括有效会话重启后复用、过期后返回人工认证提示、跨系统需单独认证时能区分、取消登录可返回抽屉、清除会话后恢复待登录、其他浏览器 Profile 无影响，以及输出和日志无敏感凭据。至少复跑本报告的定向后端和前端测试，并记录现场验证证据。先补齐校方模块现场核验和覆盖矩阵，再开始 C1 的真实会话验证。

### 下一阶段 Codex 任务

> 在 HoneyOS-development 核查当前分支、HEAD、未提交改动与运行发布目录。依照 C0 覆盖矩阵完成真实只读站点核验，由用户在已确认的官方入口自行登录。完成后实施 C1 最小会话管理，优先复用专用 Windows Edge Profile 和既有 Study 日历契约。先验证本机会话隔离，再验证重启复用、失效提示、跨系统认证和会话清除。附实际测试、未验证项、回滚方式和阶段提交，保留原有未提交修改。
