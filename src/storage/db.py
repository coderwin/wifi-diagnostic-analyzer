import json
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Boolean,
    Text,
    create_engine,
    desc,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from src.config import settings
from src.models.incident import Incident, RootCauseType
from src.models.metrics import (
    ConnectivityProbeResult,
    NetworkHealthStatus,
    WifiBand,
    WifiInterfaceInfo,
    WifiMetricsSnapshot,
    WifiState,
)
from src.utils.logger import logger

Base = declarative_base()


class MetricLogRecord(Base):
    """시계열 메트릭 로그 테이블"""
    __tablename__ = "metrics_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    os_type = Column(String(20), nullable=False)
    health_status = Column(String(30), nullable=False, index=True)
    wifi_connected = Column(Boolean, nullable=False)
    
    # Wi-Fi 상세
    ssid = Column(String(100), default="")
    bssid = Column(String(50), default="")
    signal_percent = Column(Integer, default=0)
    rssi_dbm = Column(Integer, nullable=True)
    channel = Column(Integer, default=0)
    band = Column(String(20), default="")
    tx_rate_mbps = Column(Float, nullable=True)
    rx_rate_mbps = Column(Float, nullable=True)

    # 핑 & 연결성 프로브
    gateway_ip = Column(String(50), nullable=True)
    gateway_ping_ms = Column(Float, nullable=True)
    internet_ping_ms = Column(Float, nullable=True)
    dns_resolved = Column(Boolean, default=False)
    dns_latency_ms = Column(Float, nullable=True)
    http_ok = Column(Boolean, default=False)
    http_latency_ms = Column(Float, nullable=True)
    wired_connected = Column(Boolean, default=False)


class IncidentRecord(Base):
    """장애 발생 및 분석 사건 기록 테이블"""
    __tablename__ = "incidents"

    id = Column(String(100), primary_key=True)
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    root_cause = Column(String(50), nullable=False, index=True)
    confidence_score = Column(Float, default=0.0)
    summary = Column(Text, default="")
    evidence_json = Column(Text, default="[]")
    recommendations_json = Column(Text, default="[]")
    pattern_note = Column(Text, nullable=True)
    snapshot_count = Column(Integer, default=1)


