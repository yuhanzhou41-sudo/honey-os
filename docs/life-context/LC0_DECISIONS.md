# Life Context LC-0 初步技术决策

截至 2026-11-19 已读上游文档及仓库说明。采用任何代码之前，需固定提交并复核许可证文本、Android Manifest、锁定依赖、监听及出站路径。

| 来源 | 当前决策 | 需要验证 |
| --- | --- | --- |
| [ActivityWatch Android](https://github.com/ActivityWatch/aw-android) | 沿用官方安装的版本做时长基线。仓库标注 MPL-2.0。 | 真机版本、事件字段、锁屏及后台行为。 |
| [ActivityWatch Sync](https://docs.activitywatch.net/en/latest/syncing.html) | 参考设备独占写入、只读导入的目录模式。传输需要独立工具。 | 分别跟踪源端、共享目录和导入后的副本，验证删除结果。 |
| [aw-screentext](https://github.com/sam0ed/aw-screentext) | 仅参考节点读取及标题模式。其说明披露本地 Dashboard API key 被停用，现阶段不采用该构建。 | 核查监听、敏感过滤、原生库来源及 MPL-2.0 合规。 |
| [TextGrabber](https://github.com/freemedom/TextGrabber) | 参考去重思路。上游说明覆盖所有可见 UI，超出 Honey 白名单范围，仓库标注 MIT。 | 核查持久化前过滤、节点边界及依赖，评估自行实现。 |
| [HistoryHub](https://github.com/LifeArchiveProject/HistoryHub) | 后续可独立评估授权导入。浏览器历史和 B 站历史保留各自来源。 | 核查 B 站登录态的存储、接口维护与撤回，凭据不进入 Honey。 |
| [Syncthing-Fork](https://github.com/researchxxl/syncthing-android) | 优先试验合成批次的本地网络传输。仓库标注 MPL-2.0。 | 关闭公网发现和中继后验证配对、锁屏重连、状态回执和副本清理。 |
| [华为分享](https://consumer.huawei.com/cn/support/content/zh-cn15947796/) | 备选传输验证。 | Windows 是否能限制访问目录，锁屏、重启和自动连接是否稳定。 |
| [Android AccessibilityService](https://developer.android.com/reference/android/accessibilityservice/AccessibilityService) | 参考系统接口实现最小探针，先只读取公开测试页面的必要节点。 | HarmonyOS 4.2 对窗口和节点的实际可见性。 |

## 风险与观察点

- 私聊、密码、验证码和输入框泄漏。白名单与敏感规则在持久化前执行。用公开测试页面及合成敏感输入核查数据库、日志与队列。
- 局域网暴露及配对凭据泄漏。验证只接受配对设备，记录网络访问路径，避免把凭据放入样本或日志。
- 后台进程终止、中断、重复与迟到批次。模拟锁屏和断电，记录时间缺口，未确认覆盖前暂停清理。
- 第三方历史 API 失效。单独标记来源不可用，避免把来源空缺当作无活动。
- 页面文字诱导调用工具。分析模型和会话入口把采集内容作为数据，候选产物无权决定外部动作。
