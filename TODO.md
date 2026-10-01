# 📋 Wi-Fi Diagnostic Analyzer 작업 체크리스트 (TODO)

> **프로젝트 목표:** Windows 및 Linux 공용으로 Wi-Fi 장애 원인과 매일 반복되는 패턴(예: 오전 9시경)을 자동 분석하고, PDF 리포트를 생성하는 진단 프로그램 구축

---

## ⚙️ 작업 진행 규칙 (Rules)
- [ ] **Rule 0:** 작업 전, GitHub에 이슈를 발행한다.
- [ ] **Rule 1:** 새로운 작업을 할 때마다 브랜치를 생성한다. (`feature/#이슈번호-기능명`)
- [ ] **Rule 2:** 작업이 완료되면 commit 후 PR을 생성한다.
- [ ] **Rule 3:** PR을 merge 하기 전, 사용자 승인을 받는다.
- [ ] **Rule 4:** PR을 merge하면 관련 issue를 닫는다.

---

## 📌 Phase 1. 프로젝트 기반 및 환경 구성
- [x] 프로젝트 디렉터리 아키텍처 수립 (`src/`, `templates/`, `tests/`, `reports/`)
- [x] 의존성 명세서 작성 (`requirements.txt` / `pyproject.toml`)
  - [x] Core: `psutil`, `ping3`, `dnspython`, `requests`, `pydantic`
  - [x] Schedule & CLI: `apscheduler`, `typer`, `rich`
  - [x] Storage: `sqlalchemy`, `aiosqlite`
  - [x] Report & Chart: `jinja2`, `weasyprint`, `matplotlib`, `seaborn`
- [x] 공통 데이터 모델 및 타입 정의 (`src/models/metrics.py`, `src/models/incident.py`)
- [x] 로깅 및 환경 설정 모듈 구현 (`src/config.py`, `src/utils/logger.py`)

---

## 📌 Phase 2. 크로스 플랫폼 Wi-Fi & 네트워크 수집기 (Collector)
- [x] OS 추상화 수집기 베이스 인터페이스 구현 (`BaseCollector`)
- [x] **Windows 수집기 구현 (`WindowsCollector`)**
  - [x] `netsh wlan show interfaces` 파싱 (SSID, BSSID, RSSI, 채널, 대역, 링크 속도)
  - [x] `netsh wlan show networks mode=bssid` 파싱 (주변 AP 및 채널 혼잡도)
  - [x] 기본 게이트웨이 및 DNS 주소 조회 (`ipconfig` / `psutil`)
  - [x] 유선 이더넷(LAN) 어댑터 상태 조회
- [x] **Linux 수집기 구현 (`LinuxCollector`)**
  - [x] `nmcli` 또는 `iw`/`wpa_supplicant` 기반 Wi-Fi 상태 파싱
  - [x] 주변 Wi-Fi 스캔 및 채널 혼잡도 수집
  - [x] 라우팅 테이블 파싱 (`ip route` 기반 게이트웨이 조회)
  - [x] 유선 네트워크 인터페이스 상태 확인
- [x] 네트워크 핑 & 연결성 프로브 구현 (`src/collectors/probe.py`)
  - [x] 기본 게이트웨이(공유기 IP) Ping RTT 및 패킷 손실률 측정
  - [x] 외부 인터넷(8.8.8.8, 1.1.1.1) Ping 측정
  - [x] DNS 질의 응답 테스트
  - [x] L7 HTTPS 웹 연결 테스트 (캡티브 포털 및 실제 웹 통신 검증)

---

## 📌 Phase 3. 장애 감지 및 원인 추론 엔진 (Diagnostic & Rule Engine)
- [x] 동적 모니터링 루프 구현 (평상시 경량 폴링 5~10초 ↔ 장애 시 1초 고해상도 폴링)
- [x] 장애 판별 조건 정의 (Wi-Fi 연결 해제, 게이트웨이 무응답, 패킷로스 임계치 초과 등)
- [x] **원인 분류 룰 매트릭스 엔진 구현 (`src/analyzer/rules.py`)**
  - [x] `공유기/AP 무선 기능 장애`: 유선 정상 + Wi-Fi RSSI 정상 + 게이트웨이 무응답
  - [x] `인터넷 회선(WAN) 장애`: 유선/무선 모두 게이트웨이 정상 + 외부 인터넷 불가
  - [x] `Wi-Fi 신호 감쇄`: RSSI -80dBm 이하 급감
  - [x] `채널 간섭/혼잡`: 주변 동일 채널 신호 중첩 및 간섭
  - [x] `AP 채널 자동 변경(DFS)`: BSSID는 같으나 채널 급변
  - [x] `DHCP / DNS 장애`: IP 할당 실패 또는 DNS 타임아웃
  - [x] `네트워크 어댑터 장애`: 클라이언트 측 어댑터 비정상 오프라인
