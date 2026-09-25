from __future__ import annotations

SKILL_GROUP_MANIFEST: dict[str, str] = {
    "study": "学习计划、复习、番茄钟、闪卡、抽题、课程资料",
    "files": "PDF、Word、PPT、CSV、上传文件读取与处理",
    "memory": "回忆、时间线、历史对话、用户偏好与关系连续性",
    "coding": "代码、报错、测试、Git、开发与调试",
    "research": "资料研究、比较、事实核验、论文与深度分析",
    "communication": "邮件、消息、联系人、日程沟通",
    "automation": "提醒、定时任务、未来执行、条件监控",
    "media": "图片、音频、视频、视觉内容",
    "system": "HoneyOS 设置、运行状态、本地环境、系统维护",
}

def compact_manifest() -> str:
    return "\n".join(f"- {name}: {description}" for name, description in SKILL_GROUP_MANIFEST.items())
