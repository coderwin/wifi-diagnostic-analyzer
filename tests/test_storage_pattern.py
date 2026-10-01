import os
from datetime import datetime, timezone, timedelta
import pytest

from src.analyzer.pattern import IncidentPatternAnalyzer
from src.models.incident import Incident, RootCauseType
from src.models.metrics import (
    ConnectivityProbeResult,
    NetworkHealthStatus,
    WifiBand,
    WifiInterfaceInfo,
    WifiMetricsSnapshot,
    WifiState,
)
from src.storage.db import DatabaseStorage


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_sentinel.db"
    storage = DatabaseStorage(db_path=str(db_file))
    return storage


def test_storage_save_and_query_snapshot(temp_db):
    now = datetime.now(timezone.utc)
    snapshot = WifiMetricsSnapshot(
        timestamp=now,
        os_type="windows",
        health_status=NetworkHealthStatus.HEALTHY,
        wifi_connected=True,
        wifi_info=WifiInterfaceInfo(
            ssid="HMS",
            bssid="5a:86:94:cf:6f:5c",
            signal_percent=88,
            rssi_dbm=-48,
            channel=149,
            band=WifiBand.BAND_5GHZ,
        ),
        probe=ConnectivityProbeResult(
            gateway_ip="192.168.0.1",
            gateway_ping_ms=2.1,
            internet_ping_ms=12.4,
            dns_resolved=True,
            http_ok=True,
        ),
    )

    rec_id = temp_db.save_snapshot(snapshot)
    assert rec_id > 0

    snapshots = temp_db.get_snapshots()
    assert len(snapshots) == 1
    assert snapshots[0].ssid == "HMS"
    assert snapshots[0].gateway_ping_ms == 2.1
    assert snapshots[0].rssi_dbm == -48


def test_storage_save_and_query_incident(temp_db):
    now = datetime.now(timezone.utc)
    inc = Incident(
        id="inc-test-01",
        start_time=now,
        end_time=now + timedelta(seconds=45),
        duration_seconds=45.0,
        root_cause=RootCauseType.AP_HARDWARE_OR_CRASH,
        confidence_score=0.98,
        summary="09:00:03 공유기 무선 AP 크래시 감지",
        evidence=["Gateway Ping Timeout", "Wired OK"],
        recommendations=["공유기 예약 설정 확인"],
    )

    temp_db.save_incident(inc)
    incidents = temp_db.get_incidents()
    assert len(incidents) == 1
    assert incidents[0].id == "inc-test-01"
    assert incidents[0].root_cause == RootCauseType.AP_HARDWARE_OR_CRASH
    assert incidents[0].duration_seconds == 45.0
    assert "Gateway Ping Timeout" in incidents[0].evidence


def test_pattern_detection_daily_9am():
    """사용자 실제 시나리오: 최근 5일 중 4일 매일 오전 9시경 장애 발생 패턴 검증"""
    base_date = datetime(2026, 9, 25, 9, 0, 0, tzinfo=timezone.utc)
    incidents = []

    # Day 1: 08:58:30
    incidents.append(
        Incident(
            id="inc-d1",
            start_time=base_date + timedelta(days=0, minutes=-1.5),
            root_cause=RootCauseType.AP_HARDWARE_OR_CRASH,
            confidence_score=0.95,
        )
    )
    # Day 2: 09:01:10
    incidents.append(
        Incident(
            id="inc-d2",
            start_time=base_date + timedelta(days=1, minutes=1.2),
            root_cause=RootCauseType.AP_HARDWARE_OR_CRASH,
            confidence_score=0.95,
        )
    )
    # Day 3: 09:00:05
    incidents.append(
        Incident(
            id="inc-d3",
            start_time=base_date + timedelta(days=2, seconds=5),
            root_cause=RootCauseType.AP_HARDWARE_OR_CRASH,
            confidence_score=0.95,
        )
    )
    # Day 4: (장애 없음)
    # Day 5: 08:59:40
    incidents.append(
        Incident(
            id="inc-d5",
            start_time=base_date + timedelta(days=4, seconds=-20),
            root_cause=RootCauseType.AP_HARDWARE_OR_CRASH,
            confidence_score=0.95,
        )
    )

    insight = IncidentPatternAnalyzer.analyze_patterns(incidents, window_minutes=15)

    assert insight.has_recurring_pattern is True
    assert insight.target_hour == 9
    assert insight.days_with_incident == 4
    assert insight.incident_count_in_window == 4
    assert insight.primary_cause == RootCauseType.AP_HARDWARE_OR_CRASH
    assert "09:00경" in insight.pattern_summary or "09:" in insight.pattern_summary
    assert "공유기(AP)의 '매일 09시 자동 재부팅'" in insight.recommendation
    print(f"\n[Pattern Detected] {insight.pattern_summary}")
    print(f"[Recommendation] {insight.recommendation}")
