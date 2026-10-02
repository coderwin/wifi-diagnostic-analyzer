from datetime import date, datetime, timezone, timedelta
from pathlib import Path
import pytest

from src.models.incident import Incident, RootCauseType
from src.models.metrics import (
    ConnectivityProbeResult,
    NetworkHealthStatus,
    WifiBand,
    WifiInterfaceInfo,
    WifiMetricsSnapshot,
)
from src.reporter.charts import (
    generate_hourly_heatmap,
    generate_latency_trend_chart,
    generate_rssi_chart,
)
from src.reporter.pdf_generator import PdfReportGenerator
from src.storage.db import DatabaseStorage


@pytest.fixture
def populated_storage(tmp_path):
    db_file = tmp_path / "report_test.db"
    storage = DatabaseStorage(db_path=str(db_file))
    base_time = datetime(2026, 9, 30, 8, 55, 0, tzinfo=timezone.utc)

    # 1. 10개 시계열 스냅샷 생성
    for i in range(10):
        t = base_time + timedelta(minutes=i * 2)
        is_down = 2 <= i <= 4
        snap = WifiMetricsSnapshot(
            timestamp=t,
            os_type="windows",
            health_status=NetworkHealthStatus.GATEWAY_UNREACHABLE if is_down else NetworkHealthStatus.HEALTHY,
            wifi_connected=True,
            wifi_info=WifiInterfaceInfo(
                ssid="HMS",
                rssi_dbm=-48,
                channel=149,
                band=WifiBand.BAND_5GHZ,
            ),
            probe=ConnectivityProbeResult(
                gateway_ip="192.168.0.1",
                gateway_ping_ms=None if is_down else 2.5,
                internet_ping_ms=None if is_down else 15.0,
                dns_resolved=not is_down,
                http_ok=not is_down,
                wired_connected=True,
            ),
        )
        storage.save_snapshot(snap)

    # 2. 장애 인시던트 생성 (오전 9시 장애)
    inc = Incident(
        id="inc-report-01",
        start_time=base_time + timedelta(minutes=5),  # 09:00:00
        end_time=base_time + timedelta(minutes=9),    # 09:04:00
        duration_seconds=240.0,
        root_cause=RootCauseType.AP_HARDWARE_OR_CRASH,
        confidence_score=0.98,
        summary="09:00:00 공유기 무선 AP 응답 불가 (유선 정상)",
        evidence=["Gateway Ping 무응답", "유선 LAN 연결 정상"],
        recommendations=["공유기 예약 재부팅 시간 점검", "공유기 최신 펌웨어 적용"],
    )
    storage.save_incident(inc)

    return storage


def test_chart_generation():
    timestamps = ["08:50", "08:55", "09:00", "09:05"]
    gw_pings = [2.0, 3.1, None, 2.5]
    inet_pings = [14.0, 15.2, None, 16.0]
    rssi_vals = [-50, -52, -50, -51]
    hourly = {8: 1, 9: 4, 10: 0}

    lat_img = generate_latency_trend_chart(timestamps, gw_pings, inet_pings)
    assert lat_img.startswith("data:image/png;base64,")

    rssi_img = generate_rssi_chart(timestamps, rssi_vals)
    assert rssi_img.startswith("data:image/png;base64,")

    heat_img = generate_hourly_heatmap(hourly)
    assert heat_img.startswith("data:image/png;base64,")


def test_daily_report_generation(populated_storage, tmp_path):
    generator = PdfReportGenerator(db_storage=populated_storage)
    target_date = datetime(2026, 9, 30).date()
    
    out_file = generator.generate_daily_report(target_date=target_date)
    assert out_file.exists()
    assert out_file.stat().st_size > 0
    print(f"\n[Generated Daily Report] {out_file} ({out_file.stat().st_size} bytes)")


def test_daily_report_clock_follows_report_timezone(populated_storage, monkeypatch):
    """DB의 09:00 UTC 장애는 Asia/Seoul 리포트에서 18:00으로 표시됩니다."""
    monkeypatch.setenv("WIFI_TIMEZONE", "Asia/Seoul")
    generator = PdfReportGenerator(db_storage=populated_storage)
    out_file = generator.generate_daily_report(target_date=date(2026, 9, 30))

    html_path = out_file if out_file.suffix == ".html" else out_file.with_suffix(".html")
    html = html_path.read_text(encoding="utf-8")
    assert "18:00:00" in html
    assert "KST" in html


def test_pattern_report_generation(populated_storage, tmp_path):
    generator = PdfReportGenerator(db_storage=populated_storage)
    
    out_file = generator.generate_pattern_report(days=7)
    assert out_file.exists()
    assert out_file.stat().st_size > 0
    print(f"\n[Generated Pattern Report] {out_file} ({out_file.stat().st_size} bytes)")
