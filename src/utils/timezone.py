"""리포트 표시용 시간대 변환.

측정값 저장은 UTC를 유지하고, 리포트를 만들 때만 실행 환경의 시간대로 바꿉니다.
`WIFI_TIMEZONE`이 있으면 그 IANA 이름(예: Asia/Seoul)을 쓰고, 없으면 OS 시간대를 씁니다.
"""
import os
from datetime import date, datetime, time, timezone, tzinfo
from typing import Optional, Tuple

from zoneinfo import ZoneInfo

from src.models.incident import Incident


def report_timezone() -> tzinfo:
    """리포트에 사용할 시간대."""
    name = os.getenv("WIFI_TIMEZONE")
    if name:
        return ZoneInfo(name)
    local = datetime.now().astimezone().tzinfo
    if local is None:
        return timezone.utc
    return local


def as_utc(dt: datetime) -> datetime:
    """시간대가 없는 값은 SQLite에 저장된 UTC 시각으로 봅니다."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def as_utc_naive(dt: datetime) -> datetime:
    """DB 비교에 맞추기 위해 시간대 정보를 뺀 UTC 시각."""
    return as_utc(dt).replace(tzinfo=None)


def to_local(dt: datetime, tz: Optional[tzinfo] = None) -> datetime:
    """UTC 시각을 리포트 시간대로 변환합니다."""
    return as_utc(dt).astimezone(tz or report_timezone())


def local_day_bounds(target: date, tz: Optional[tzinfo] = None) -> Tuple[datetime, datetime]:
    """로컬 달력의 하루를 UTC naive 조회 구간으로 바꿉니다."""
    zone = tz or report_timezone()
    start_local = datetime.combine(target, time.min, tzinfo=zone)
    end_local = datetime.combine(target, time.max, tzinfo=zone)
    return as_utc_naive(start_local), as_utc_naive(end_local)


def issued_at_label(tz: Optional[tzinfo] = None) -> str:
    """발행일시에 시간대 이름을 붙입니다."""
    zone = tz or report_timezone()
    now = datetime.now(zone)
    label = now.tzname() or getattr(zone, "key", "") or ""
    return f"{now.strftime('%Y-%m-%d %H:%M:%S')} {label}".strip()


def localize_incident(inc: Incident, tz: Optional[tzinfo] = None) -> Incident:
    """표시용으로 발생·종료 시각만 로컬 시간으로 바꾼 사본."""
    return inc.model_copy(
        update={
            "start_time": to_local(inc.start_time, tz),
            "end_time": to_local(inc.end_time, tz) if inc.end_time else None,
        }
    )
