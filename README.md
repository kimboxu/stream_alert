# StreamAlert 📡

**경량 AI 기반 실시간 방송 재미도 분석 및 개인화 알림 시스템**

[![Python](https://img.shields.io/badge/Python-3.13.3-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Latest-009688.svg)](https://fastapi.tiangolo.com/)
[![Flutter](https://img.shields.io/badge/Flutter-Latest-02569B.svg)](https://flutter.dev/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> 💡 **1GB RAM 환경에서도 동작하는 실시간 방송 모니터링 & 하이라이트 분석 시스템**

---

## 📋 목차

- [소개](#-소개)
- [주요 기능](#-주요-기능)
- [시스템 아키텍처](#-시스템-아키텍처)
- [기술 스택](#-기술-스택)
- [설치 방법](#-설치-방법)
- [사용 방법](#-사용-방법)
- [재미도 분석 알고리즘](#-재미도-분석-알고리즘)
- [성능 지표](#-성능-지표)
- [프로젝트 구조](#-프로젝트-구조)
- [API 문서](#-api-문서)
- [기여 가이드](#-기여-가이드)
- [라이선스](#-라이선스)
- [논문 및 참고자료](#-논문-및-참고자료)

---

## 🎯 소개

**StreamAlert**는 다중 플랫폼(Chzzk, Soop, YouTube, 네이버 카페)의 인터넷 방송 활동을 실시간으로 모니터링하고, **경량 AI 기반 통계 분석**을 통해 방송의 **재미도(Fun Score)**를 자동으로 계산하여 사용자에게 맞춤형 알림을 제공하는 시스템입니다.

### 🌟 핵심 특징

- **🔥 실시간 하이라이트 자동 검출**: 채팅 반응, 시청자 추세, 참여 다양성을 종합 분석
- **💪 저사양 환경 최적화**: 1GB RAM에서도 안정적 동작 (99.99% API 성공률)
- **🎨 멀티플랫폼 통합**: 4개 플랫폼의 7가지 이벤트를 일원화된 알림으로 제공
- **🤖 경량 AI 모델**: 딥러닝 없이도 문맥을 고려한 재미도 분석 (평균 응답시간 1ms 이하)
- **📱 크로스 플랫폼 알림**: Discord Webhook + Firebase FCM 지원

---

## ✨ 주요 기능

### 1️⃣ 방송 상태 알림
- ✅ 방송 시작(뱅온) / 종료(뱅종)
- ✅ 방송 제목 변경 감지
- ✅ 실시간 시청자 수 추적

### 2️⃣ 실시간 하이라이트 알림
- 📊 **재미도 점수** 기반 하이라이트 자동 탐지
  - 채팅 급증도 (45%)
  - 반응 강도 (30%)
  - 참여 다양성 (10%)
  - 시청자 추세 (15%)
- 🎬 실시간 썸네일 캡처 및 업로드
- 💬 Google Gemini API 기반 하이라이트 설명 자동 생성

### 3️⃣ 핫클립 알림
- 🔥 조회수 급증 클립 자동 감지
- ⏰ 최신성 가중치 적용 (70% 조회수 + 30% 최신성)

### 4️⃣ VOD 업로드 알림
- 📹 다시보기 영상 업로드 즉시 감지
- 📝 하이라이트 타임라인 댓글 자동 작성

### 5️⃣ 유튜브 업로드 알림
- 🎥 YouTube 영상 업로드 모니터링
- 🔔 새 영상 알림 전송

### 6️⃣ 팬카페 게시글 알림
- 📢 네이버 카페 새 게시글 감지
- 👤 특정 작성자 필터링 지원

### 7️⃣ VOD 하이라이트 타임라인 댓글
- ⏱️ 하이라이트 시간을 VOD 타임라인으로 자동 변환
- ⭐ 재미 점수 기반 댓글 포맷 생성

---

## 🏗️ 시스템 아키텍처
```
┌─────────────────────────────────────────────────────────────────┐
│                        데이터 수집 계층                           │
├─────────────────────────────────────────────────────────────────┤
│  Chzzk API  │  Soop API  │  YouTube API  │  Naver Cafe API     │
└──────┬──────┴──────┬─────┴───────┬────────┴──────┬──────────────┘
       │             │             │               │
       ▼             ▼             ▼               ▼
┌─────────────────────────────────────────────────────────────────┐
│                        데이터 처리 계층                           │
├─────────────────────────────────────────────────────────────────┤
│  • 방송 상태 모니터링 (2초 간격)                                  │
│  • 재미도 분석 (5초 간격, 30초 윈도우)                            │
│  • 핫클립 분석 (30분 간격)                                        │
│  • VOD/유튜브/카페 모니터링 (3초 간격)                            │
│  • AI 기반 하이라이트 설명 생성 (Google Gemini API)              │
└──────┬──────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│                        알림 전송 계층                             │
├─────────────────────────────────────────────────────────────────┤
│           Discord Webhook  │  Firebase FCM (Flutter App)        │
│  • 사용자별 맞춤 알림 설정                                        │
│  • 알림 유형별 On/Off 제어                                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ 기술 스택

### Backend
| 분야 | 기술/언어 | 역할 |
|------|-----------|------|
| **언어** | Python 3.13.3 | 서버 로직 및 비동기 처리 |
| **프레임워크** | FastAPI | API 개발 및 고성능 비동기 처리 |
| **데이터 분석** | Pandas, Stats, re | 재미도 계산, 통계 분석 |
| **AI/ML** | Google Gemini API | 하이라이트 설명 자동 생성 |
| **웹 통신** | aiohttp, websockets | HTTP 요청, 웹소켓 실시간 통신 |

### Frontend
| 분야 | 기술 | 용도 |
|------|------|------|
| **프레임워크** | Flutter, Dart | 크로스플랫폼 웹앱 개발 |

### Infrastructure
| 분류 | 서비스 | 용도 |
|------|---------|------|
| **데이터베이스** | Supabase | 사용자 데이터, 설정 정보 저장 |
| **클라우드** | Oracle Cloud | 서버 배포 (1GB RAM, 1 vCPU) |
| **호스팅** | Firebase Hosting | 웹앱 호스팅 |
| **이미지 저장** | Imgbb API | 썸네일 이미지 업로드 |
| **푸시 알림** | Firebase FCM | 모바일 푸시 알림 전송 |

---

## 📦 설치 방법

### 1. 사전 요구사항
- Python 3.13.3 이상
- Oracle Cloud 계정 (또는 1GB RAM 이상 서버)
- Supabase 계정
- Firebase 프로젝트

### 2. 저장소 클론
```bash
git clone https://github.com/kimboxu/stream_alert.git
cd stream_alert
```

### 3. 가상환경 생성 및 활성화
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 4. 의존성 패키지 설치
```bash
pip install -r requirements.txt
```

### 5. 환경 변수 설정
`.env.example` 파일을 복사하여 `.env` 파일 생성 후 필요한 API 키 입력:
```bash
cp .env.example .env
```

`.env` 파일 예시:
```env
# Supabase
supabase_url=https://your-project.supabase.co
supabase_key=your-supabase-anon-key

# Google APIs
GOOGLE_API_KEY=your-gemini-api-key
DeveloperKey=your-youtube-api-key

# Firebase
FIREBASE_PROJECT_ID=your-firebase-project-id
FIREBASE_PRIVATE_KEY=your-firebase-private-key
FIREBASE_CLIENT_EMAIL=your-firebase-client-email

# Imgbb
IMGBB_API_KEY=your-imgbb-api-key

# Chzzk (네이버 로그인 필요)
NID_AUT=your-naver-auth-token
NID_SES=your-naver-session-token

# Soop (아프리카TV 로그인 필요)
AuthTicket=your-afreeca-auth-ticket
```

### 6. 데이터베이스 스키마 설정
Supabase 콘솔에서 `부록 4.2`의 SQL 스키마 실행

### 7. 서버 실행
```bash
python combined_app.py
```

---

## 🚀 사용 방법

### 1. 웹 애플리케이션 접속
```
https://streamalert-a07d2.web.app/
```

### 2. 회원가입/로그인
- Discord Webhook URL 등록
- 사용자 이름 설정

### 3. 알림 설정
- 모니터링할 스트리머 선택
- 알림 유형별 On/Off 설정:
  - ✅ 뱅온 알림
  - ✅ 방제 변경 알림
  - ✅ 하이라이트 알림
  - ✅ 핫클립 알림
  - ✅ VOD 알림
  - ✅ 유튜브 알림
  - ✅ 카페 알림

### 4. Discord에서 알림 수신
설정한 Webhook URL로 실시간 알림 수신

---

## 🧠 재미도 분석 알고리즘

### Fun Score 계산 수식

**최종 재미도 점수 (0~100점)**:
```
FunScore = 0.45 × Score_chat 
         + 0.30 × Score_reaction 
         + 0.10 × Score_diversity 
         + 0.15 × Score_viewer
```

### 1. 채팅 급증 점수 (45%)
```python
Score_chat = min(σ((M_win / M_avg - 3.0) × 100), 100)

# σ(x, m): 시그모이드 변환 함수 = 2 / (1 + e^(-(x-m)))
# M_win: 현재 윈도우(30초) 채팅 수
# M_avg: 기준 평균 채팅 수 (지수 이동 평균)
```

### 2. 반응 강도 점수 (30%)
키워드 가중치 × 길이 가중치 × 밀도:
```python
Score_reaction = min(σ(Σ(w_k × L_k × C_k) / M_chat, 9.0) × 100, 100)

# w_k: 키워드 가중치 (웃음=4.0, 흥분=3.5, 놀람=2.5, 일반=1.0)
# L_k: 길이 가중치 (1~5자=1.0, 51자 이상=2.0)
# C_k: 키워드 등장 횟수
```

### 3. 참여 다양성 점수 (10%)
```python
Score_diversity = UserDiv + LengthDiv + TimeDiv

# UserDiv: 고유 사용자 수 비율
# LengthDiv: 메시지 길이 표준편차
# TimeDiv: 메시지 작성 시간 분산도
```

### 4. 시청자 추세 점수 (15%)
```python
Score_viewer = min(s1 + s2 + s3, 100)

# s1: 단기 증가 추세 (최근 10분 vs 이전 10분)
# s2: 즉시 급등 (현재 vs 1분 전)
# s3: 지속적 상승 (최근 20분을 5구간으로 나눠 비교)
```

### 하이라이트 판단 기준
```python
D_t = max(F_t - min(F_i), 0)  # 직전 1분 최소 대비 점수 차이

if D_t >= 15:  # 작은 하이라이트 → VOD 타임라인 댓글 저장
if D_t >= 70:  # 큰 하이라이트 → 실시간 알림 + VOD 댓글 저장
```

---

## 📊 성능 지표

### 실험 환경
- **서버**: Oracle Cloud VM.Standard.E2.1.Micro (1GB RAM, 1 vCPU)
- **기간**: 30일간 (2025.10.15 ~ 11.14)
- **모니터링 대상**: 15개 채널 (Chzzk 8개 + Soop 7개)

### 주요 성과
| 지표 | 결과 |
|------|------|
| **API 성공률** | 99.997% (45,218,649건 중 45,217,319건 성공) |
| **알림 성공률** | 98.09% (Discord 97.96% + FCM 100%) |
| **평균 응답시간** | 666.65ms (목표: <1000ms ✅) |
| **CPU 사용률** | 평균 38.87%, 최대 92.20% |
| **메모리 사용률** | 평균 84.42%, 최대 93.14% |
| **시스템 가동률** | 100% (30일간 무중단 운영) |

### 하이라이트 검출 정확도
- **Precision**: 100% (False Positive 0건)
- **Recall**: 98.1% (False Negative 5건 / 257개)
- **검출 속도**: 5초 간격 실시간 분석

### 단순 키워드 방식 대비 우수성
| 비교 항목 | 본 연구 (경량 AI) | 규칙 기반 |
|----------|-------------------|-----------|
| 하이라이트 점수 범위 | 20.77~88.56점 (연속 분포) | 대부분 100점 (양극화) |
| 점수 표준편차 | 18.62점 | 30.24점 |
| 하이라이트 구분 능력 | ⭐⭐⭐⭐⭐ | ⭐ |
| 처리 시간 | 1ms 이하 | 1ms 이하 |

---

## 📁 프로젝트 구조
```
stream_alert/
├── combined_app.py              # 메인 애플리케이션
├── my_app.py                    # Flask API 서버
├── base.py                      # 공통 유틸리티 함수
├── shared_state.py              # 전역 상태 관리
├── requirements.txt             # Python 의존성
├── .env.example                 # 환경 변수 템플릿
│
├── data/                        # 데이터 저장 디렉토리
│   ├── highlight_chats/         # 하이라이트 JSON 파일
│   └── user_notifications/      # 유저 알림 로그 파일
│
├── py/                          # 핵심 모듈
│   ├── live_message.py          # 방송 상태 모니터링
│   ├── chat_analyzer.py         # 재미도 분석 알고리즘
│   ├── unified_vod.py           # VOD 처리
│   ├── unified_hot_clip.py      # 핫클립 분석
│   ├── getYoutubeJsonData.py    # 유튜브 모니터링
│   ├── getCafePostTitle.py      # 카페 모니터링
│   ├── discord_webhook_sender.py # 알림 전송
│   ├── notification_service.py  # FCM 푸시 알림
│   └── make_log_api_performance.py # 성능 로깅
│
└── docs/                        # 문서
    ├── 졸업논문_김성재.pdf       # 학사 논문 (전체 알고리즘 설명)
```

---

## 📖 API 문서

### 주요 엔드포인트

#### 1. 사용자 인증
```http
POST /login
Content-Type: application/json

{
  "username": "your_username",
  "discordWebhooksURL": "https://discord.com/api/webhooks/..."
}
```

#### 2. 알림 설정 저장
```http
POST /save_user_settings
Content-Type: application/json

{
  "discordWebhooksURL": "https://discord.com/api/webhooks/...",
  "username": "your_username",
  "뱅온 알림": "on",
  "하이라이트 알림": "on",
  "chat_user_json": {
    "channel_id_1": ["streamer_name_1"],
    "channel_id_2": ["streamer_name_2"]
  }
}
```

#### 3. 하이라이트 데이터 저장 (관리자용)
```http
GET /save_highlight_data
Content-Type: text/event-stream

# SSE 스트림으로 실시간 진행 상황 전송
data: {"status": "processing", "progress": 50, "message": "..."}
```

#### 4. 성능 통계 조회
```http
GET /get_performance_stats?days=7&api_type=chzzk_api

Response:
{
  "status": "success",
  "total_requests": 1234567,
  "success_rate": 99.99,
  "avg_response_time_ms": 627.20
}
```

전체 API 문서는 서버 실행 후 `/docs`에서 확인 가능 (FastAPI Swagger UI)

---

## 🤝 기여 가이드

### 기여 방법
1. Fork this repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### 코딩 컨벤션
- **Python**: PEP 8 스타일 가이드 준수
- **변수명**: 한글 주석 + 영문 변수명
- **들여쓰기**: 공백 4칸
- **비동기 함수**: `async def` 사용, `await` 명시

---

## 📚 논문 및 참고자료

### 논문
- **제목**: StreamAlert: 경량 AI 기반 실시간 방송 재미도 분석 및 개인화 알림 시스템
- **저자**: 김성재
- **학위**: 학사학위 청구논문 (숭실대학교 IT대학 AI융합학부, 2025)
- **지도교수**: 박건우
- **PDF**: [`docs/졸업논문_김성재.pdf`](docs/졸업논문_김성재.pdf)

### 주요 참고문헌
1. 송혜림 외, "청년 1인가구의 생활시간 사용 연구", 한국가족자원경영학회지, 2018
2. 이주헌, 염익준, "실시간 채팅 데이터를 사용하여 하이라이트 추출", 한국통신학회, 2021
3. 문하겸, "사용자 채팅 데이터를 활용한 스트리밍 방송 하이라이트 구간 자동추출 시스템", 충남대학교, 2020

---

## 👨‍💻 개발자

**김성재** (Kim Sungjae)
- GitHub: [@kimboxu](https://github.com/kimboxu)
- Email: kimboxu@soongsil.ac.kr
- 소속: 숭실대학교 IT대학 AI융합학부

---

## 📞 문의

프로젝트에 대한 질문이나 제안 사항이 있으시면 GitHub Issues를 통해 문의해 주세요.

**⭐ 이 프로젝트가 도움이 되셨다면 Star를 눌러주세요!**

---

<div align="center">

**Made with ❤️ by Kim Sungjae**

[⬆ Back to top](#streamalert-)

</div>


