from datetime import datetime, timezone
from src.models.metrics import (
    WifiMetricsSnapshot,
    WifiInterfaceInfo,
    ConnectivityProbeResult,
    NearbyNetwork,
    WifiBand,
    WifiState,
    NetworkHealthStatus,
)
from src.models.incident import Incident, RootCauseType


def test_wifi_metrics_snapshot_creation():
    snapshot = WifiMetricsSnapshot(
        os_type="windows",
        health_status=NetworkHealthStatus.HEALTHY,
        wifi_connected=True,
        wifi_info=WifiInterfaceInfo(
            interface_name="Wi-Fi",
            state=WifiState.CONNECTED,
            ssid="Office-5G",
            bssid="aa:bb:cc:dd:ee:ff",
            signal_percent=95,
            rssi_dbm=-52,
            channel=36,
            band=WifiBand.BAND_5GHZ,
            radio_type="802.11ax",
        ),
        probe=ConnectivityProbeResult(
            gateway_ip="192.168.0.1",
            gateway_ping_ms=2.5,
            internet_ping_ms=15.2,
            dns_resolved=True,
            dns_latency_ms=10.0,
            http_ok=True,
            http_latency_ms=35.0,
            wired_connected=False,
        ),
        nearby_networks=[
            NearbyNetwork(
                ssid="Office-Guest",
                bssid="aa:bb:cc:dd:ee:fe",
                signal_percent=80,
                rssi_dbm=-60,
                channel=36,
                band=WifiBand.BAND_5GHZ,
            )
        ]
    )
    
    assert snapshot.os_type == "windows"
    assert snapshot.wifi_connected is True
    assert snapshot.wifi_info.ssid == "Office-5G"
    assert snapshot.probe.gateway_ping_ms == 2.5
    assert len(snapshot.nearby_networks) == 1


def test_incident_model_creation():
    incident = Incident(
        id="inc-20261001-090003",
        start_time=datetime.now(timezone.utc),
        root_cause=RootCauseType.AP_HARDWARE_OR_CRASH,
        confidence_score=0.92,
        summary="09:00:03 Wi-Fi 장애 감지: 게이트웨이 무응답, 유선망 정상",
        evidence=[
            "Gateway (192.168.0.1) Ping Timeout",
            "Wired Ethernet Ping (192.168.0.1) OK (1.2ms)",
            "Wi-Fi RSSI 정상 (-50 dBm)"
        ],
        recommendations=[
            "공유기 예약 재부팅 및 무선 스케줄 설정 확인",
            "공유기 무선 펌웨어 최신 업데이트"
        ]
    )
    
    assert incident.root_cause == RootCauseType.AP_HARDWARE_OR_CRASH
    assert incident.confidence_score == 0.92
    assert len(incident.evidence) == 3
