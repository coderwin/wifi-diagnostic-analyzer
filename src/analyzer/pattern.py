from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Tuple

from src.models.incident import Incident, RootCauseType


@dataclass
class RecurringPatternInsight:
    """반복 장애 패턴 분석 결과"""
    has_recurring_pattern: bool = False
    target_hour: Optional[int] = None           # 예: 9 (오전 9시)
    time_window_str: str = ""                   # 예: "08:50 ~ 09:15"
    incident_count_in_window: int = 0
    total_days_analyzed: int = 0
    days_with_incident: int = 0                 # 예: 5일 중 4일
    frequency_rate: float = 0.0                 # 예: 0.8 (80%)
    primary_cause: RootCauseType = RootCauseType.UNKNOWN
    pattern_summary: str = ""
    recommendation: str = ""
    hourly_distribution: Dict[int, int] = field(default_factory=dict)


class IncidentPatternAnalyzer:
    """장애 발생 주기성 및 특정 시간대(예: 매일 09:00) 반복 패턴 분석기"""

    @classmethod
    def analyze_patterns(
        cls,
        incidents: List[Incident],
        window_minutes: int = 15,
        min_occurrences: int = 3,
        threshold_ratio: float = 0.6,
    ) -> RecurringPatternInsight:
        """
        장애 목록을 분석하여 특정 시간대 집중 반복 패턴을 식별합니다.

        :param incidents: 분석할 Incident 리스트
        :param window_minutes: 중심 시간 기준 전후 윈도우 (분)
        :param min_occurrences: 패턴으로 인정할 최소 발생 횟수
        :param threshold_ratio: 해당 시간대 발생일수 / 전체 분석일수 비율 기준
        """
        if not incidents or len(incidents) < min_occurrences:
            return RecurringPatternInsight(
                pattern_summary="분석에 필요한 충분한 장애 이력이 없습니다 (최소 3건 필요)."
            )

        # 1. 24시간 시간대별 발생 카운트
        hourly_dist: Dict[int, int] = defaultdict(int)
        for h in range(24):
            hourly_dist[h] = 0

        # 분 단위 타임슬롯 (하루 1440분)
        minute_incidents: Dict[int, List[Incident]] = defaultdict(list)
        dates_with_incidents = set()

        all_dates = set()
        for inc in incidents:
            dt = inc.start_time
            all_dates.add(dt.date())
            hour = dt.hour
            minute = dt.minute
            hourly_dist[hour] += 1
            minute_of_day = hour * 60 + minute
            minute_incidents[minute_of_day].append(inc)

        # 전체 분석 기간(일수)
        if all_dates:
            min_date = min(all_dates)
            max_date = max(all_dates)
            total_days = max(1, (max_date - min_date).days + 1)
        else:
            total_days = 1

        # 2. 이동 윈도우(Sliding Window)로 하루 중 가장 장애가 집중된 시간대 탐색
        best_center_minute = None
        max_window_incidents: List[Incident] = []
        max_window_count = 0
        min_dispersion = float("inf")

        # 1분 단위로 슬라이딩 윈도우 검사 (00:00 ~ 23:59)
        for m_center in range(0, 1440):
            window_incs = []
            dispersion = 0.0
            for m_offset in range(-window_minutes, window_minutes + 1):
                target_m = (m_center + m_offset) % 1440
                incs = minute_incidents.get(target_m, [])
                window_incs.extend(incs)
                dispersion += len(incs) * abs(m_offset)

            count = len(window_incs)
            if count > max_window_count or (count == max_window_count and dispersion < min_dispersion):
                max_window_count = count
                max_window_incidents = window_incs
                best_center_minute = m_center
                min_dispersion = dispersion

        if max_window_count < min_occurrences or best_center_minute is None:
            return RecurringPatternInsight(
                has_recurring_pattern=False,
                hourly_distribution=dict(hourly_dist),
                total_days_analyzed=total_days,
                pattern_summary="특정 시간대에 집중되는 반복 패턴이 감지되지 않았습니다.",
            )

        # 3. 윈도우 내 고유 발생 일자 계산
        window_dates = {inc.start_time.date() for inc in max_window_incidents}
        days_with_inc = len(window_dates)
        freq_rate = days_with_inc / total_days

        # 윈도우 내 실제 인시던트들의 가중 평균 시각 계산
        total_minutes_sum = sum(
            inc.start_time.hour * 60 + inc.start_time.minute
            for inc in max_window_incidents
        )
        avg_minute = round(total_minutes_sum / len(max_window_incidents))
        # 만약 08:50 ~ 09:10 사이에 걸쳐 있고 avg_minute이 535(08:55) 이상이면 반올림하여 목표 시각 산출
        target_hour = round(avg_minute / 60) % 24
        center_h = (avg_minute // 60) % 24
        center_m = avg_minute % 60
        start_m = (best_center_minute - window_minutes) % 1440
        end_m = (best_center_minute + window_minutes) % 1440
        window_str = f"{start_m // 60:02d}:{start_m % 60:02d} ~ {end_m // 60:02d}:{end_m % 60:02d}"

        # 주된 원인 집계
        cause_counts: Dict[RootCauseType, int] = defaultdict(int)
        for inc in max_window_incidents:
            cause_counts[inc.root_cause] += 1
        primary_cause = max(cause_counts.items(), key=lambda x: x[1])[0]

        has_pattern = (max_window_count >= min_occurrences) and (freq_rate >= threshold_ratio or days_with_inc >= 3)

        summary_msg = (
            f"최근 {total_days}일 중 {days_with_inc}일간 {window_str} (중심: {center_h:02d}:{center_m:02d}경) "
            f"특정 시간대에 장애가 집중 반복 발생함 (발생률 {freq_rate * 100:.0f}%)."
        )

        rec_msg = (
            f"매일 {target_hour:02d}시 전후로 일정한 시간에 장애가 발생하는 패턴입니다. "
            f"공유기(AP)의 '매일 {target_hour:02d}시 자동 재부팅', '무선 절전/Wi-Fi On/Off 스케줄러', "
            f"또는 주변 고출력 전자기기 가동 시간대를 확인하세요."
        )

        return RecurringPatternInsight(
            has_recurring_pattern=has_pattern,
            target_hour=target_hour,
            time_window_str=window_str,
            incident_count_in_window=max_window_count,
            total_days_analyzed=total_days,
            days_with_incident=days_with_inc,
            frequency_rate=round(freq_rate, 2),
            primary_cause=primary_cause,
            pattern_summary=summary_msg,
            recommendation=rec_msg,
            hourly_distribution=dict(hourly_dist),
        )
