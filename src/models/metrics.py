from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class WifiBand(str, Enum):
    BAND_2_4GHZ = "2.4GHz"
    BAND_5GHZ = "5GHz"
    BAND_6GHZ = "6GHz"
    UNKNOWN = "Unknown"


class WifiState(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    SCANNING = "scanning"
    UNKNOWN = "unknown"


class NearbyNetwork(BaseModel):
    """주변 Wi-Fi AP 정보"""
    ssid: str = ""
    bssid: str = ""
    signal_percent: int = 0
    rssi_dbm: Optional[int] = None
    channel: int = 0
    band: WifiBand = WifiBand.UNKNOWN
    auth: str = ""


class WifiInterfaceInfo(BaseModel):
    """현재 연결된 Wi-Fi 인터페이스 상세 정보"""
    interface_name: str = ""
    state: WifiState = WifiState.UNKNOWN
    ssid: str = ""
    bssid: str = ""
    signal_percent: int = 0
    rssi_dbm: Optional[int] = None
    channel: int = 0
    band: WifiBand = WifiBand.UNKNOWN
    radio_type: str = ""          # e.g., 802.11ax, 802.11ac, 802.11n
    tx_rate_mbps: Optional[float] = None
    rx_rate_mbps: Optional[float] = None


class ConnectivityProbeResult(BaseModel):
    """네트워크 다계층 연결성 핑 및 통신 프로브 결과"""
    gateway_ip: Optional[str] = None
    gateway_ping_ms: Optional[float] = None      # None = Packet Loss / Timeout
    internet_ping_ms: Optional[float] = None     # 8.8.8.8 등 외부 IP
    dns_resolved: bool = False
    dns_latency_ms: Optional[float] = None
    http_ok: bool = False
    http_latency_ms: Optional[float] = None
    wired_connected: bool = False
    wired_gateway_ping_ms: Optional[float] = None


class NetworkHealthStatus(str, Enum):
    HEALTHY = "HEALTHY"                     # 모든 연결 정상
    DEGRADED = "DEGRADED"                   # 지연시간 증가 또는 패킷 손실 발생
    WIFI_DISCONNECTED = "WIFI_DISCONNECTED" # Wi-Fi 연결 끊김
    GATEWAY_UNREACHABLE = "GATEWAY_UNREACHABLE" # 공유기 응답 없음 (무선 AP 장애 유력)
    WAN_DOWN = "WAN_DOWN"                   # 공유기는 되나 외부 인터넷 불능 (회선 문제)
    DNS_ERROR = "DNS_ERROR"                 # IP 통신은 되나 도메인 풀이 실패


class WifiMetricsSnapshot(BaseModel):
    """단일 시점에 수집된 종합 네트워크 메트릭 스냅샷"""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    os_type: str = "unknown"  # "windows" | "linux"
    health_status: NetworkHealthStatus = NetworkHealthStatus.HEALTHY
    wifi_connected: bool = False
    wifi_info: Optional[WifiInterfaceInfo] = None
    probe: ConnectivityProbeResult = Field(default_factory=ConnectivityProbeResult)
    nearby_networks: List[NearbyNetwork] = Field(default_factory=list)
