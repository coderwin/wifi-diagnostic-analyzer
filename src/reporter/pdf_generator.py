from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from jinja2 import Environment, FileSystemLoader

from src.analyzer.pattern import IncidentPatternAnalyzer
from src.config import settings
from src.reporter.charts import (
    generate_hourly_heatmap,
    generate_latency_trend_chart,
    generate_rssi_chart,
)
from src.storage.db import DatabaseStorage
from src.utils.logger import logger
from src.utils.timezone import (
    as_utc_naive,
    issued_at_label,
    local_day_bounds,
    localize_incident,
    report_timezone,
    to_local,
)

try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except Exception as e:
    WEASYPRINT_AVAILABLE = False
    logger.warning(f"WeasyPrint 로드 실패 (HTML 모드로 대체): {e}")


class PdfReportGenerator:
    """Jinja2 템플릿과 차트를 결합하여 PDF 및 HTML 리포트를 발행하는 생성기"""

    def __init__(self, db_storage: Optional[DatabaseStorage] = None):
        self.storage = db_storage or DatabaseStorage()
        settings.ensure_directories()
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(settings.TEMPLATES_DIR)),
            autoescape=True,
        )

    def _render_to_file(self, html_content: str, output_pdf_path: Path) -> Path:
        """HTML을 PDF로 변환하여 저장 (WeasyPrint 미지원 시 .html 백업)"""
        output_pdf_path.parent.mkdir(parents=True, exist_ok=True)
        html_backup_path = output_pdf_path.with_suffix(".html")
        
        # HTML 파일 저장 (브라우저 열람용 백업)
        with open(html_backup_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        if WEASYPRINT_AVAILABLE:
            try:
                HTML(string=html_content).write_pdf(str(output_pdf_path))
                logger.info(f"📄 PDF 리포트 생성 완료: {output_pdf_path}")
                return output_pdf_path
            except Exception as e:
                logger.error(f"WeasyPrint PDF 렌더링 실패: {e}")
                logger.info(f"📄 대체 HTML 리포트 생성: {html_backup_path}")
                return html_backup_path
        else:
            logger.info(f"📄 HTML 리포트 생성 완료: {html_backup_path}")
            return html_backup_path

    def generate_daily_report(self, target_date: Optional[datetime.date] = None) -> Path:
        """일별 장애 및 네트워크 상태 요약 리포트 생성"""
        tz = report_timezone()
        if not target_date:
            target_date = datetime.now(tz).date()

        start_dt, end_dt = local_day_bounds(target_date, tz)

        incidents = self.storage.get_incidents(start_time=start_dt, end_time=end_dt)
        snapshots = self.storage.get_snapshots(start_time=start_dt, end_time=end_dt, limit=1000)
        local_incidents = [localize_incident(inc, tz) for inc in incidents]

        # 차트 생성 데이터 추출 (가로축은 리포트 시간대)
        timestamps = [to_local(s.timestamp, tz).strftime("%H:%M") for s in snapshots]
        gw_pings = [s.gateway_ping_ms for s in snapshots]
        inet_pings = [s.internet_ping_ms for s in snapshots]
        rssi_vals = [s.rssi_dbm for s in snapshots]

        latency_chart = generate_latency_trend_chart(timestamps, gw_pings, inet_pings) if timestamps else None
        rssi_chart = generate_rssi_chart(timestamps, rssi_vals) if timestamps else None

        # 가동률 및 통계 계산
        total_snaps = len(snapshots)
        down_snaps = sum(1 for s in snapshots if not s.wifi_connected or s.gateway_ping_ms is None)
        uptime_pct = round(((total_snaps - down_snaps) / total_snaps * 100), 2) if total_snaps > 0 else 100.0
        total_downtime_sec = sum(inc.duration_seconds or 0 for inc in local_incidents)

        primary_issue = local_incidents[0].root_cause.value if local_incidents else "정상 유지"

        all_recommendations = []
        for inc in local_incidents:
            for rec in inc.recommendations:
                if rec not in all_recommendations:
                    all_recommendations.append(rec)

        template = self.jinja_env.get_template("daily_report.html")
        html_out = template.render(
            report_date=issued_at_label(tz),
            os_type="Windows & Linux",
            uptime_pct=uptime_pct,
            total_incidents=len(local_incidents),
            total_downtime_str=f"{int(total_downtime_sec)}초" if total_downtime_sec < 60 else f"{int(total_downtime_sec // 60)}분 {int(total_downtime_sec % 60)}초",
            primary_issue=primary_issue,
            incidents=local_incidents,
            recommendations=all_recommendations,
            latency_chart=latency_chart,
            rssi_chart=rssi_chart,
        )

        out_path = settings.REPORTS_DIR / f"daily_report_{target_date.strftime('%Y%m%d')}.pdf"
        return self._render_to_file(html_out, out_path)

    def generate_pattern_report(self, days: int = 7) -> Path:
        """기간별(7일/30일) 반복 패턴 심층 분석 리포트 생성"""
        tz = report_timezone()
        now_local = datetime.now(tz)
        start_local = now_local - timedelta(days=days)

        incidents = self.storage.get_incidents(
            start_time=as_utc_naive(start_local),
            end_time=as_utc_naive(now_local),
            limit=500,
        )
        local_incidents = [localize_incident(inc, tz) for inc in incidents]
        pattern_insight = IncidentPatternAnalyzer.analyze_patterns(local_incidents, window_minutes=15)

        heatmap_chart = generate_hourly_heatmap(pattern_insight.hourly_distribution)

        template = self.jinja_env.get_template("pattern_report.html")
        html_out = template.render(
            period_str=f"{start_local.strftime('%Y-%m-%d')} ~ {now_local.strftime('%Y-%m-%d')}",
            total_days=days,
            report_date=issued_at_label(tz),
            pattern_insight=pattern_insight,
            pattern_incidents=local_incidents[:20],
            heatmap_chart=heatmap_chart,
        )

        out_path = settings.REPORTS_DIR / f"pattern_analysis_{days}days_{now_local.strftime('%Y%m%d')}.pdf"
        return self._render_to_file(html_out, out_path)