- [x] 장애 1건에 대한 사건(Incident) 요약 및 권장 조치 가이드 생성기

---

## 📌 Phase 4. 데이터 저장소 및 시계열 패턴 분석 (Storage & Pattern Detection)
- [x] SQLite 데이터베이스 스키마 및 마이그레이션 (`src/storage/db.py`)
  - [x] 시계열 메트릭 테이블 (`metrics_log`)
  - [x] 장애 이벤트 및 분석 결과 테이블 (`incidents`)
- [x] 오래된 메트릭 자동 정리(Retention) 정책 적용
- [x] **반복 패턴 탐지 알고리즘 구현 (`src/analyzer/pattern.py`)**
  - [x] 일별/시간대별 장애 발생 빈도 군집화 (Clustering)
  - [x] "매일 특정 시간대(예: 오전 9시경) 반복 발생" 신뢰도/주기성 점수 산출
  - [x] 연속 N일 중 M일 발생 여부 판별 로직

---

## 📌 Phase 5. 차트 시각화 및 PDF 리포트 생성기 (Reporting & PDF)
- [ ] **데이터 시각화 모듈 (`src/reporter/charts.py`)**
  - [ ] 시간대별 Ping 지연시간 & 패킷 손실률 꺾은선 차트
  - [ ] Wi-Fi 신호 세기(RSSI) 변동 추이 차트
  - [ ] 24시간 x 7일 요일/시간대별 장애 히트맵 (Heatmap)
  - [ ] 주변 Wi-Fi 채널 점유 다이어그램
- [ ] **Jinja2 HTML/CSS 템플릿 설계 (`templates/`)**
  - [ ] 일별 장애 요약 보고서 템플릿 (`daily_report.html`)
  - [ ] 주기성/패턴 심층 분석 보고서 템플릿 (`pattern_report.html`)
  - [ ] 통신사/공유기 제조사 제출용 장애 입증서 템플릿 (`vendor_proof.html`)
  - [ ] 인쇄 표준 규격 스타일시트 (A4, 페이지 넘김 방지, 한글 폰트 임베딩)
- [ ] WeasyPrint 기반 HTML -> 고품질 PDF 변환 파이프라인 구현 (`src/reporter/pdf_generator.py`)

---

## 📌 Phase 6. CLI 인터페이스 및 데몬/서비스 러너
- [ ] Typer 기반 CLI 명령어 구축 (`src/main.py`)
  - [ ] `wifi-analyzer monitor`: 백그라운드 상시 모니터링 실행
  - [ ] `wifi-analyzer diagnose`: 현재 네트워크 즉각 정밀 진단 1회 실행
  - [ ] `wifi-analyzer report --daily [YYYY-MM-DD]`: 일별 리포트 PDF 생성
  - [ ] `wifi-analyzer report --pattern [--days 7|30]`: 기간별 패턴 분석 리포트 PDF 생성
  - [ ] `wifi-analyzer status`: 최근 발생 장애 및 가동률 상태 출력
- [ ] Windows 작업 스케줄러 / 백그라운드 서비스 등록 스크립트 작성
- [ ] Linux systemd 서비스 유닛 파일 작성

---

## 📌 Phase 7. 테스트, 시뮬레이션 및 검증
- [ ] 네트워크 메트릭 수집기 단위 테스트 (Mock 기반 OS 명령어 출력 테스트)
- [ ] **가상 장애 시나리오 시뮬레이터 작성**
  - [ ] "매일 오전 09:00 Wi-Fi AP 크래시" 가상 시계열 데이터 주입 스크립트
- [ ] 패턴 탐지 엔진이 09:00 집중 발생 패턴을 정확히 감지하는지 검증
- [ ] 생성된 PDF 리포트 레이아웃 및 한글 폰트 렌더링 무결성 확인
- [ ] Git 커밋 및 변경사항 반영
