import base64
import io
from typing import Dict, List, Optional
import matplotlib
matplotlib.use("Agg")  # GUI 없는 백엔드 모드
import matplotlib.pyplot as plt
import numpy as np

# 기본 한글 폰트 설정 (Windows: Malgun Gothic, Linux: DejaVu Sans/NanumGothic)
plt.rcParams["font.sans-serif"] = ["Malgun Gothic", "NanumGothic", "DejaVu Sans", "Arial"]
plt.rcParams["axes.unicode_minus"] = False


def fig_to_base64(fig: plt.Figure) -> str:
    """Matplotlib Figure를 base64 PNG 문자열로 인코딩"""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    img_b64 = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return f"data:image/png;base64,{img_b64}"


def generate_latency_trend_chart(timestamps: List[str], gw_pings: List[Optional[float]], inet_pings: List[Optional[float]]) -> str:
    """시간대별 게이트웨이 및 외부 인터넷 핑 RTT 꺾은선 차트"""
    fig, ax = plt.subplots(figsize=(10, 3.5))
    
    x = range(len(timestamps))
    gw_clean = [p if p is not None else np.nan for p in gw_pings]
    inet_clean = [p if p is not None else np.nan for p in inet_pings]

    ax.plot(x, gw_clean, label="게이트웨이(공유기)", color="#2563eb", linewidth=1.8, marker="o", markersize=3)
    ax.plot(x, inet_clean, label="외부 인터넷(8.8.8.8)", color="#10b981", linewidth=1.8, linestyle="--", marker="s", markersize=3)

    # 타임아웃 / 손실 구간 표시 (None인 곳)
    loss_indices = [i for i, p in enumerate(gw_pings) if p is None]
    if loss_indices:
        for idx in loss_indices:
            ax.axvline(x=idx, color="#ef4444", alpha=0.3, linewidth=2, linestyle=":")
        ax.scatter(loss_indices, [0] * len(loss_indices), color="#ef4444", s=50, zorder=5, label="패킷 손실(단절)")

    ax.set_ylabel("응답 시간 (ms)", fontsize=10)
    ax.set_title("네트워크 응답 시간 추이 및 단절 구간", fontsize=12, fontweight="bold", pad=10)
    ax.grid(True, linestyle=":", alpha=0.6)
    ax.legend(loc="upper right", framealpha=0.9)

    # X축 눈금 간소화
    step = max(1, len(timestamps) // 8)
    ax.set_xticks(list(x)[::step])
    ax.set_xticklabels([timestamps[i] for i in list(x)[::step]], rotation=15, ha="right", fontsize=8)

    return fig_to_base64(fig)


def generate_rssi_chart(timestamps: List[str], rssi_values: List[Optional[int]]) -> str:
    """Wi-Fi 신호 세기(RSSI) 추이 차트"""
    fig, ax = plt.subplots(figsize=(10, 2.8))

    x = range(len(timestamps))
    clean_rssi = [r if r is not None else np.nan for r in rssi_values]

    ax.plot(x, clean_rssi, label="신호 세기 (RSSI)", color="#8b5cf6", linewidth=1.8)
    ax.axhline(y=-80, color="#ef4444", linestyle="--", alpha=0.7, label="위험 기준선 (-80 dBm)")
    ax.axhline(y=-65, color="#f59e0b", linestyle=":", alpha=0.7, label="양호 기준선 (-65 dBm)")

    ax.set_ylabel("신호 세기 (dBm)", fontsize=10)
    ax.set_title("Wi-Fi 신호 강도 변동 추이", fontsize=12, fontweight="bold", pad=10)
    ax.grid(True, linestyle=":", alpha=0.6)
    ax.legend(loc="lower left", framealpha=0.9, fontsize=8)

    step = max(1, len(timestamps) // 8)
    ax.set_xticks(list(x)[::step])
    ax.set_xticklabels([timestamps[i] for i in list(x)[::step]], rotation=15, ha="right", fontsize=8)

    return fig_to_base64(fig)


def generate_hourly_heatmap(hourly_distribution: Dict[int, int]) -> str:
    """24시간 시간대별 장애 발생 빈도 히트맵/바 차트"""
    fig, ax = plt.subplots(figsize=(10, 3.0))

    hours = list(range(24))
    counts = [hourly_distribution.get(h, 0) for h in hours]
    colors = ["#ef4444" if c >= 3 else ("#f59e0b" if c > 0 else "#e2e8f0") for c in counts]

    bars = ax.bar(hours, counts, color=colors, edgecolor="#94a3b8", linewidth=0.5, width=0.7)
    
    # 막대 위 숫자 표시
    for bar in bars:
        h = bar.get_height()
        if h > 0:
            ax.annotate(f"{int(h)}",
                        xy=(bar.get_x() + bar.get_width() / 2, h),
                        xytext=(0, 3),
                        textcoords="offset points",
                        ha="center", va="bottom", fontsize=9, fontweight="bold")

    ax.set_xlabel("시간대 (0시 ~ 23시)", fontsize=10)
    ax.set_ylabel("장애 발생 건수", fontsize=10)
    ax.set_title("시간대별 장애 발생 빈도 분포 (주기성 식별)", fontsize=12, fontweight="bold", pad=10)
    ax.set_xticks(hours)
    ax.set_xticklabels([f"{h:02d}시" for h in hours], fontsize=8)
    ax.grid(axis="y", linestyle=":", alpha=0.6)

    return fig_to_base64(fig)
