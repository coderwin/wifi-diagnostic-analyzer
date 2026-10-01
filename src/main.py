"""Wi-Fi Sentinel 메인 진입점 CLI"""
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.logger import logger
from src.config import settings

def main():
    print(r"""
  __          ___ _____ _    _____            _   _            _ 
  \ \        / (_)  ___(_)  / ____|          | | (_)          | |
   \ \  /\  / / _| |_   _  | (___   ___ _ __ | |_ _ _ __   ___| |
    \ \/  \/ / | |  _| | |  \___ \ / _ \ '_ \| __| | '_ \ / _ \ |
     \  /\  /  | | |   | |  ____) |  __/ | | | |_| | | | |  __/ |
      \/  \/   |_|_|   |_| |_____/ \___|_| |_|\__|_|_| |_|\___|_|
                     Intelligent Wi-Fi Diagnostic & Incident Analyzer
    """)
    settings.ensure_directories()
    logger.info("Wi-Fi Sentinel 초기화 완료 (버전 0.1.0)")
    logger.info(f"데이터 디렉터리: {settings.DATA_DIR}")
    logger.info(f"리포트 디렉터리: {settings.REPORTS_DIR}")

if __name__ == "__main__":
    main()