class DatabaseStorage:
    """SQLite 데이터베이스 관리자"""

    def __init__(self, db_path: Optional[str] = None):
        settings.ensure_directories()
        self.db_url = f"sqlite:///{db_path or settings.DB_PATH}"
        self.engine = create_engine(self.db_url, echo=False)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def save_snapshot(self, snapshot: WifiMetricsSnapshot) -> int:
        """메트릭 스냅샷 기록 저장"""
        session = self.Session()
        try:
            wifi = snapshot.wifi_info
            probe = snapshot.probe
            rec = MetricLogRecord(
                timestamp=snapshot.timestamp,
                os_type=snapshot.os_type,
                health_status=snapshot.health_status.value,
                wifi_connected=snapshot.wifi_connected,
                ssid=wifi.ssid if wifi else "",
                bssid=wifi.bssid if wifi else "",
                signal_percent=wifi.signal_percent if wifi else 0,
                rssi_dbm=wifi.rssi_dbm if wifi else None,
                channel=wifi.channel if wifi else 0,
                band=wifi.band.value if wifi else "",
                tx_rate_mbps=wifi.tx_rate_mbps if wifi else None,
                rx_rate_mbps=wifi.rx_rate_mbps if wifi else None,
                gateway_ip=probe.gateway_ip,
                gateway_ping_ms=probe.gateway_ping_ms,
                internet_ping_ms=probe.internet_ping_ms,
                dns_resolved=probe.dns_resolved,
                dns_latency_ms=probe.dns_latency_ms,
                http_ok=probe.http_ok,
                http_latency_ms=probe.http_latency_ms,
                wired_connected=probe.wired_connected,
            )
            session.add(rec)
            session.commit()
            return rec.id
        except Exception as e:
            session.rollback()
            logger.error(f"스냅샷 저장 실패: {e}")
            return -1
        finally:
            session.close()

    def save_incident(self, incident: Incident):
        """장애 사건 저장 또는 업데이트 (Upsert)"""
        session = self.Session()
        try:
            rec = session.query(IncidentRecord).filter(IncidentRecord.id == incident.id).first()
            if not rec:
                rec = IncidentRecord(
                    id=incident.id,
                    start_time=incident.start_time,
                    end_time=incident.end_time,
                    duration_seconds=incident.duration_seconds,
                    root_cause=incident.root_cause.value,
                    confidence_score=incident.confidence_score,
                    summary=incident.summary,
                    evidence_json=json.dumps(incident.evidence, ensure_ascii=False),
                    recommendations_json=json.dumps(incident.recommendations, ensure_ascii=False),
                    pattern_note=incident.pattern_note,
                    snapshot_count=incident.snapshot_count,
                )
                session.add(rec)
            else:
                rec.end_time = incident.end_time
                rec.duration_seconds = incident.duration_seconds
                rec.root_cause = incident.root_cause.value
                rec.confidence_score = incident.confidence_score
                rec.summary = incident.summary
                rec.evidence_json = json.dumps(incident.evidence, ensure_ascii=False)
                rec.recommendations_json = json.dumps(incident.recommendations, ensure_ascii=False)
                rec.pattern_note = incident.pattern_note
                rec.snapshot_count = incident.snapshot_count
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"인시던트 저장 실패: {e}")
        finally:
            session.close()

    def get_incidents(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Incident]:
        """지정 기간 장애 목록 조회"""
        session = self.Session()
        try:
            q = session.query(IncidentRecord)
            if start_time:
                q = q.filter(IncidentRecord.start_time >= start_time)
            if end_time:
                q = q.filter(IncidentRecord.start_time <= end_time)
            recs = q.order_by(desc(IncidentRecord.start_time)).limit(limit).all()

            results: List[Incident] = []
            for r in recs:
                try:
                    ev = json.loads(r.evidence_json) if r.evidence_json else []
                except Exception:
                    ev = []
                try:
                    rec = json.loads(r.recommendations_json) if r.recommendations_json else []
                except Exception:
                    rec = []

                results.append(
                    Incident(
                        id=r.id,
                        start_time=r.start_time,
                        end_time=r.end_time,
                        duration_seconds=r.duration_seconds,
                        root_cause=RootCauseType(r.root_cause) if r.root_cause in RootCauseType._value2member_map_ else RootCauseType.UNKNOWN,
                        confidence_score=r.confidence_score,
                        summary=r.summary,
                        evidence=ev,
                        recommendations=rec,
                        pattern_note=r.pattern_note,
                        snapshot_count=r.snapshot_count,
                    )
                )
            return results
        finally:
            session.close()

    def get_snapshots(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 2000,
    ) -> List[MetricLogRecord]:
        """지정 기간 메트릭 스냅샷 조회"""
        session = self.Session()
        try:
            q = session.query(MetricLogRecord)
            if start_time:
                q = q.filter(MetricLogRecord.timestamp >= start_time)
            if end_time:
                q = q.filter(MetricLogRecord.timestamp <= end_time)
            return q.order_by(MetricLogRecord.timestamp.asc()).limit(limit).all()
        finally:
            session.close()

    def cleanup_old_metrics(self, days_retention: int = 30) -> int:
        """오래된 메트릭 로그 자동 정리 (데이터 보존 정책)"""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_retention)
        session = self.Session()
        try:
            deleted_count = session.query(MetricLogRecord).filter(MetricLogRecord.timestamp < cutoff).delete()
            session.commit()
            if deleted_count > 0:
                logger.info(f"오래된 메트릭 {deleted_count}건 정리 완료 (기준: {cutoff})")
            return deleted_count
        except Exception as e:
            session.rollback()
            logger.error(f"메트릭 정리 실패: {e}")
            return 0
        finally:
            session.close()
