"""Wi-Fi Sentinel: 지능형 Wi-Fi 장애 진단 & 패턴 분석 자동화 시스템 CLI"""
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
from typing import Optional

# 루트 디렉터리를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from src.analyzer.detector import IncidentDetector
from src.analyzer.engine import MonitoringEngine
from src.analyzer.pattern import IncidentPatternAnalyzer
from src.analyzer.rules import RuleMatrixEngine
from src.collectors.factory import get_collector
from src.config import settings
from src.models.metrics import NetworkHealthStatus
from src.reporter.pdf_generator import PdfReportGenerator
from src.storage.db import DatabaseStorage
from src.utils.logger import logger

app = typer.Typer(
    name="wifi-sentinel",
    help="Wi-Fi 장애 원인과 매일 반복되는 패턴(예: 09:00 AP 크래시)을 자동 진단/리포팅하는 도구",
    add_completion=False,
)

# Windows 콘솔 인코딩 대응 (UTF-8 호환)
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

console = Console(highlight=False)


@app.command()
def diagnose():
    """현재 네트워크 상태와 Wi-Fi 지표를 즉시 1회 정밀 진단합니다."""
    settings.ensure_directories()
    collector = get_collector()
    storage = DatabaseStorage()

    with console.status("[bold green]현재 Wi-Fi 및 다계층 네트워크 진단 중...", spinner="dots"):
        snapshot = asyncio.run(collector.collect_snapshot())
        eval_res = RuleMatrixEngine.evaluate(snapshot)
        storage.save_snapshot(snapshot)

    # 1. 진단 요약 패널
    status_color = "green" if snapshot.health_status == NetworkHealthStatus.HEALTHY else "red"
    console.print(
        Panel.fit(
            f"[bold {status_color}]상태: {snapshot.health_status.value}[/bold {status_color}]\n"
            f"[bold]진단 결과:[/bold] {eval_res.summary}\n"
            f"[bold]추정 원인:[/bold] {eval_res.root_cause.value} (신뢰도 {eval_res.confidence_score * 100:.0f}%)",
            title="[진단 결과]",
            border_style=status_color,
        )
    )

    # 2. 메트릭 상세 테이블
    table = Table(title="네트워크 및 Wi-Fi 세부 지표", show_header=True, header_style="bold cyan")
    table.add_column("항목", style="dim", width=22)
    table.add_column("측정값", width=38)

    wifi = snapshot.wifi_info
    probe = snapshot.probe

    table.add_row("운영체제", snapshot.os_type)
    table.add_row("Wi-Fi 연결 여부", "[green]연결됨[/green]" if snapshot.wifi_connected else "[red]연결 안 됨[/red]")
    if wifi:
        table.add_row("SSID / BSSID", f"{wifi.ssid} ({wifi.bssid})")
        table.add_row("주파수 대역 / 채널", f"{wifi.band.value} (채널 {wifi.channel})")
        rssi_str = f"{wifi.rssi_dbm} dBm ({wifi.signal_percent}%)" if wifi.rssi_dbm else f"{wifi.signal_percent}%"
        table.add_row("신호 세기 (RSSI)", rssi_str)
        table.add_row("무선 규격", wifi.radio_type or "-")
        table.add_row("링크 속도 (Tx/Rx)", f"{wifi.tx_rate_mbps or '-'} / {wifi.rx_rate_mbps or '-'} Mbps")

    table.add_row("기본 게이트웨이(공유기)", f"{probe.gateway_ip or '-'} (Ping: {f'{probe.gateway_ping_ms} ms' if probe.gateway_ping_ms else '[red]타임아웃[/red]'})")
    table.add_row("외부 인터넷(8.8.8.8)", f"Ping: {f'{probe.internet_ping_ms} ms' if probe.internet_ping_ms else '[red]타임아웃[/red]'}")
    table.add_row("DNS 질의", f"[green]성공[/green] ({probe.dns_latency_ms} ms)" if probe.dns_resolved else "[red]실패[/red]")
    table.add_row("HTTP 웹 연결", f"[green]정상[/green] ({probe.http_latency_ms} ms)" if probe.http_ok else "[red]실패[/red]")
    table.add_row("유선(LAN) 동시 연결", "[green]연결됨[/green]" if probe.wired_connected else "미연결")
    table.add_row("주변 감지된 AP 개수", f"{len(snapshot.nearby_networks)}개")

    console.print(table)

    # 3. 조치 권고안 출력
    if eval_res.recommendations:
        rec_panel = Panel.fit(
            "\n".join([f"- {rec}" for rec in eval_res.recommendations]),
            title="[권장 조치 가이드]",
            border_style="yellow",
        )
        console.print(rec_panel)


