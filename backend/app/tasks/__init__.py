"""Celery task 包。

导入各 task 模块，使 Celery worker 能在启动时完成任务注册。
"""

from app.tasks.agent_review_task import process_pr_review_with_agent
from app.tasks.background_agent_task import process_issue_with_agent
from app.tasks.summary_task import process_pr_summary_with_agent

__all__ = [
    "process_issue_with_agent",
    "process_pr_review_with_agent",
    "process_pr_summary_with_agent",
]
