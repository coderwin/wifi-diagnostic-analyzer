from abc import ABC, abstractmethod
from typing import Optional
from src.models.metrics import WifiMetricsSnapshot

class BaseCollector(ABC):
    """OS별 네트워크 상태 및 메트릭 수집기 기본 추상 클래스"""
    
    @abstractmethod
    async def collect_snapshot(self) -> WifiMetricsSnapshot:
        """현재 시점의 Wi-Fi 및 네트워크 상태 스냅샷 수집"""
        pass
    
    @abstractmethod
    def get_os_type(self) -> str:
        """지원 OS 명칭 반환 ('windows' | 'linux')"""
        pass
