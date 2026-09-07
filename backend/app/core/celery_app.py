"""Celery 应用配置。

Redis 同时承担 broker 与 result backend：API 只投递轻量任务消息，worker 再执行
耗时的 Agent 流程。这里集中配置序列化、确认、重试、超时和生命周期日志。
"""

from celery import Celery, Task
from celery.signals import (
    task_failure,
    task_postrun,
    task_prerun,
    task_retry,
    worker_init,
    worker_process_init,
)
from app.core.langsmith_tracing import (
    configure_langsmith_tracing,
)

from app.core.config import settings

celery_app = Celery(
    "metis",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    # 任务序列化：仅接受 JSON，避免 worker 反序列化不可信对象。
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # 任务执行：完成后才确认；worker 异常退出时任务可重新入队。
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # 长任务场景下减少单个 worker 的预取，分配更公平。
    # Worker 管理
    worker_max_tasks_per_child=100,  # 每执行 100 个任务重启子进程，控制长期内存增长。
    worker_disable_rate_limits=False,
    # 时间限制：soft limit 先给任务收尾机会，hard limit 是最终强制边界。
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT,
    task_soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT,
    # Result backend 中的任务结果保留 1 小时。
    result_expires=3600,
    result_backend_transport_options={"master_name": "mymaster"},
    # 统一使用 UTC，避免 worker 所在时区影响调度与日志。
    timezone="UTC",
    enable_utc=True,
)

# =========================================================
# LangSmith Tracing
# =========================================================


@worker_init.connect
def configure_langsmith_for_worker(**kwargs):
    """Worker 主进程启动时初始化 LangSmith。

    主要覆盖 solo / threads 等运行模式。
    """
    configure_langsmith_tracing()


@worker_process_init.connect
def configure_langsmith_for_worker_process(**kwargs):
    """每个实际执行任务的 Worker 子进程初始化 LangSmith。

    prefork / Windows spawn 场景下，
    每个 Worker Process 都拥有自己的 tracing 配置。
    """
    configure_langsmith_tracing()

# 所有后台任务共用的重试基类。
class BaseTask(Task):
    """提供自动重试与最终状态回调的 Celery Task 基类。"""

    autoretry_for = (Exception,)  # 任意未处理异常都会触发重试。
    retry_kwargs = {"max_retries": 3}
    retry_backoff = True  # 指数退避，避免持续快速重试。
    retry_backoff_max = 600  # 单次退避最多 10 分钟。
    retry_jitter = True  # 增加随机抖动，避免多个 worker 同时重试。

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """全部重试耗尽后记录失败。"""
        print(f"Task {task_id} failed: {exc}")

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """任务准备重试时记录当前次数。"""
        print(f"Task {task_id} retry {self.request.retries}/{self.max_retries}: {exc}")

    def on_success(self, retval, task_id, args, kwargs):
        """任务成功结束时记录结果。"""
        print(f"Task {task_id} succeeded")


# Celery 信号用于补充任务生命周期的可观测日志。
@task_prerun.connect
def task_prerun_handler(task_id, task, **kwargs):
    """记录任务开始。"""
    print(f"Task started: {task.name} [{task_id}]")


@task_postrun.connect
def task_postrun_handler(task_id, task, **kwargs):
    """记录任务结束。"""
    print(f"Task finished: {task.name} [{task_id}]")


@task_retry.connect
def task_retry_handler(sender, **kwargs):
    """记录任务重试。"""
    print(f"Task retrying: {sender.name}")


@task_failure.connect
def task_failure_handler(sender, task_id, exception, **kwargs):
    """记录任务失败。"""
    print(f"Task failed: {sender.name} [{task_id}] - {exception}")


# 导入 task 模块以完成 Celery 注册；放在末尾可避免循环导入。
from app.tasks import (
    agent_review_task,
    background_agent_task,
    summary_task,
)  # noqa: F401, E402