@app.command()
def monitor(
    normal_interval: float = typer.Option(5.0, "--interval", "-i", help="평상시 폴링 주기 (초)"),
    high_res_interval: float = typer.Option(1.0, "--high-res", help="장애 시 고해상도 폴링 주기 (초)"),
):
    """실시간 적응형 모니터링 데몬을 백그라운드로 실행합니다 (Ctrl+C로 종료)."""
    settings.ensure_directories()
    settings.NORMAL_POLL_INTERVAL_SEC = normal_interval
    settings.HIGH_RES_POLL_INTERVAL_SEC = high_res_interval

    storage = DatabaseStorage()
    collector = get_collector()

    def on_snapshot(snap):
        storage.save_snapshot(snap)

    def on_incident_start(inc):
        storage.save_incident(inc)
        console.print(f"[bold red]! [장애 감지][/bold red] {inc.summary} (원인: {inc.root_cause.value})")

    def on_incident_resolved(inc):
        storage.save_incident(inc)
        console.print(f"[bold green]OK [장애 복구][/bold green] ID: {inc.id} | 지속 시간: {inc.duration_seconds}초")

    engine = MonitoringEngine(
        collector=collector,
        on_snapshot=on_snapshot,
        on_incident_start=on_incident_start,
        on_incident_resolved=on_incident_resolved,
    )

    console.print(Panel.fit(
        f"[bold cyan]Wi-Fi Sentinel 상시 모니터링 시작[/bold cyan]\n"
        f"- 감시 대상: {collector.get_os_type().upper()} 무선 인터페이스\n"
        f"- 평상시 주기: {normal_interval}초\n"
        f"- 장애 시 고해상도 주기: {high_res_interval}초\n"
        f"- DB 경로: {settings.DB_PATH}\n\n"
        f"종료하려면 [bold yellow]Ctrl + C[/bold yellow]를 누르세요.",
        title="[모니터링 데몬]",
        border_style="blue",
    ))

    try:
        asyncio.run(engine._loop())
    except KeyboardInterrupt:
        console.print("\n[yellow]모니터링을 정상적으로 중지했습니다.[/yellow]")


@app.command()
def report(
    daily: bool = typer.Option(False, "--daily", "-d", help="일별 진단 요약 리포트 생성"),
    pattern: bool = typer.Option(False, "--pattern", "-p", help="주기성 및 반복 패턴 분석 리포트 생성"),
    date: Optional[str] = typer.Option(None, "--date", help="일별 리포트 대상 날짜 (YYYY-MM-DD, 기본값: 오늘)"),
    days: int = typer.Option(7, "--days", help="패턴 분석 기간 (일수, 기본값: 7)"),
):
    """일별 진단 리포트 또는 기간별 반복 패턴 분석 리포트를 PDF/HTML로 생성합니다."""
    settings.ensure_directories()
    storage = DatabaseStorage()
    generator = PdfReportGenerator(db_storage=storage)

    if not daily and not pattern:
        # 둘 다 지정 안 한 경우 둘 다 생성
        daily = True
        pattern = True

    if daily:
        target_d = datetime.strptime(date, "%Y-%m-%d").date() if date else datetime.now().date()
        with console.status(f"[bold green]{target_d} 일별 리포트 생성 중..."):
            out_file = generator.generate_daily_report(target_date=target_d)
        console.print(f"[bold green]OK 일별 리포트 생성 완료:[/bold green] [underline]{out_file}[/underline]")

    if pattern:
        with console.status(f"[bold green]최근 {days}일간 주기성/반복 패턴 분석 리포트 생성 중..."):
            out_file = generator.generate_pattern_report(days=days)
        console.print(f"[bold green]OK 패턴 분석 리포트 생성 완료:[/bold green] [underline]{out_file}[/underline]")


@app.command()
def status():
    """최근 발생한 장애 이력과 통계를 확인합니다."""
    storage = DatabaseStorage()
    now = datetime.now(timezone.utc)
    incidents = storage.get_incidents(limit=10)

    table = Table(title="최근 감지된 Wi-Fi 장애 이력 (최근 10건)", show_header=True, header_style="bold red")
    table.add_column("시작 시각", width=19)
    table.add_column("지속 시간", width=10)
    table.add_column("추정 원인", width=24)
    table.add_column("신뢰도", width=8)
    table.add_column("요약", width=35)

    if not incidents:
        console.print("[green]감지된 장애 이력이 없습니다. 네트워크가 정상 상태입니다.[/green]")
        return

    for inc in incidents:
        table.add_row(
            inc.start_time.strftime("%Y-%m-%d %H:%M:%S"),
            f"{inc.duration_seconds or 0}초",
            inc.root_cause.value,
            f"{inc.confidence_score * 100:.0f}%",
            inc.summary,
        )

    console.print(table)


if __name__ == "__main__":
    app()
