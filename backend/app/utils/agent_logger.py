"""记录 Agent 操作的结构化文件日志。"""

import json
import logging
from datetime import datetime
from pathlib import Path


def setup_agent_logger(agent_id: str, log_dir: str = "logs/agents") -> logging.Logger:
    """为单次 Agent 执行创建文件 logger。

    Args:
        agent_id: 用于日志文件命名的 Agent ID
        log_dir: 日志目录

    Returns:
        已配置的 logger 实例
    """
    # 首次运行时创建日志目录。
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    # agent_id 作为 logger 名称，隔离不同 Agent 的日志。
    logger_name = f"agent.{agent_id}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)

    # 移除旧 handler，避免重复初始化后同一日志写入多次。
    logger.handlers.clear()

    # 文件 handler 保存详细 JSON 日志。
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = Path(log_dir) / f"{agent_id}_{timestamp}.log"

    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)

    # 结构化 JSON formatter 便于机器检索。
    class JSONFormatter(logging.Formatter):
        def format(self, record):
            log_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "level": record.levelname,
                "agent_id": agent_id,
                "message": record.getMessage(),
            }

            # 存在扩展字段时一并写入结构化记录。
            if hasattr(record, "extra"):
                log_data.update(record.extra)

            return json.dumps(log_data)

    file_handler.setFormatter(JSONFormatter())
    logger.addHandler(file_handler)

    # 控制台 handler 使用适合人工监控的简洁格式。
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    logger.info(f"Agent logger initialized: {log_file}")

    return logger
