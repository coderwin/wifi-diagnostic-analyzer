import logging
import sys
from pathlib import Path
from src.config import settings

def setup_logger(name: str = "wifi_sentinel") -> logging.Logger:
    """애플리케이션 전역 로거 설정"""
    settings.ensure_directories()
    
    logger = logging.getLogger(name)
    if logger.hasHandlers():
        return logger
        
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(log_level)
    
    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] [%(name)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # 1. 콘솔 핸들러
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 2. 파일 핸들러 (logs/wifi_sentinel.log)
    log_file = settings.LOGS_DIR / "wifi_sentinel.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger

logger = setup_logger()
