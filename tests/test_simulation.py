from datetime import datetime, timezone, timedelta
import pytest

from src.analyzer.pattern import IncidentPatternAnalyzer
from src.models.incident import RootCauseType
from src.reporter.pdf_generator import PdfReportGenerator
from src.simulator import generate_simulated_dataset
from src.storage.db import DatabaseStorage


@pytest.fixture
def sim_db(tmp_path):
    db_file = tmp_path / "sim_test.db"
    return DatabaseStorage(db_path=str(db_file))


def test_simulation_data_injection(sim_db):
    """5일 중 4일 09:00 장애 데이터 주입 검증"""
    start_d = datetime(2026, 9, 26, 0, 0, 0, tzinfo=timezone.utc)
    incidents = generate_simulated_dataset(
        storage=sim_db,
        days=5,
        crash_days_count=4,
        start_date=start_d,
    )

    assert len(incidents) == 4
    db_incidents = sim_db.get_incidents(limit=20)
    assert len(db_incidents) == 4
    for inc in db_incidents:
        assert inc.root_cause == RootCauseType.AP_HARDWARE_OR_CRASH
        assert inc.confidence_score >= 0.95
        assert "유선 정상" in inc.summary

    snapshots = sim_db.get_snapshots(limit=500)
    assert len(snapshots) >= 100


def test_simulation_pattern_detection_and_reporting(sim_db, tmp_path):
    """시뮬레이션 데이터로부터 09:00 패턴 자동 검출 및 리포트 파일 생성 통합 검증"""
    start_d = datetime.now(timezone.utc) - timedelta(days=4)
    generate_simulated_dataset(
        storage=sim_db,
        days=5,
        crash_days_count=4,
        start_date=start_d,
    )

    incidents = sim_db.get_incidents(limit=100)
    insight = IncidentPatternAnalyzer.analyze_patterns(incidents, window_minutes=15)

    assert insight.has_recurring_pattern is True
    assert insight.target_hour == 9
    assert insight.days_with_incident == 4
    assert insight.primary_cause == RootCauseType.AP_HARDWARE_OR_CRASH
    assert "09:00" in insight.pattern_summary or "09:" in insight.pattern_summary
    assert "자동 재부팅" in insight.recommendation

    generator = PdfReportGenerator(db_storage=sim_db)
    pattern_report_path = generator.generate_pattern_report(days=7)
    assert pattern_report_path.exists()
    assert pattern_report_path.stat().st_size > 0
    print(f"\n[Verified Pattern Report] {pattern_report_path} ({pattern_report_path.stat().st_size} bytes)")
