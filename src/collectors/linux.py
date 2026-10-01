import asyncio
import re
import subprocess
from typing import List, Optional

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


class LinuxCollector(BaseCollector):
    """Linux 환경의 Wi-Fi 및 네트워크 상태 수집기 (nmcli / iw 기반)"""

    def get_os_type(self) -> str:
        return "linux"

    def run_cmd(self, cmd: str) -> str:
        """리눅스 셸 명령어 실행 및 출력 반환"""
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
            logger.debug(f"Linux 명령어 실행 실패 ({cmd}): {e}")
            return ""

    def get_gateway_ip(self) -> Optional[str]:
        """리눅스 기본 게이트웨이 IP 조회 ('ip route show default' 활용)"""
        output = self.run_cmd("ip route show default")
        # default via 192.168.0.1 dev wlan0 proto dhcp metric 600
        m = re.search(r"default via ([0-9.]+)", output)
        if m:
            return m.group(1)

        # Fallback: /proc/net/route
        try:
            with open("/proc/net/route", "r") as f:
                for line in f.readlines()[1:]:
                    parts = line.strip().split()
                    if len(parts) >= 3 and parts[1] == "00000000":
                        gw_hex = parts[2]
                        # Little endian hex to IP
                        gw_int = int(gw_hex, 16)
                        return f"{gw_int & 0xFF}.{(gw_int >> 8) & 0xFF}.{(gw_int >> 16) & 0xFF}.{(gw_int >> 24) & 0xFF}"
        except Exception:
            pass

        return None

    def _channel_to_band(self, channel: int) -> WifiBand:
        if 1 <= channel <= 14:
            return WifiBand.BAND_2_4GHZ
        elif 36 <= channel <= 177:
            return WifiBand.BAND_5GHZ
        elif channel > 177:
            return WifiBand.BAND_6GHZ
        return WifiBand.UNKNOWN

    def parse_nmcli_active(self, output: str) -> Optional[WifiInterfaceInfo]:
        """'nmcli -t -f IN-USE,SSID,BSSID,CHAN,BARS,SIGNAL,SECURITY dev wifi' 활성 연결 파싱"""
        if not output:
            return None

        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            # ':'로 분리 (단, 이스케이프된 콜론 '\:' 처리 필요할 수 있음)
            parts = re.split(r"(?<!\\):", line)
            if len(parts) >= 6:
                in_use = parts[0].strip()
                if in_use == "*":
                    ssid = parts[1].replace(r"\:", ":").strip()
                    bssid = parts[2].replace(r"\:", ":").strip()
                    channel_str = parts[3].strip()
                    signal_str = parts[5].strip() if len(parts) > 5 else "0"

                    try:
                        channel = int(channel_str)
                    except ValueError:
                        channel = 0

                    try:
                        signal = int(signal_str)
                    except ValueError:
                        signal = 0

                    band = self._channel_to_band(channel)
                    rssi = int((signal / 2) - 100) if signal > 0 else None

                    return WifiInterfaceInfo(
                        interface_name="wlan0",
                        state=WifiState.CONNECTED,
                        ssid=ssid,
                        bssid=bssid,
                        signal_percent=signal,
                        rssi_dbm=rssi,
                        channel=channel,
                        band=band,
                    )
        return None

    def parse_nmcli_nearby(self, output: str) -> List[NearbyNetwork]:
        """주변 Wi-Fi 목록 파싱"""
        nearby_list: List[NearbyNetwork] = []
        if not output:
            return nearby_list

        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = re.split(r"(?<!\\):", line)
            if len(parts) >= 6:
                ssid = parts[1].replace(r"\:", ":").strip()
                bssid = parts[2].replace(r"\:", ":").strip()
                chan_str = parts[3].strip()
                sig_str = parts[5].strip() if len(parts) > 5 else "0"
                auth = parts[6].replace(r"\:", ":").strip() if len(parts) > 6 else ""

                try:
                    channel = int(chan_str)
                except ValueError:
                    channel = 0

                try:
                    signal = int(sig_str)
                except ValueError:
                    signal = 0

                nearby_list.append(
                    NearbyNetwork(
                        ssid=ssid,
                        bssid=bssid,
                        signal_percent=signal,
                        rssi_dbm=int((signal / 2) - 100) if signal > 0 else None,
                        channel=channel,
                        band=self._channel_to_band(channel),
                        auth=auth,
                    )
                )
        return nearby_list

    async def collect_snapshot(self) -> WifiMetricsSnapshot:
        """Linux Wi-Fi 정보 및 비동기 프로브 결합 스냅샷 생성"""
        loop = asyncio.get_running_loop()

        # nmcli 실행
        cmd = "nmcli -t -f IN-USE,SSID,BSSID,CHAN,BARS,SIGNAL,SECURITY dev wifi"
        wifi_out_task = loop.run_in_executor(None, self.run_cmd, cmd)
        gw_task = loop.run_in_executor(None, self.get_gateway_ip)

        wifi_out, gateway_ip = await asyncio.gather(wifi_out_task, gw_task)

        wifi_info = self.parse_nmcli_active(wifi_out)
        nearby_networks = self.parse_nmcli_nearby(wifi_out)

        probe_result = await ConnectivityProbe.probe(gateway_ip=gateway_ip)

        wifi_connected = (
            wifi_info is not None and wifi_info.state == WifiState.CONNECTED and bool(wifi_info.ssid)
        )

        health_status = NetworkHealthStatus.HEALTHY
        if not wifi_connected:
            health_status = NetworkHealthStatus.WIFI_DISCONNECTED
        elif probe_result.gateway_ip and probe_result.gateway_ping_ms is None:
            health_status = NetworkHealthStatus.GATEWAY_UNREACHABLE
        elif probe_result.internet_ping_ms is None:
            health_status = NetworkHealthStatus.WAN_DOWN
        elif not probe_result.dns_resolved:
            health_status = NetworkHealthStatus.DNS_ERROR
        elif (probe_result.gateway_ping_ms and probe_result.gateway_ping_ms > 150) or not probe_result.http_ok:
            health_status = NetworkHealthStatus.DEGRADED

        return WifiMetricsSnapshot(
            os_type="linux",
            health_status=health_status,
            wifi_connected=wifi_connected,
            wifi_info=wifi_info,
            probe=probe_result,
            nearby_networks=nearby_networks,
        )
