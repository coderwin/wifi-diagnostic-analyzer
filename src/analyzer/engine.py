import asyncio
from typing import Callable, Optional

from src.analyzer.detector import IncidentDetector
from src.collectors.base import BaseCollector
from src.collectors.factory import get_collector
from src.config import settings
from src.models.incident import Incident
from src.models.metrics import NetworkHealthStatus, WifiMetricsSnapshot
from src.utils.logger import logger


class MonitoringEngine:
    """적응형 동적 폴링 및 장애 실시간 모니터링 엔진"""

    def __init__(
        self,
        collector: Optional[BaseCollector] = None,
        on_snapshot: Optional[Callable[[WifiMetricsSnapshot], None]] = None,
        on_incident_start: Optional[Callable[[Incident], None]] = None,
        on_incident_resolved: Optional[Callable[[Incident], None]] = None,
    ):
        self.collector = collector or get_collector()
        self.detector = IncidentDetector(
            on_incident_start=on_incident_start,
            on_incident_resolved=on_incident_resolved,
        )
        self.on_snapshot = on_snapshot
        self.is_running = False
        self._task: Optional[asyncio.Task] = None

    async def run_once(self) -> WifiMetricsSnapshot:
        """스냅샷 1회 수집 및 분석"""
        snapshot = await self.collector.collect_snapshot()
        self.detector.process_snapshot(snapshot)
        if self.on_snapshot:
            self.on_snapshot(snapshot)
        return snapshot

    async def _loop(self):
        logger.info(
            f"🚀 Wi-Fi Sentinel 모니터링 시작 (평상시: {settings.NORMAL_POLL_INTERVAL_SEC}초, "
            f"장애 시 고해상도: {settings.HIGH_RES_POLL_INTERVAL_SEC}초)"
        )
        while self.is_running:
            try:
                snapshot = await self.collector.collect_snapshot()
                self.detector.process_snapshot(snapshot)

                if self.on_snapshot:
                    self.on_snapshot(snapshot)

                # 장애 중이면 1초 고해상도 폴링, 정상이면 5초 경량 폴링
                if self.detector.active_incident is not None:
                    sleep_interval = settings.HIGH_RES_POLL_INTERVAL_SEC
                else:
                    sleep_interval = settings.NORMAL_POLL_INTERVAL_SEC

                await asyncio.sleep(sleep_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"모니터링 루프 오류 발생: {e}", exc_info=True)
                await asyncio.sleep(settings.NORMAL_POLL_INTERVAL_SEC)

        logger.info("🛑 Wi-Fi Sentinel 모니터링 종료")

    def start(self):
        """비동기 모니터링 태스크 시작"""
        if not self.is_running:
            self.is_running = True
            self._task = asyncio.create_task(self._loop())

    def stop(self):
        """모니터링 태스크 정지"""
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
