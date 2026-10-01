from typing import List, Optional, Tuple
from src.config import settings
from src.models.incident import RootCauseType
from src.models.metrics import NetworkHealthStatus, WifiMetricsSnapshot, WifiState


class DiagnosticEvaluation:
    """원인 진단 평가 결과"""

    def __init__(
        self,
        root_cause: RootCauseType,
        confidence_score: float,
        summary: str,
        evidence: List[str],
        recommendations: List[str],
    ):
        self.root_cause = root_cause
        self.confidence_score = confidence_score
        self.summary = summary
        self.evidence = evidence
        self.recommendations = recommendations


class RuleMatrixEngine:
    """네트워크 메트릭 스냅샷 기반 원인 추론 룰 엔진"""

    @classmethod
    def evaluate(
        cls,
        current: WifiMetricsSnapshot,
        previous: Optional[WifiMetricsSnapshot] = None,
    ) -> DiagnosticEvaluation:
        evidence: List[str] = []
        recommendations: List[str] = []

        wifi = current.wifi_info
        probe = current.probe

        # 1. 무선 어댑터 자체가 비활성화 / 꺼짐
        if not current.wifi_connected or (wifi and wifi.state == WifiState.DISCONNECTED):
            if not wifi or not wifi.ssid:
                evidence.append("Wi-Fi 어댑터가 분리되었거나 비활성화 상태입니다.")
                recommendations.extend([
                    "Wi-Fi 어댑터 전원 절약 설정(장치 관리자 -> 전원 관리)을 해제하세요.",
                    "Wi-Fi 드라이버를 최신 버전으로 업데이트하세요."
                ])
                return DiagnosticEvaluation(
                    root_cause=RootCauseType.ADAPTER_ISSUE,
                    confidence_score=0.85,
                    summary="Wi-Fi 어댑터 비활성화 또는 드라이버 오류 감지",
                    evidence=evidence,
                    recommendations=recommendations,
                )

        gw_down = (probe.gateway_ip is not None and probe.gateway_ping_ms is None)
        inet_down = (probe.internet_ping_ms is None)
        http_down = not probe.http_ok
        dns_down = not probe.dns_resolved

        rssi = wifi.rssi_dbm if (wifi and wifi.rssi_dbm is not None) else -60
        signal_pct = wifi.signal_percent if wifi else 0

        # 2. 채널 급변(DFS 또는 채널 호핑) 감지
        if previous and previous.wifi_info and wifi:
            if (
                previous.wifi_info.bssid == wifi.bssid
                and previous.wifi_info.channel != wifi.channel
                and previous.wifi_info.channel > 0
                and wifi.channel > 0
            ):
                evidence.append(
                    f"AP 채널이 {previous.wifi_info.channel}번에서 {wifi.channel}번으로 실시간 변경되었습니다."
                )
                recommendations.extend([
                    "공유기 설정에서 무선 채널을 '자동(Auto/DFS)' 대신 '고정 채널(예: 36, 40, 44, 48번)'로 지정하세요."
                ])
                return DiagnosticEvaluation(
                    root_cause=RootCauseType.DFS_CHANNEL_HOP,
                    confidence_score=0.90,
                    summary="무선 AP 채널 자동 변경(DFS/호핑)으로 인한 일시 단절",
                    evidence=evidence,
                    recommendations=recommendations,
                )

        # 3. [핵심 시나리오] 공유기 무선 AP 장애 (유선 LAN 정상 또는 Wi-Fi RSSI는 양호하나 게이트웨이 무응답)
        if gw_down:
            evidence.append(f"기본 게이트웨이({probe.gateway_ip})에 대한 Ping 응답이 없습니다 (Packet Loss 100%).")

            if probe.wired_connected:
                evidence.append("동일 시간대 유선 이더넷(LAN) 연결은 정상 작동 중입니다.")
                evidence.append(f"Wi-Fi 신호 세기는 {rssi} dBm ({signal_pct}%)로 정상 수신되고 있습니다.")
                recommendations.extend([
                    "공유기(무선 AP)의 무선 모듈 프로세스가 멈추었거나 펌웨어 크래시가 발생했습니다.",
                    "공유기 관리자 페이지에서 '예약 재부팅' 또는 'Wi-Fi 켜짐/꺼짐 스케줄' 설정을 확인하세요.",
                    "공유기 제조사의 최신 펌웨어로 업그레이드하거나 공유기 AS/교체를 권장합니다."
                ])
                return DiagnosticEvaluation(
                    root_cause=RootCauseType.AP_HARDWARE_OR_CRASH,
                    confidence_score=0.98,
                    summary="공유기 무선 AP 모듈 장애 (유선 정상, 무선 게이트웨이 무응답)",
                    evidence=evidence,
                    recommendations=recommendations,
                )

            # 유선 연결이 없는 단일 Wi-Fi 환경일 때도 RSSI가 정상이면 AP 모듈 장애 확률 높음
            if rssi > settings.WEAK_SIGNAL_THRESHOLD_DBM:
                evidence.append(f"Wi-Fi 신호 세기는 {rssi} dBm ({signal_pct}%)로 강하게 감지되나 통신이 두절되었습니다.")
                recommendations.extend([
                    "공유기(AP)의 무선 프로세스 중단 또는 메모리 부족으로 인한 크래시 가능성이 유력합니다.",
                    "공유기 재시작 후 반복 발생 시 무선 스케줄 및 펌웨어 업데이트를 확인하세요."
                ])
                return DiagnosticEvaluation(
                    root_cause=RootCauseType.AP_HARDWARE_OR_CRASH,
                    confidence_score=0.90,
                    summary="공유기 무선 AP 응답 불가 (신호 세기 양호)",
                    evidence=evidence,
                    recommendations=recommendations,
                )

        # 4. 신호 세기 급감 (거리 및 차폐 문제)
        if rssi <= settings.WEAK_SIGNAL_THRESHOLD_DBM or signal_pct < 25:
            evidence.append(f"Wi-Fi 신호 세기(RSSI)가 {rssi} dBm ({signal_pct}%)로 기준치({settings.WEAK_SIGNAL_THRESHOLD_DBM} dBm) 이하로 급감했습니다.")
            if gw_down or inet_down:
                evidence.append("신호 미약으로 인한 패킷 손실 및 연결 단절이 발생했습니다.")
            recommendations.extend([
                "공유기와의 거리를 좁히거나 사이에 장애물(콘크리트 벽, 철제 파티션)이 있는지 확인하세요.",
                "Wi-Fi 확장기(증폭기/Mesh AP) 설치를 고려하세요."
            ])
            return DiagnosticEvaluation(
                root_cause=RootCauseType.SIGNAL_WEAK,
                confidence_score=0.88,
                summary="Wi-Fi 수신 신호 강도 미약으로 인한 연결 불안정",
                evidence=evidence,
                recommendations=recommendations,
            )

        # 5. 인터넷 회선(WAN/모뎀) 장애 (게이트웨이 응답 정상 + 외부 인터넷 불가)
        if not gw_down and inet_down:
            evidence.append(f"공유기 게이트웨이({probe.gateway_ip}) 통신은 정상 응답({probe.gateway_ping_ms:.1f}ms)합니다.")
            evidence.append(f"외부 공용 인터넷({settings.INTERNET_PING_HOST})으로의 Ping이 실패했습니다.")
            recommendations.extend([
                "공유기와 통신사 모뎀(WAN) 간의 케이블 연결 상태를 확인하세요.",
                "통신사(ISP) 고객센터에 해당 지역 인터넷 회선 장애 여부를 문의하세요."
            ])
            return DiagnosticEvaluation(
                root_cause=RootCauseType.ISP_WAN_DOWN,
                confidence_score=0.95,
                summary="외부 인터넷 회선(WAN) 장애 (내부 공유기 통신 정상)",
                evidence=evidence,
                recommendations=recommendations,
            )

        # 6. DNS 장애 (외부 IP Ping은 되나 도메인 풀이 실패)
        if not inet_down and dns_down:
            evidence.append(f"외부 IP({settings.INTERNET_PING_HOST}) 통신은 정상이나 도메인 풀이({settings.DNS_TEST_HOST})가 실패했습니다.")
            recommendations.extend([
                "공유기 또는 PC의 기본 DNS를 구글 공용 DNS(8.8.8.8, 8.8.4.4) 또는 Cloudflare(1.1.1.1)로 변경해 보세요."
            ])
            return DiagnosticEvaluation(
                root_cause=RootCauseType.DNS_FAILURE,
                confidence_score=0.92,
                summary="도메인 네임서버(DNS) 질의 실패",
                evidence=evidence,
                recommendations=recommendations,
            )

        # 7. 무선 채널 간섭 및 혼잡 (주변 동일 채널 AP 다수)
        if wifi and current.nearby_networks:
            same_channel_aps = [
                ap for ap in current.nearby_networks
                if ap.channel == wifi.channel and ap.bssid != wifi.bssid
            ]
            if len(same_channel_aps) >= 4 or (wifi.band.value == "2.4GHz" and len(same_channel_aps) >= 3):
                evidence.append(
                    f"현재 사용 중인 {wifi.channel}번 채널에 동일 대역 AP가 {len(same_channel_aps)}개 중첩되어 있습니다."
                )
                recommendations.extend([
                    "2.4GHz 대역 대신 혼잡도가 낮은 5GHz 대역 SSID로 연결하세요.",
                    "공유기 관리자 페이지에서 주변과 겹치지 않는 빈 채널을 수동 선택하세요."
                ])
                return DiagnosticEvaluation(
                    root_cause=RootCauseType.CHANNEL_INTERFERENCE,
                    confidence_score=0.75,
                    summary="주변 Wi-Fi 채널 중첩으로 인한 전파 간섭 및 혼잡",
                    evidence=evidence,
                    recommendations=recommendations,
                )

        # 8. 원인 불명 또는 정상
        if current.health_status == NetworkHealthStatus.HEALTHY:
            return DiagnosticEvaluation(
                root_cause=RootCauseType.UNKNOWN,
                confidence_score=0.0,
                summary="모든 네트워크 지표가 정상 범위입니다.",
                evidence=["게이트웨이, 인터넷, DNS, HTTP 프로브 모두 정상 통과"],
                recommendations=[],
            )

        return DiagnosticEvaluation(
            root_cause=RootCauseType.UNKNOWN,
            confidence_score=0.30,
            summary="복합적이거나 일시적인 네트워크 지연 현상",
            evidence=["원인을 특정할 수 있는 명확한 실패 패턴이 감지되지 않았습니다."],
            recommendations=["지속적으로 모니터링하여 로그를 누적 수집합니다."],
        )
