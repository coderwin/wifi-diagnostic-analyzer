import pytest
from src.collectors.windows import WindowsCollector
from src.collectors.linux import LinuxCollector
from src.collectors.factory import get_collector
from src.models.metrics import WifiBand, WifiState, NetworkHealthStatus


SAMPLE_NETSH_INTERFACES_KO = """
시스템에 1 인터페이스가 있습니다. 

    이름                   : Wi-Fi
    설명                   : Intel(R) Wi-Fi 6 AX201 160MHz
    상태                   : 연결됨
    SSID                   : HMS
    AP BSSID               : 5a:86:94:cf:6f:5c
    밴드                   : 5GHz
    채널                : 149
    송수신 장치 종류       : 802.11 ax
    수신 속도(Mbps)        : 961
    전송 속도(Mbps)        : 613
    신호                   : 88% 
    Rssi                   : -48
    프로필                : HMS 
"""

SAMPLE_NETSH_INTERFACES_EN = """
There is 1 interface on the system:

    Name                   : Wi-Fi
    Description            : Intel(R) Wi-Fi 6 AX201 160MHz
    State                  : connected
    SSID                   : Office_Network
    BSSID                  : aa:bb:cc:dd:ee:01
    Band                   : 2.4GHz
    Channel                : 6
    Radio type             : 802.11ax
    Receive rate (Mbps)    : 300
    Transmit rate (Mbps)   : 300
    Signal                 : 75% 
    Rssi                   : -62
    Profile                : Office_Network 
"""

SAMPLE_NETSH_NEARBY_KO = """
인터페이스 이름: Wi-Fi 
현재 2개 네트워크를 볼 수 있습니다. 

SSID 1 : HMS-Guest
    네트워크 종류            : 인프라
    인증          : WPA2-개인
    BSSID 1                 : 5a:86:94:9f:6f:5c
         신호             : 87%  
         밴드               : 2.4GHz
         채널            : 2 
    BSSID 2                 : 5a:86:94:df:6f:5c
         신호             : 85%  
         밴드               : 5GHz
         채널            : 149 

SSID 2 : Nearby_AP
    네트워크 종류            : 인프라
    인증          : WPA2-개인
    BSSID 1                 : 58:86:94:63:cd:80
         신호             : 50%  
         밴드               : 5GHz
         채널            : 44 
"""

SAMPLE_NMCLI_OUTPUT = """
*:Office-WiFi:aa\\:bb\\:cc\\:dd\\:ee\\:10:36:▂▄▆█:80:WPA2
 :Guest-WiFi:aa\\:bb\\:cc\\:dd\\:ee\\:20:1:▂▄__:45:WPA2
"""


def test_windows_parse_interfaces_korean():
    collector = WindowsCollector()
    info = collector.parse_interfaces(SAMPLE_NETSH_INTERFACES_KO)
    
    assert info is not None
    assert info.interface_name == "Wi-Fi"
    assert info.state == WifiState.CONNECTED
    assert info.ssid == "HMS"
    assert info.bssid == "5a:86:94:cf:6f:5c"
    assert info.band == WifiBand.BAND_5GHZ
    assert info.channel == 149
    assert info.signal_percent == 88
    assert info.rssi_dbm == -48
    assert info.rx_rate_mbps == 961.0
    assert info.tx_rate_mbps == 613.0


def test_windows_parse_interfaces_english():
    collector = WindowsCollector()
    info = collector.parse_interfaces(SAMPLE_NETSH_INTERFACES_EN)
    
    assert info is not None
    assert info.interface_name == "Wi-Fi"
    assert info.state == WifiState.CONNECTED
    assert info.ssid == "Office_Network"
    assert info.bssid == "aa:bb:cc:dd:ee:01"
    assert info.band == WifiBand.BAND_2_4GHZ
    assert info.channel == 6
    assert info.signal_percent == 75
    assert info.rssi_dbm == -62


def test_windows_parse_nearby_networks():
    collector = WindowsCollector()
    nearby = collector.parse_nearby_networks(SAMPLE_NETSH_NEARBY_KO)
    
    assert len(nearby) == 3
    assert nearby[0].ssid == "HMS-Guest"
    assert nearby[0].bssid == "5a:86:94:9f:6f:5c"
    assert nearby[0].channel == 2
    assert nearby[0].band == WifiBand.BAND_2_4GHZ
    
    assert nearby[1].ssid == "HMS-Guest"
    assert nearby[1].bssid == "5a:86:94:df:6f:5c"
    assert nearby[1].channel == 149
    assert nearby[1].band == WifiBand.BAND_5GHZ
    
    assert nearby[2].ssid == "Nearby_AP"
    assert nearby[2].channel == 44


def test_linux_nmcli_parser():
    collector = LinuxCollector()
    info = collector.parse_nmcli_active(SAMPLE_NMCLI_OUTPUT)
    
    assert info is not None
    assert info.ssid == "Office-WiFi"
    assert info.bssid == "aa:bb:cc:dd:ee:10"
    assert info.channel == 36
    assert info.band == WifiBand.BAND_5GHZ
    assert info.signal_percent == 80
    assert info.state == WifiState.CONNECTED

    nearby = collector.parse_nmcli_nearby(SAMPLE_NMCLI_OUTPUT)
    assert len(nearby) == 2
    assert nearby[1].ssid == "Guest-WiFi"
    assert nearby[1].channel == 1
    assert nearby[1].band == WifiBand.BAND_2_4GHZ


def test_factory_returns_collector():
    collector = get_collector()
    assert collector is not None
    assert collector.get_os_type() in ["windows", "linux"]


@pytest.mark.asyncio
async def test_live_snapshot_collection():
    collector = get_collector()
    snapshot = await collector.collect_snapshot()
    
    assert snapshot is not None
    assert snapshot.os_type in ["windows", "linux"]
    assert snapshot.health_status in list(NetworkHealthStatus)
    assert snapshot.probe is not None
    print(f"\n[Live Snapshot] Health: {snapshot.health_status}, Gateway Ping: {snapshot.probe.gateway_ping_ms}ms, Wi-Fi: {snapshot.wifi_connected}")
