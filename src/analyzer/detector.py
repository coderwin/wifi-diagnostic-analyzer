import uuid
from datetime import datetime, timezone
from typing import Callable, List, Optional

from src.analyzer.rules import DiagnosticEvaluation, RuleMatrixEngine
from src.models.incident import Incident, RootCauseType
from src.models.metrics import NetworkHealthStatus, WifiMetricsSnapshot
from src.utils.logger import logger


class IncidentDetector:
    """장애 발생 감지, 지속 시간 추적, 복구 완료 라이프사이클 관리자"""

    def __init__(
        self,
        on_incident_start: Optional[Callable[[Incident], None]] = None,
        on_incident_resolved: Optional[Callable[[Incident], None]] = None,
    ):
        self.active_incident: Optional[Incident] = None
        self.previous_snapshot: Optional[WifiMetricsSnapshot] = None
        self.on_incident_start = on_incident_start
        self.on_incident_resolved = on_incident_resolved

    def process_snapshot(self, snapshot: WifiMetricsSnapshot) -> Optional[Incident]:
        """새 스냅샷을 받아 장애 발생 여부 및 복구 여부를 판정"""
        is_issue = snapshot.health_status != NetworkHealthStatus.HEALTHY
        now = datetime.now(timezone.utc)
        resolved_incident: Optional[Incident] = None

        if is_issue:
            # 1. 원인 진단 평가
            eval_res: DiagnosticEvaluation = RuleMatrixEngine.evaluate(
                current=snapshot,
                previous=self.previous_snapshot,
            )

            if self.active_incident is None:
                # 새로운 장애 발생
                incident_id = f"inc-{now.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
                self.active_incident = Incident(
                    id=incident_id,
                    start_time=now,
                    root_cause=eval_res.root_cause,
                    confidence_score=eval_res.confidence_score,
                    summary=f"{now.strftime('%H:%M:%S')} {eval_res.summary}",
                    evidence=eval_res.evidence,
                    recommendations=eval_res.recommendations,
                    trigger_snapshot=snapshot,
                    snapshot_count=1,
                )
                logger.warning(
                    f"⚠️ [장애 감지] ID: {incident_id} | 원인: {eval_res.root_cause.value} "
                    f"(신뢰도 {eval_res.confidence_score * 100:.0f}%) | {eval_res.summary}"
                )
                if self.on_incident_start:
                    self.on_incident_start(self.active_incident)
            else:
                # 기존 장애 지속 중 -> 스냅샷 카운트 증가 및 더 구체적인 원인 발생 시 갱신
                self.active_incident.snapshot_count += 1
                if eval_res.confidence_score > self.active_incident.confidence_score:
                    self.active_incident.root_cause = eval_res.root_cause
                    self.active_incident.confidence_score = eval_res.confidence_score
                    self.active_incident.summary = f"{self.active_incident.start_time.strftime('%H:%M:%S')} {eval_res.summary}"
                    self.active_incident.evidence = eval_res.evidence
                    self.active_incident.recommendations = eval_res.recommendations

        else:
            # 상태 정상
            if self.active_incident is not None:
                # 장애 복구 완료
                self.active_incident.end_time = now
                self.active_incident.recovery_snapshot = snapshot
                duration = (now - self.active_incident.start_time).total_seconds()
                self.active_incident.duration_seconds = round(duration, 1)

                logger.info(
                    f"✅ [장애 복구] ID: {self.active_incident.id} | "
                    f"지속 시간: {self.active_incident.duration_seconds}초 | 원인: {self.active_incident.root_cause.value}"
                )

                resolved_incident = self.active_incident
                if self.on_incident_resolved:
                    self.on_incident_resolved(resolved_incident)

                self.active_incident = None

        self.previous_snapshot = snapshot
        return resolved_incident
