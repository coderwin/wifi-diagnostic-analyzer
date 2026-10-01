import asyncio
import re
import socket
import subprocess
import sys
import time
from typing import Optional, Tuple
import dns.resolver
import ping3
import psutil
import requests

from src.config import settings
from src.models.metrics import ConnectivityProbeResult
from src.utils.logger import logger


def _system_ping(host: str, timeout_sec: float) -> Optional[float]:
    """OS 기본 ping 명령어를 사용한 fallback 핑 측정 (밀리초 반환, 실패 시 None)"""
    try:
        if sys.platform.startswith("win"):
            timeout_ms = int(timeout_sec * 1000)
            cmd = ["ping", "-n", "1", "-w", str(timeout_ms), host]
        else:
            cmd = ["ping", "-c", "1", "-W", str(max(1, int(timeout_sec))), host]
            
        t0 = time.perf_counter()
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout_sec + 1.0)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        
        if proc.returncode == 0:
            # 출력에서 RTT 파싱 시도 (실패 시 proc 시간 사용)
            m = re.search(r'(?:time|시간)[=<]?\s*([0-9.]+)\s*ms', proc.stdout, re.IGNORECASE)
            if m:
                return float(m.group(1))
            return round(elapsed_ms, 2)
        return None
    except Exception:
        return None


def ping_host(host: Optional[str], timeout_sec: float = None) -> Optional[float]:
    """ICMP 핑을 수행하고 RTT(ms)를 반환. 실패/타임아웃 시 None 반환"""
    if not host:
        return None
        
    timeout = timeout_sec or settings.PING_TIMEOUT_SEC
    try:
        rtt_sec = ping3.ping(host, timeout=timeout)
        if rtt_sec is None or rtt_sec is False:
            # Fallback to system ping
            return _system_ping(host, timeout)
        return round(rtt_sec * 1000.0, 2)
    except Exception:
        return _system_ping(host, timeout)


def check_dns(host: str = None, timeout_sec: float = None) -> Tuple[bool, Optional[float]]:
    """도메인 이름 풀이(DNS) 테스트"""
    target = host or settings.DNS_TEST_HOST
    timeout = timeout_sec or settings.DNS_TIMEOUT_SEC
    resolver = dns.resolver.Resolver()
    resolver.lifetime = timeout
    resolver.timeout = timeout
    
    t0 = time.perf_counter()
    try:
        answers = resolver.resolve(target, "A")
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return (len(answers) > 0, latency_ms)
    except Exception:
        return (False, None)


def check_http(url: str = None, timeout_sec: float = None) -> Tuple[bool, Optional[float]]:
    """L7 HTTP/HTTPS 연결성 테스트"""
    target = url or settings.HTTP_TEST_URL
    timeout = timeout_sec or settings.HTTP_TIMEOUT_SEC
    
    t0 = time.perf_counter()
    try:
        resp = requests.get(target, timeout=timeout)
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        # 200 OK 또는 204 No Content
        return (resp.status_code in [200, 204], latency_ms)
    except Exception:
        return (False, None)


def check_wired_status() -> Tuple[bool, Optional[float]]:
    """유선 이더넷 어댑터 활성화 여부 및 유선 게이트웨이 핑 체크"""
    try:
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()
        
        wired_active = False
        for iface_name, stat in stats.items():
            name_lower = iface_name.lower()
            # 무선, 가상망, 루프백 제외하고 유선 이더넷 식별
            if any(skip in name_lower for skip in ["wi-fi", "wlan", "wireless", "loopback", "virtual", "tap", "vpn", "vEthernet"]):
                continue
            if "이더넷" in iface_name or "eth" in name_lower or "enp" in name_lower or "ethernet" in name_lower:
                if stat.isup:
                    # 유효한 IPv4 주소가 있는지 확인
                    if iface_name in addrs:
                        for addr in addrs[iface_name]:
                            if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                                wired_active = True
                                break
            if wired_active:
                break
        return (wired_active, None)
    except Exception as e:
        logger.debug(f"유선 상태 감지 중 오류: {e}")
        return (False, None)


class ConnectivityProbe:
    """다계층 비동기 네트워크 프로브"""
    
    @staticmethod
    async def probe(gateway_ip: Optional[str] = None) -> ConnectivityProbeResult:
        loop = asyncio.get_running_loop()
        
        # 4개 프로브를 비동기 병렬 실행
        gw_ping_task = loop.run_in_executor(None, ping_host, gateway_ip)
        inet_ping_task = loop.run_in_executor(None, ping_host, settings.INTERNET_PING_HOST)
        dns_task = loop.run_in_executor(None, check_dns, settings.DNS_TEST_HOST)
        http_task = loop.run_in_executor(None, check_http, settings.HTTP_TEST_URL)
        wired_task = loop.run_in_executor(None, check_wired_status)
        
        gw_ping, inet_ping, (dns_ok, dns_lat), (http_ok, http_lat), (wired_conn, _) = await asyncio.gather(
            gw_ping_task,
            inet_ping_task,
            dns_task,
            http_task,
            wired_task,
            return_exceptions=True
        )
        
        # 예외 처리 방어 코드
        gw_ping_val = gw_ping if isinstance(gw_ping, (float, int)) else None
        inet_ping_val = inet_ping if isinstance(inet_ping, (float, int)) else None
        dns_ok_val = dns_ok if isinstance(dns_ok, bool) else False
        dns_lat_val = dns_lat if isinstance(dns_lat, (float, int)) else None
        http_ok_val = http_ok if isinstance(http_ok, bool) else False
        http_lat_val = http_lat if isinstance(http_lat, (float, int)) else None
        wired_conn_val = wired_conn if isinstance(wired_conn, bool) else False
        
        return ConnectivityProbeResult(
            gateway_ip=gateway_ip,
            gateway_ping_ms=gw_ping_val,
            internet_ping_ms=inet_ping_val,
            dns_resolved=dns_ok_val,
            dns_latency_ms=dns_lat_val,
            http_ok=http_ok_val,
            http_latency_ms=http_lat_val,
            wired_connected=wired_conn_val,
        )
