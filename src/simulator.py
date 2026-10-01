"""09:00 Wi-Fi AP 크래시 가상 장애 시나리오 시뮬레이터"""
from datetime import datetime, timezone, timedelta
import random
from typing import List, Optional

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
from src.utils.logger import logger


def generate_simulated_dataset(
    storage: DatabaseStorage,
    days: int = 5,
    crash_days_count: int = 4,
    start_date: Optional[datetime] = None,
) -> List[Incident]:
    """
    최근 N일 중 M일간 매일 오전 09:00경 공유기 무선 AP 장애가 발생하는
    실제 시나리오 데이터를 생성하여 DB에 주입합니다.
    """
    if start_date is None:
        start_date = datetime.now(timezone.utc) - timedelta(days=days - 1)

    generated_incidents: List[Incident] = []

    logger.info(f"🧪 가상 시뮬레이션 데이터 생성 시작 (총 {days}일 중 {crash_days_count}일간 09:00 장애)")

    for d in range(days):
        cur_date = (start_date + timedelta(days=d)).date()
        # 4일간은 09:00 장애 발생, 나머지 날은 정상
        has_incident = (d < crash_days_count)

        # 08:30 ~ 09:30 (1시간 동안 2분 단위 스냅샷 생성)
        base_time = datetime.combine(cur_date, datetime.min.time(), tzinfo=timezone.utc).replace(hour=8, minute=30)
        
        incident_started = False
        incident_start_time = None
        incident_id = f"inc-sim-{cur_date.strftime('%Y%m%d')}-0900"

        # 각 날짜별 09:00 전후 약간의 현실적 분산 (08:59, 09:00, 09:01 등)
        outage_start_minute = 59 + (d % 3)  # 59(08:59), 60(09:00), 61(09:01)
        outage_start_time = datetime.combine(cur_date, datetime.min.time(), tzinfo=timezone.utc).replace(hour=8, minute=0) + timedelta(minutes=outage_start_minute)
        outage_end_time = outage_start_time + timedelta(minutes=6)

        for step in range(30):
            snap_time = base_time + timedelta(minutes=step * 2)
            is_during_outage = has_incident and (outage_start_time <= snap_time <= outage_end_time)

            if is_during_outage:
                # 장애 순간: 유선 정상, Wi-Fi 신호는 정상 수신되나 무선 게이트웨이 무응답
                snap = WifiMetricsSnapshot(
                    timestamp=snap_time,
                    os_type="windows",
                    health_status=NetworkHealthStatus.GATEWAY_UNREACHABLE,
                    wifi_connected=True,
                    wifi_info=WifiInterfaceInfo(
                        interface_name="Wi-Fi",
                        state=WifiState.CONNECTED,
                        ssid="Office_AP_5G",
                        bssid="5a:86:94:cf:6f:5c",
                        signal_percent=88,
                        rssi_dbm=-48,
                        channel=149,
                        band=WifiBand.BAND_5GHZ,
                        radio_type="802.11 ax",
                    ),
                    probe=ConnectivityProbeResult(
                        gateway_ip="192.168.0.1",
                        gateway_ping_ms=None,       # 패킷 손실 100%
                        internet_ping_ms=None,
                        dns_resolved=False,
                        http_ok=False,
                        wired_connected=True,       # 유선은 정상
                    ),
                )
                if not incident_started:
                    incident_started = True
                    incident_start_time = snap_time
            else:
                # 정상 상태: 게이트웨이 2~5ms, 인터넷 12~18ms
                snap = WifiMetricsSnapshot(
                    timestamp=snap_time,
                    os_type="windows",
                    health_status=NetworkHealthStatus.HEALTHY,
                    wifi_connected=True,
                    wifi_info=WifiInterfaceInfo(
                        interface_name="Wi-Fi",
                        state=WifiState.CONNECTED,
                        ssid="Office_AP_5G",
                        bssid="5a:86:94:cf:6f:5c",
                        signal_percent=88 + random.randint(-3, 3),
                        rssi_dbm=-48 + random.randint(-2, 2),
                        channel=149,
                        band=WifiBand.BAND_5GHZ,
                        radio_type="802.11 ax",
                    ),
                    probe=ConnectivityProbeResult(
                        gateway_ip="192.168.0.1",
                        gateway_ping_ms=round(random.uniform(2.0, 5.0), 2),
                        internet_ping_ms=round(random.uniform(12.0, 18.0), 2),
                        dns_resolved=True,
                        dns_latency_ms=round(random.uniform(10.0, 20.0), 2),
                        http_ok=True,
                        http_latency_ms=round(random.uniform(80.0, 150.0), 2),
                        wired_connected=True,
                    ),
                )

            storage.save_snapshot(snap)

        if incident_started and incident_start_time:
            end_time = incident_start_time + timedelta(minutes=6)
            inc = Incident(
                id=incident_id,
                start_time=incident_start_time,
                end_time=end_time,
                duration_seconds=360.0,
                root_cause=RootCauseType.AP_HARDWARE_OR_CRASH,
                confidence_score=0.98,
                summary=f"{incident_start_time.strftime('%H:%M:%S')} 공유기 무선 AP 모듈 장애 (유선 정상, 게이트웨이 무응답)",
                evidence=[
                    "기본 게이트웨이(192.168.0.1) 무응답 (Packet Loss 100%)",
                    "동일 시각 유선 이더넷(LAN) 연결은 정상 작동 중",
                    "Wi-Fi 신호 세기는 -48 dBm (88%)로 양호하게 감지됨",
                ],
                recommendations=[
                    "공유기 관리자 페이지에서 '예약 재부팅' 또는 'Wi-Fi 켜짐/꺼짐 스케줄' 설정 확인",
                    "공유기 무선 펌웨어 최신 버전 업데이트 및 과열/메모리 누수 점검",
                ],
            )
            storage.save_incident(inc)
            generated_incidents.append(inc)

    logger.info(f"✔ 시뮬레이션 데이터 주입 완료: 인시던트 {len(generated_incidents)}건 생성")
    return generated_incidents
