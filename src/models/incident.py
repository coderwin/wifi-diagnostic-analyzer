from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

from .metrics import WifiMetricsSnapshot


class RootCauseType(str, Enum):
    AP_HARDWARE_OR_CRASH = "AP_HARDWARE_OR_CRASH"       # 공유기 무선 AP 모듈 장애 / 크래시
    ISP_WAN_DOWN = "ISP_WAN_DOWN"                       # 외부 인터넷 회선(WAN/모뎀) 장애
    SIGNAL_WEAK = "SIGNAL_WEAK"                         # 신호 세기 급감 / 거리 및 차폐 문제
    CHANNEL_INTERFERENCE = "CHANNEL_INTERFERENCE"       # 동일/인접 채널 간섭 및 혼잡
    DFS_CHANNEL_HOP = "DFS_CHANNEL_HOP"                 # 레이더 감지 등으로 인한 채널 급변(DFS)
    DHCP_FAILURE = "DHCP_FAILURE"                       # IP 할당 실패 / 임대 만료
    DNS_FAILURE = "DNS_FAILURE"                         # DNS 서버 응답 불가
    ADAPTER_ISSUE = "ADAPTER_ISSUE"                     # 클라이언트 무선 LAN 카드/드라이버 절전 오류
    SCHEDULED_REBOOT = "SCHEDULED_REBOOT"               # 공유기 예약 재부팅 / 스케줄 재시작
    UNKNOWN = "UNKNOWN"                                 # 원인 불명


class Incident(BaseModel):
    """감지된 장애 이벤트 및 분석 결과 모델"""
    id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    root_cause: RootCauseType = RootCauseType.UNKNOWN
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0) # 0.0 ~ 1.0 (신뢰도)
    summary: str = ""
    evidence: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    pattern_note: Optional[str] = None
    trigger_snapshot: Optional[WifiMetricsSnapshot] = None
    recovery_snapshot: Optional[WifiMetricsSnapshot] = None
    snapshot_count: int = 1
