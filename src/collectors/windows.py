import asyncio
import re
import subprocess
from typing import List, Optional, Tuple

from src.collectors.base import BaseCollector
from src.collectors.probe import ConnectivityProbe
from src.models.metrics import (
    ConnectivityProbeResult,
    NearbyNetwork,
    NetworkHealthStatus,
    WifiBand,
    WifiInterfaceInfo,
    WifiMetricsSnapshot,
    WifiState,
)
from src.utils.logger import logger


class WindowsCollector(BaseCollector):
    """Windows 환경의 Wi-Fi 및 네트워크 상태 수집기"""

    def get_os_type(self) -> str:
        return "windows"

    def run_cmd(self, cmd: str) -> str:
        """Windows 셸 명령어 실행 및 출력 텍스트 반환"""
        try:
            res = subprocess.run(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5.0,
            )
            return res.stdout
        except Exception as e:
            logger.debug(f"명령어 실행 실패 ({cmd}): {e}")
            return ""

    def get_gateway_ip(self) -> Optional[str]:
        """IPv4 기본 게이트웨이 주소 조회 (route print 0.0.0.0 활용)"""
        output = self.run_cmd("route print 0.0.0.0")
        matches = re.findall(r"0\.0\.0\.0\s+0\.0\.0\.0\s+([0-9.]+)\s+([0-9.]+)", output)
        if matches:
            # 첫 번째 일치하는 IPv4 기본 게이트웨이 반환
            for gw, iface_ip in matches:
                if not gw.startswith("0.") and not gw.startswith("127."):
                    return gw
        return None

    def _parse_band(self, band_str: str) -> WifiBand:
        band_str = band_str.lower().strip()
        if "2.4" in band_str:
            return WifiBand.BAND_2_4GHZ
        elif "5" in band_str:
            return WifiBand.BAND_5GHZ
        elif "6" in band_str:
            return WifiBand.BAND_6GHZ
        return WifiBand.UNKNOWN

    def _parse_wifi_state(self, state_str: str) -> WifiState:
        state_str = state_str.lower().strip()
        if "연결됨" in state_str or "connected" in state_str:
            return WifiState.CONNECTED
        elif "연결 끊김" in state_str or "disconnected" in state_str:
            return WifiState.DISCONNECTED
        elif "연결하는 중" in state_str or "connecting" in state_str:
            return WifiState.CONNECTING
        return WifiState.UNKNOWN

    def parse_interfaces(self, output: str) -> Optional[WifiInterfaceInfo]:
        """'netsh wlan show interfaces' 출력 파싱"""
        if not output or "SSID" not in output:
            return None

        info = WifiInterfaceInfo()
        lines = output.splitlines()

        for line in lines:
            if ":" not in line:
                continue
            key, val = [part.strip() for part in line.split(":", 1)]
            key_lower = key.lower()

            # 인터페이스 이름
            if key_lower in ["이름", "name"]:
                info.interface_name = val
            # 상태
            elif key_lower in ["상태", "state"]:
                info.state = self._parse_wifi_state(val)
            # SSID (BSSID 줄 제외)
            elif key_lower == "ssid":
                info.ssid = val
            # AP BSSID
            elif key_lower in ["ap bssid", "bssid"]:
                info.bssid = val
            # 밴드 / 주파수
            elif key_lower in ["밴드", "band"]:
                info.band = self._parse_band(val)
            # 채널
            elif key_lower in ["채널", "channel"]:
                m = re.search(r"\d+", val)
                if m:
                    info.channel = int(m.group(0))
            # 신호 세기 (%)
            elif key_lower in ["신호", "signal"]:
                m = re.search(r"(\d+)%", val)
                if m:
                    info.signal_percent = int(m.group(1))
            # RSSI (dBm)
            elif key_lower == "rssi":
                m = re.search(r"(-?\d+)", val)
                if m:
                    info.rssi_dbm = int(m.group(1))
            # 무선 규격 (802.11 ax 등)
            elif key_lower in ["송수신 장치 종류", "radio type"]:
                info.radio_type = val
            # 전송/수신 속도
            elif "전송 속도" in key or "transmit rate" in key_lower:
                m = re.search(r"([0-9.]+)", val)
                if m:
                    info.tx_rate_mbps = float(m.group(1))
            elif "수신 속도" in key or "receive rate" in key_lower:
                m = re.search(r"([0-9.]+)", val)
                if m:
                    info.rx_rate_mbps = float(m.group(1))

        # RSSI 필드가 없는 구버전 Windows의 경우 signal_percent로 추정
        if info.rssi_dbm is None and info.signal_percent > 0:
            # 대략적인 변환식: RSSI(dBm) = (signal_percent / 2) - 100
            info.rssi_dbm = int((info.signal_percent / 2) - 100)

        return info

    def parse_nearby_networks(self, output: str) -> List[NearbyNetwork]:
        """'netsh wlan show networks mode=bssid' 출력 파싱"""
        nearby_list: List[NearbyNetwork] = []
        if not output:
            return nearby_list

        current_ssid = ""
        current_bssid = ""
        current_signal = 0
        current_channel = 0
        current_band = WifiBand.UNKNOWN
        current_auth = ""

        lines = output.splitlines()
        for line in lines:
            stripped = line.strip()
            if not stripped or ":" not in stripped:
                continue

            key, val = [part.strip() for part in stripped.split(":", 1)]
            key_lower = key.lower()

            # SSID 블록 시작
            if re.match(r"^ssid\s+\d+", key_lower):
                if current_bssid:
                    nearby_list.append(
                        NearbyNetwork(
                            ssid=current_ssid,
                            bssid=current_bssid,
                            signal_percent=current_signal,
                            rssi_dbm=int((current_signal / 2) - 100) if current_signal > 0 else None,
                            channel=current_channel,
                            band=current_band,
                            auth=current_auth,
                        )
                    )
                    current_bssid = ""
                    current_signal = 0
                    current_channel = 0
                    current_band = WifiBand.UNKNOWN
                current_ssid = val
            elif key_lower in ["인증", "authentication"]:
                current_auth = val
            elif re.match(r"^bssid\s+\d+", key_lower):
                # 새로운 BSSID 진입 전 이전 BSSID 저장
                if current_bssid:
                    nearby_list.append(
                        NearbyNetwork(
                            ssid=current_ssid,
                            bssid=current_bssid,
                            signal_percent=current_signal,
                            rssi_dbm=int((current_signal / 2) - 100) if current_signal > 0 else None,
                            channel=current_channel,
                            band=current_band,
                            auth=current_auth,
                        )
                    )
                current_bssid = val
                current_signal = 0
                current_channel = 0
                current_band = WifiBand.UNKNOWN
            elif key_lower in ["신호", "signal"]:
                m = re.search(r"(\d+)%", val)
                if m:
                    current_signal = int(m.group(1))
            elif key_lower in ["채널", "channel"]:
                m = re.search(r"\d+", val)
                if m:
                    current_channel = int(m.group(0))
            elif key_lower in ["밴드", "band"]:
                current_band = self._parse_band(val)

        # 마지막 네트워크 항목 추가
        if current_bssid:
            nearby_list.append(
                NearbyNetwork(
                    ssid=current_ssid,
                    bssid=current_bssid,
                    signal_percent=current_signal,
                    rssi_dbm=int((current_signal / 2) - 100) if current_signal > 0 else None,
                    channel=current_channel,
                    band=current_band,
                    auth=current_auth,
                )
            )

        return nearby_list

    async def collect_snapshot(self) -> WifiMetricsSnapshot:
        """Windows Wi-Fi 정보 및 비동기 프로브를 결합하여 스냅샷 생성"""
        loop = asyncio.get_running_loop()

        # 1. 셸 명령어 수집 (비동기 executor 실행)
        iface_out_task = loop.run_in_executor(None, self.run_cmd, "netsh wlan show interfaces")
        nearby_out_task = loop.run_in_executor(None, self.run_cmd, "netsh wlan show networks mode=bssid")
        gw_task = loop.run_in_executor(None, self.get_gateway_ip)

        iface_out, nearby_out, gateway_ip = await asyncio.gather(
            iface_out_task, nearby_out_task, gw_task
        )

        wifi_info = self.parse_interfaces(iface_out)
        nearby_networks = self.parse_nearby_networks(nearby_out)

        # 2. 다계층 연결성 프로브 수행
        probe_result = await ConnectivityProbe.probe(gateway_ip=gateway_ip)

        # 3. 헬스 상태 판별
        wifi_connected = (
            wifi_info is not None and wifi_info.state == WifiState.CONNECTED and bool(wifi_info.ssid)
        )

        health_status = NetworkHealthStatus.HEALTHY
        if not wifi_connected:
            health_status = NetworkHealthStatus.WIFI_DISCONNECTED
        elif probe_result.gateway_ip and probe_result.gateway_ping_ms is None:
            # Wi-Fi는 붙어있으나 게이트웨이 무응답 -> 공유기 AP 크래시 의심
            health_status = NetworkHealthStatus.GATEWAY_UNREACHABLE
        elif probe_result.internet_ping_ms is None:
            # 공유기는 되나 인터넷 무응답 -> 회선 문제
            health_status = NetworkHealthStatus.WAN_DOWN
        elif not probe_result.dns_resolved:
            health_status = NetworkHealthStatus.DNS_ERROR
        elif (probe_result.gateway_ping_ms and probe_result.gateway_ping_ms > 150) or not probe_result.http_ok:
            health_status = NetworkHealthStatus.DEGRADED

        return WifiMetricsSnapshot(
            os_type="windows",
            health_status=health_status,
            wifi_connected=wifi_connected,
            wifi_info=wifi_info,
            probe=probe_result,
            nearby_networks=nearby_networks,
        )
