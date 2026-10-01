import os
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings:
    """Wi-Fi Sentinel 시스템 환경 설정"""
    # 진단 폴링 주기
    NORMAL_POLL_INTERVAL_SEC: float = float(os.getenv("WIFI_POLL_INTERVAL", "5.0"))
    HIGH_RES_POLL_INTERVAL_SEC: float = float(os.getenv("WIFI_HIGH_RES_INTERVAL", "1.0"))
    
    # 네트워크 프로브 대상
    INTERNET_PING_HOST: str = os.getenv("WIFI_INTERNET_HOST", "8.8.8.8")
    BACKUP_INTERNET_HOST: str = os.getenv("WIFI_BACKUP_HOST", "1.1.1.1")
    DNS_TEST_HOST: str = os.getenv("WIFI_DNS_HOST", "www.google.com")
    HTTP_TEST_URL: str = os.getenv("WIFI_HTTP_URL", "https://www.google.com/generate_204")
    
    # 타임아웃 설정 (초)
    PING_TIMEOUT_SEC: float = float(os.getenv("WIFI_PING_TIMEOUT", "1.5"))
    DNS_TIMEOUT_SEC: float = float(os.getenv("WIFI_DNS_TIMEOUT", "2.0"))
    HTTP_TIMEOUT_SEC: float = float(os.getenv("WIFI_HTTP_TIMEOUT", "3.0"))
    
    # 신호 세기 임계치 (dBm)
    WEAK_SIGNAL_THRESHOLD_DBM: int = int(os.getenv("WIFI_WEAK_SIGNAL_DBM", "-80"))
    
    # 데이터베이스 및 파일 경로
    DATA_DIR: Path = Path(os.getenv("WIFI_DATA_DIR", str(BASE_DIR / "data")))
    DB_PATH: Path = DATA_DIR / "wifi_sentinel.db"
    REPORTS_DIR: Path = Path(os.getenv("WIFI_REPORTS_DIR", str(BASE_DIR / "reports")))
    LOGS_DIR: Path = Path(os.getenv("WIFI_LOGS_DIR", str(BASE_DIR / "logs")))
    TEMPLATES_DIR: Path = BASE_DIR / "templates"
    
    # 로깅 설정
    LOG_LEVEL: str = os.getenv("WIFI_LOG_LEVEL", "INFO")
    
    def ensure_directories(self) -> None:
        """필요한 디렉터리 자동 생성"""
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        self.LOGS_DIR.mkdir(parents=True, exist_ok=True)

settings = Settings()
