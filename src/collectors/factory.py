import sys
from src.collectors.base import BaseCollector
from src.collectors.windows import WindowsCollector
from src.collectors.linux import LinuxCollector


def get_collector() -> BaseCollector:
    """운영체제에 맞는 수집기 인스턴스를 반환하는 팩토리 함수"""
    if sys.platform.startswith("win"):
        return WindowsCollector()
    elif sys.platform.startswith("linux"):
        return LinuxCollector()
    else:
        # 기타 플랫폼 (macOS 등 테스트 시 Linux 포맷 유사 처리)
        return LinuxCollector()
