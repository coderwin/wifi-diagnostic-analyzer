from datetime import datetime, timezone
import pytest

from src.analyzer.detector import IncidentDetector
from src.analyzer.rules import RuleMatrixEngine
from src.models.incident import RootCauseType
from src.models.metrics import (
    ConnectivityProbeResult,
    NearbyNetwork,
    NetworkHealthStatus,
    WifiBand,
    WifiInterfaceInfo,
    WifiMetricsSnapshot,
    WifiState,
)


def create_mock_snapshot(
    health: NetworkHealthStatus = NetworkHealthStatus.HEALTHY,
    gw_ping: float = 2.0,
    inet_ping: float = 15.0,
    wired: bool = False,
    rssi: int = -50,
    channel: int = 149,
    ssid: str = "Office-5G",
    bssid: str = "aa:bb:cc:dd:ee:01",
    dns_ok: bool = True,
    http_ok: bool = True,
    nearby: list = None,
) -> WifiMetricsSnapshot:
    return WifiMetricsSnapshot(
        os_type="windows",
        health_status=health,
        wifi_connected=True,
        wifi_info=WifiInterfaceInfo(
            interface_name="Wi-Fi",
            state=WifiState.CONNECTED,
            ssid=ssid,
            bssid=bssid,
            signal_percent=90 if rssi > -70 else 20,
            rssi_dbm=rssi,
            channel=channel,
            band=WifiBand.BAND_5GHZ if channel > 14 else WifiBand.BAND_2_4GHZ,
        ),
        probe=ConnectivityProbeResult(
            gateway_ip="192.168.0.1",
            gateway_ping_ms=gw_ping,
            internet_ping_ms=inet_ping,
            dns_resolved=dns_ok,
            dns_latency_ms=10.0 if dns_ok else None,
            http_ok=http_ok,
            http_latency_ms=50.0 if http_ok else None,
            wired_connected=wired,
        ),
        nearby_networks=nearby or [],
    )


def test_rule_ap_hardware_crash():
    """핵심 시나리오: 유선 정상 + Wi-Fi RSSI 정상이나 무선 게이트웨이 무응답 (AP 크래시)"""
    snap = create_mock_snapshot(
        health=NetworkHealthStatus.GATEWAY_UNREACHABLE,
        gw_ping=None,       # Gateway Timeout
        inet_ping=None,     # Internet Timeout
        wired=True,         # 유선망 정상 연결
        rssi=-48,           # 신호 세기 매우 좋음
    )
    
    evaluation = RuleMatrixEngine.evaluate(snap)
    assert evaluation.root_cause == RootCauseType.AP_HARDWARE_OR_CRASH
    assert evaluation.confidence_score >= 0.95
    assert any("유선 이더넷" in ev for ev in evaluation.evidence)
    assert any("공유기(무선 AP)" in rec for rec in evaluation.recommendations)


def test_rule_isp_wan_down():
    """인터넷 회선 장애: 게이트웨이 정상 응답이나 외부 인터넷 단절"""
    snap = create_mock_snapshot(
        health=NetworkHealthStatus.WAN_DOWN,
        gw_ping=1.5,        # Gateway OK
        inet_ping=None,     # Internet Timeout
        http_ok=False,
    )
    
    evaluation = RuleMatrixEngine.evaluate(snap)
    assert evaluation.root_cause == RootCauseType.ISP_WAN_DOWN
    assert evaluation.confidence_score >= 0.90
    assert any("외부 공용 인터넷" in ev for ev in evaluation.evidence)


def test_rule_signal_weak():
    """신호 세기 급감 시나리오 (-85 dBm)"""
    snap = create_mock_snapshot(
        health=NetworkHealthStatus.DEGRADED,
        gw_ping=120.0,
        inet_ping=180.0,
        rssi=-85,
    )
    
    evaluation = RuleMatrixEngine.evaluate(snap)
    assert evaluation.root_cause == RootCauseType.SIGNAL_WEAK
    assert any("기준치" in ev for ev in evaluation.evidence)


def test_rule_dfs_channel_hop():
    """동일 AP의 채널 급변(DFS) 감지"""
    prev = create_mock_snapshot(channel=100)
    curr = create_mock_snapshot(channel=36)
    
    evaluation = RuleMatrixEngine.evaluate(curr, previous=prev)
    assert evaluation.root_cause == RootCauseType.DFS_CHANNEL_HOP
    assert any("100번에서 36번으로" in ev for ev in evaluation.evidence)


def test_incident_lifecycle():
    """장애 발생 -> 고해상도 지속 -> 복구 라이프사이클 테스트"""
    started_incidents = []
    resolved_incidents = []
    
    detector = IncidentDetector(
        on_incident_start=lambda inc: started_incidents.append(inc),
        on_incident_resolved=lambda inc: resolved_incidents.append(inc),
    )
    
    # 1. 정상 상태
    normal_snap = create_mock_snapshot(health=NetworkHealthStatus.HEALTHY)
    detector.process_snapshot(normal_snap)
    assert detector.active_incident is None
    
    # 2. 장애 발생
    failure_snap = create_mock_snapshot(
        health=NetworkHealthStatus.GATEWAY_UNREACHABLE,
        gw_ping=None,
        wired=True,
    )
    detector.process_snapshot(failure_snap)
    assert detector.active_incident is not None
    assert detector.active_incident.root_cause == RootCauseType.AP_HARDWARE_OR_CRASH
    assert len(started_incidents) == 1
    
    # 3. 장애 지속
    detector.process_snapshot(failure_snap)
    assert detector.active_incident.snapshot_count == 2
    
    # 4. 복구 완료
    recovered = detector.process_snapshot(normal_snap)
    assert detector.active_incident is None
    assert len(resolved_incidents) == 1
    assert recovered is not None
    assert recovered.duration_seconds is not None
    assert recovered.recovery_snapshot is not None
