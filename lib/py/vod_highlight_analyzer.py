"""
vod_highlight_analyzer.py
==========================

방송이 종료 후 재시작되면서 발생했던 실시간 채팅 분석 버그 때문에
당시 하이라이트를 놓친 방송을, 치지직 "다시보기(VOD)"에서 내려받은
채팅 전체 CSV로 사후 분석해서 하이라이트를 추출하는 스크립트입니다.

기존 실시간 분석기(chat_analyzer.py의 ChatAnalyzer)는 절대 수정하지 않습니다.
대신 그 안에서 "입력을 넣으면 점수가 나오는" 순수 계산 로직(정규식, 가중치,
점수 계산 공식)만 이 파일 안에 동일하게 재구현해서 사용합니다.

재사용하는 것 (기존 파일에서 import, 코드 그대로 사용):
    - live_message.highlight_chat_Data      : 하이라이트 저장용 데이터 클래스
    - highlight_chat_saver.HighlightChatSaver: 실시간과 동일한 파일 저장 로직
    - base.get_stream_start_id              : 실시간과 동일한 stream_start_id 생성 규칙
    - base.format_time_for_comment          : 초(seconds) -> "HH:MM:SS" 문자열 변환
    - genai_model.get_genai_models 등        : Gemini 멀티 모델/멀티 키 폴백 클라이언트
    - json_repair_handler.JSONRepairHandler  : API 재시도 + JSON 파싱/복구
    - json_repair_handler.ContentCensorHandler: 생성된 댓글 부적절 키워드 검열

    * genai_model.py / json_repair_handler.py는 self.init(라이브 앱 전역 상태)에
      의존하지 않는 순수 유틸리티 모듈이라, 라이브 파이프라인과 완전히 분리된
      이 배치 스크립트에서도 안전하게 그대로 재사용할 수 있습니다.
    * 실행 전에 환경변수 GOOGLE_API_KEY(콤마로 구분된 키 목록)가 설정되어 있어야
      genai_model.py의 GenAIModelManager가 정상 동작합니다.

새로 구현하는 것 (ChatAnalyzer의 계산 로직을 "라이브 상태" 의존성 없이 재현):
    - 재생시간(문자열) -> 초(float) 파싱
    - CSV 로드
    - 5초 간격 슬라이딩 윈도우 시뮬레이션 (실시간의 analyze()를 배치용으로 재현)
    - 채팅 급증 / 반응 강도 / 다양성 점수 계산 (viewer_trend는 가중치 0으로 제외)
    - 하이라이트 판정 + 쿨다운 + 구간 내 최고점(peak) 추출
    - (이미지 없는) 텍스트 전용 Gemini 프롬프트로 하이라이트 댓글(text/image_text) 생성
    - HighlightChatSaver가 요구하는 형식으로 변환 후 저장

사용 예시:
    export GOOGLE_API_KEY="key1,key2"   # 미리 설정 (콤마로 여러 키 가능)
    python vod_highlight_analyzer.py \\
        --csv "chat_2026-08-14.csv" \\
        --channel-id bighead033 \\
        --channel-name 빅헤드 \\
        --open-date "2026-08-14 18:42:53" \\
        --last-title "좋 은 아 침"

    # AI 호출 없이 규칙 기반 문구만으로 빠르게 저장하고 싶다면:
    python vod_highlight_analyzer.py ... --skip-ai
"""

import argparse
import asyncio
import csv
import json
import re
import statistics
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime
from math import exp
from os import environ
from pathlib import Path
from typing import Dict, List, Optional

# ── 기존 프로젝트 모듈 재사용 (수정하지 않고 그대로 import) ───────────────
from base import format_time_for_comment, get_stream_start_id
from live_message import highlight_chat_Data
from highlight_chat_saver import HighlightChatSaver

# 주의: genai_model.py는 "모듈을 import하는 시점"에 바로
# environ["GOOGLE_API_KEY"]를 읽어서 없으면 그 자리에서 예외를 던집니다.
# --skip-ai로 AI를 아예 안 쓰는 실행 경로까지 GOOGLE_API_KEY를 강제하지 않도록,
# 이 두 모듈은 최상단에서 import하지 않고 generate_ai_timeline_comments() 안에서
# "실제로 AI를 쓰기로 확정된 시점"에만 지연 import(lazy import) 합니다.


# =============================================================================
# 1. CSV 파싱
# =============================================================================

@dataclass
class ChatMessage:
    """CSV 한 줄(채팅 한 개)을 표현하는 데이터 클래스"""

    seconds: float   # 방송 시작 후 경과 시간(초). "00:00:15" -> 15.0
    nickname: str
    uid: str
    message: str


def parse_playtime_to_seconds(text: str) -> float:
    """
    "00:00:15" / "1:02:03" 같은 재생시간 문자열을 초(float)로 변환합니다.

    치지직 다시보기 채팅은 방송 길이가 길면 시(H)가 두 자리를 넘어갈 수도
    있으므로, datetime.strptime 대신 직접 콜론(:)으로 나눠서 파싱합니다.
    """
    parts = [p.strip() for p in text.strip().split(":")]

    try:
        parts = [float(p) for p in parts]
    except ValueError as e:
        raise ValueError(f"재생시간 형식을 숫자로 변환할 수 없습니다: '{text}'") from e

    if len(parts) == 3:
        hours, minutes, seconds = parts
    elif len(parts) == 2:
        hours, minutes, seconds = 0.0, parts[0], parts[1]
    else:
        raise ValueError(f"알 수 없는 재생시간 형식입니다: '{text}'")

    return hours * 3600 + minutes * 60 + seconds


def load_chat_csv(csv_path: str) -> List[ChatMessage]:
    """
    "재생시간,닉네임,id,메시지" 컬럼을 가진 CSV를 읽어
    재생시간 기준으로 정렬된 ChatMessage 리스트를 반환합니다.

    비어있는 줄이나 파싱 실패한 줄은 조용히 건너뛰되, 몇 개나 건너뛰었는지는
    로그로 남겨서 데이터 누락을 바로 알아챌 수 있게 합니다.
    """
    messages: List[ChatMessage] = []
    skipped_count = 0

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        required_columns = {"재생시간", "닉네임", "id", "메시지"}
        if reader.fieldnames is None or not required_columns.issubset(set(reader.fieldnames)):
            raise ValueError(
                f"CSV 헤더가 예상과 다릅니다. 필요한 컬럼: {required_columns}, "
                f"실제 컬럼: {reader.fieldnames}"
            )

        for row in reader:
            playtime_text = (row.get("재생시간") or "").strip()
            message_text = (row.get("메시지") or "").strip()

            if not playtime_text or not message_text:
                skipped_count += 1
                continue

            try:
                seconds = parse_playtime_to_seconds(playtime_text)
            except ValueError:
                skipped_count += 1
                continue

            messages.append(
                ChatMessage(
                    seconds=seconds,
                    nickname=(row.get("닉네임") or "").strip(),
                    uid=(row.get("id") or "").strip(),
                    message=message_text,
                )
            )

    messages.sort(key=lambda m: m.seconds)

    if skipped_count:
        print(f"[load_chat_csv] 파싱 실패/빈 행 {skipped_count}개를 건너뛰었습니다.")
    print(f"[load_chat_csv] 총 {len(messages)}개 채팅을 불러왔습니다.")

    return messages


# =============================================================================
# 2. 순수 계산 로직 (ChatAnalyzer의 계산 부분을 라이브 상태 없이 재현)
# =============================================================================

@dataclass
class VodAnalysisTick:
    """실시간 코드의 ChatAnalysisData에 대응하는, 배치용 분석 시점 데이터"""

    tick_seconds: float               # 이번 분석 시점 (방송 시작 후 경과 초)
    message_count: int = 0
    fun_keywords: Dict[str, float] = field(default_factory=dict)


class VodHighlightAnalyzer:
    """
    ChatAnalyzer의 "순수 계산" 부분(정규식 패턴, 가중치, 점수 공식)을
    라이브 상태(self.init, Supabase, pandas title_data 등) 없이 재구현한 버전.

    라이브 버전과 다른 점:
        - datetime.now() 대신 재생시간(초, float)을 시간축으로 사용합니다.
        - viewer_count(시청자 수) 데이터가 없으므로 viewer_spike 가중치를 0으로
          설정하고, 채팅급증/반응강도/다양성 3개 점수만으로 최종 점수를 냅니다.
        - baseline_metrics를 pandas DataFrame이 아니라 평범한 dict로 관리합니다.
          (지수이동평균으로 자기 자신을 계속 갱신하는 로직은 동일합니다.)
    """

    def __init__(
        self,
        window_size: float = 30.0,       # 분석에 사용할 채팅 윈도우 길이(초)
        analysis_interval: float = 5.0,  # 몇 초 간격으로 분석 시점을 찍을지
        small_fun_difference: float = 25.0,
        big_fun_difference: float = 85.0,
        cooldown: float = 120.0,         # 하이라이트 간 최소 간격(초)
        initial_baseline: Optional[dict] = None,
    ):
        self.window_size = window_size
        self.analysis_interval = analysis_interval
        self.small_fun_difference = small_fun_difference
        self.big_fun_difference = big_fun_difference
        self.cooldown = cooldown

        # 1분에 해당하는 tick 개수 (라이브 코드의 history_1min과 동일한 개념)
        self.history_1min = max(int(60 / self.analysis_interval), 1)
        self.analysis_history: deque = deque(maxlen=self.history_1min * 30)

        # 채팅 재미 감지용 정규식 (chat_analyzer.py의 fun_patterns와 100% 동일)
        self.fun_patterns = {
            "laugh": re.compile(r"ㅋ{2,}|z{2,}|ㅎ{2,}|하하|푸하|풉|웃겨|개웃|존웃|엌"),
            "excitement": re.compile(
                r"!{1,}|\?{2,}|ㄷ{2,}|ㄱ{2,}|ㅏ{2,}|헐|대박|캬|^굳$|^구뜨|^와|^오$|^오(?!\S)|^오.|^오우|^오이|^옹|^올$|우와|미친|ㅁㅊ|나이스|ㄴㅇㅅ|개쩔|쩐다|고고|가자잇|가즈아|ㄱㅈㅇ|ㄷㄱㄷㄱ|ㄷㄱㅈ|ㅗㅜㅑ|으흐흐|^좋..$|^좋.$"
            ),
            "surprise": re.compile(
                r"^\s*\?\s*$|헉|왓|뭣|뭐야|뭐여|무야|어라|어래|어머|어떻게|진짜|실화|레전드|띠용|충격|놀람|지리네|o0o|O0O|0o0"
            ),
            "reaction": re.compile(
                r"ㅠ{2,}|ㅜ{2,}|ㅎㅇㅌ|ㄹㅇ|앗|아악|아으|으아|으악|끄악|아니|안돼|제발|부탁|응원"
            ),
            "greeting": re.compile(
                r"^.하$|^.바$|^.ㅎ$|^.ㅂ$|ㅎㅇ|^하이|안녕|반갑|^ㅁㅍ$"
            ),
        }

        self.length_score_tiers = {
            "laugh": [
                (1, 5, 1.0), (6, 15, 1.2), (16, 30, 1.5), (31, 50, 1.8), (51, float("inf"), 2.0),
            ],
            "excitement": [
                (1, 5, 1.0), (6, 10, 1.2), (11, 20, 1.4), (21, float("inf"), 1.6),
            ],
            "surprise": [(1, float("inf"), 1.0)],
            "reaction": [
                (1, 5, 1.0), (6, 10, 1.1), (11, 20, 1.3), (21, float("inf"), 1.5),
            ],
            "greeting": [(1, float("inf"), 1.0)],
        }

        # 가중치: viewer_spike는 시청자 데이터가 없으므로 0으로 제외
        # (주의: 합이 1.0이 아니라 0.85이므로 최종 점수의 이론상 최댓값도 85점입니다.
        #  small/big_fun_difference 기본값이 라이브(25/85)와 동일하게 맞춰져 있으니,
        #  하이라이트가 너무 적게/많이 나오면 이 두 값을 조정해보세요.)
        self.weights = {
            "chat_spike": 0.45,
            "reaction": 0.30,
            "diversity": 0.10,
            "viewer_spike": 0.0,
        }

        self.keyword_weights = {
            "laugh": 4.0,
            "excitement": 3.5,
            "surprise": 2.5,
            "reaction": 1.0,
        }

        # baseline_metrics: 라이브 코드의 title_data.loc[channel_id, "baseline_metrics"]에
        # 해당하는 값을 평범한 dict로 관리합니다. 초기값은 방송 초반 데이터로 지수이동평균이
        # 알아서 수렴하므로, 대략적인 기본값이면 충분합니다.
        self.baseline_metrics = initial_baseline or {
            "avg_chat_count": 5.0,
            "avg_viewer_count": 0.0,   # 사용하지 않음 (viewer_spike 가중치 0)
            "avg_threshold_score": 15.0,
            "sequence_count": 0,
        }

    # ── 키워드 추출 (chat_analyzer.py의 _extract_keywords와 동일 로직) ──────
    def _extract_keywords(self, message: str) -> Dict[str, float]:
        keyword_scores: Dict[str, float] = {}

        for pattern_name, pattern in self.fun_patterns.items():
            matches = pattern.findall(message.lower())
            if not matches:
                continue

            total_score = 0.0
            tiers = self.length_score_tiers.get(pattern_name, [(1, float("inf"), 1.0)])

            for match in matches:
                match_length = len(match)
                score = 1.0
                for min_len, max_len, tier_score in tiers:
                    if min_len <= match_length <= max_len:
                        score = tier_score
                        break
                total_score += score

            keyword_scores[pattern_name] = total_score

        return keyword_scores

    def _sigmoid_transform(self, x: float, midpoint: float = 1.0, steepness: float = 2.0) -> float:
        return 2 / (1 + exp(-steepness * (x - midpoint)))

    # ── 점수 계산 (viewer_trend만 빠진 것 외에는 라이브와 동일한 공식) ──────
    def _calculate_chat_spike_score(self, tick: VodAnalysisTick) -> float:
        del_greeting_message_count = tick.message_count - int(
            tick.fun_keywords.get("greeting", 0.0)
        )
        count_ratio = del_greeting_message_count / self.baseline_metrics["avg_chat_count"]
        return min(self._sigmoid_transform(count_ratio, 3.0) * 100, 100)

    def _calculate_reaction_score(self, tick: VodAnalysisTick) -> float:
        total_weighted_keywords = 0.0
        for keyword, count in tick.fun_keywords.items():
            weight = self.keyword_weights.get(keyword, 1.0)
            total_weighted_keywords += count * weight

        keyword_density = total_weighted_keywords / self.baseline_metrics["avg_chat_count"]
        return min(self._sigmoid_transform(keyword_density, 4.0) * 100, 100)

    def _calculate_diversity_score(self, window_chats: List[ChatMessage]) -> float:
        if not window_chats:
            return 0.0

        unique_users = len({chat.nickname for chat in window_chats})
        user_diversity = min((unique_users / len(window_chats)) * 50, 50)

        msg_lengths = [len(chat.message) for chat in window_chats]
        length_diversity = (
            min(statistics.stdev(msg_lengths) / 20, 10) if len(msg_lengths) > 1 else 0.0
        )

        if len(window_chats) >= 3:
            sorted_chats = sorted(window_chats, key=lambda c: c.seconds)
            time_intervals = [
                sorted_chats[i].seconds - sorted_chats[i - 1].seconds
                for i in range(1, len(sorted_chats))
            ]
            time_diversity = min(statistics.stdev(time_intervals) / 5, 40) if time_intervals else 0.0
        else:
            time_diversity = 0.0

        return user_diversity + length_diversity + time_diversity

    def _update_baselines(self, tick: VodAnalysisTick, final_score: float) -> None:
        """지수이동평균으로 baseline_metrics를 갱신 (라이브 _update_baselines와 동일 공식)"""
        sequence_count = self.baseline_metrics["sequence_count"]
        avg_threshold_score = self.baseline_metrics["avg_threshold_score"]

        if final_score > avg_threshold_score and sequence_count >= 0:
            self.baseline_metrics["sequence_count"] += 1
        elif final_score < avg_threshold_score and sequence_count <= 0:
            self.baseline_metrics["sequence_count"] -= 1
        else:
            self.baseline_metrics["sequence_count"] = 0

        alpha = 0.01912  # 1 - 0.1^(1/120)
        alpha *= abs(self.baseline_metrics["sequence_count"]) // 24 + 1

        self.baseline_metrics["avg_chat_count"] = (
            alpha * tick.message_count + (1 - alpha) * self.baseline_metrics["avg_chat_count"]
        )
        self.baseline_metrics["avg_threshold_score"] = (
            alpha * final_score + (1 - alpha) * self.baseline_metrics["avg_threshold_score"]
        )
        # avg_viewer_count는 viewer_spike 가중치가 0이라 사용되지 않으므로 갱신하지 않습니다.

    def get_score_difference(self, fun_score: float) -> float:
        if len(self.analysis_history) < self.history_1min:
            return 0.0
        recent_scores = list(self.analysis_history)[-self.history_1min:]
        return max(fun_score - min(score for _, score in recent_scores), 0.0)

    def _is_highlight(self, fun_score: float, fun_difference: float) -> bool:
        if fun_score < self.baseline_metrics["avg_threshold_score"]:
            return False
        if len(self.analysis_history) < self.history_1min * 2:
            return False
        if self.get_score_difference(fun_score) < fun_difference:
            return False
        return True

    def check_cooldown(self, current_seconds: float, last_highlight_seconds: float) -> bool:
        return (current_seconds - last_highlight_seconds) >= self.cooldown

    def _should_create_new_highlight(
        self, fun_score: float, current_seconds: float, last_highlight_seconds: Optional[float]
    ) -> bool:
        if not self._is_highlight(fun_score, self.small_fun_difference):
            return False
        if last_highlight_seconds is None:
            return True
        return self.check_cooldown(current_seconds, last_highlight_seconds)

    def _determine_highlight_reason(self, tick: VodAnalysisTick, score_details: dict) -> str:
        reasons = []
        if tick.fun_keywords.get("laugh", 0) >= tick.message_count / 3:
            reasons.append("😂 폭소 반응")
        if tick.fun_keywords.get("excitement", 0) >= tick.message_count / 3:
            reasons.append("🔥 뜨거운 반응")
        if tick.fun_keywords.get("surprise", 0) >= tick.message_count / 3:
            reasons.append("😱 놀라운 순간")
        if score_details["chat_spike_score"] >= 50:
            reasons.append("💬 채팅량 폭증")
        if score_details["final_score"] >= 80:
            reasons.append("🏆 레전드 순간")
        return " + ".join(reasons) if reasons else "재미있는 순간 감지"

    # ── 한 시점(tick)을 분석하는 메인 함수 (라이브의 analyze()에 대응) ─────
    def analyze_tick(
        self,
        tick_seconds: float,
        window_chats: List[ChatMessage],
        last_highlight_seconds: Optional[float],
    ) -> dict:
        keyword_counter: Counter = Counter()
        for chat in window_chats:
            for key, count in self._extract_keywords(chat.message).items():
                keyword_counter[key] += count

        tick = VodAnalysisTick(
            tick_seconds=tick_seconds,
            message_count=len(window_chats),
            fun_keywords=dict(keyword_counter),
        )

        chat_spike_score = self._calculate_chat_spike_score(tick)
        reaction_score = self._calculate_reaction_score(tick)
        diversity_score = self._calculate_diversity_score(window_chats)
        # viewer_trend_score는 가중치 0이므로 계산 자체를 생략합니다.

        final_score = min(
            chat_spike_score * self.weights["chat_spike"]
            + reaction_score * self.weights["reaction"]
            + diversity_score * self.weights["diversity"],
            100.0,
        )

        # 점수 판정에 쓰이는 baseline은 "이번 tick 반영 전" 값을 기준으로 판정해야
        # 라이브 로직과 동일한 순서가 되므로, 판정을 먼저 하고 baseline 갱신은 나중에 합니다.
        score_details = {
            "chat_spike_score": chat_spike_score,
            "reaction_score": reaction_score,
            "diversity_score": diversity_score,
            "viewer_trend_score": 0.0,
            "final_score": final_score,
            "baseline_chat_count": self.baseline_metrics["avg_chat_count"],
            "baseline_threshold": self.baseline_metrics["avg_threshold_score"],
            "highlights": self._is_highlight(final_score, self.small_fun_difference),
            "big_highlights": self._is_highlight(final_score, self.big_fun_difference),
            "score_difference": self.get_score_difference(final_score),
            "should_create_new_highlight": self._should_create_new_highlight(
                final_score, tick_seconds, last_highlight_seconds
            ),
        }

        comment_after_openDate = format_time_for_comment(int(tick_seconds))

        detailed_log = {
            "tick_seconds": tick_seconds,
            "fun_score": final_score,
            "score_components": score_details,
            "reason": self._determine_highlight_reason(tick, score_details),
            "analysis_data": {
                "message_count": tick.message_count,
                "viewer_count": 0,
                "fun_keywords": tick.fun_keywords,
            },
            "comment_after_openDate": comment_after_openDate,
            "chat_context": [
                f"{chat.nickname}: {chat.message}" for chat in window_chats[-30:]
            ],
        }

        # 다음 tick 판정을 위해 baseline과 히스토리를 갱신 (라이브와 동일한 순서)
        self._update_baselines(tick, final_score)
        self.analysis_history.append((tick_seconds, final_score))

        return detailed_log


# =============================================================================
# 3. 전체 파이프라인: CSV -> 하이라이트 추출 -> highlight_chat_Data 생성
# =============================================================================

def extract_highlights_from_messages(
    messages: List[ChatMessage],
    analyzer: VodHighlightAnalyzer,
) -> List[dict]:
    """
    정렬된 채팅 리스트 전체를 analysis_interval 간격으로 훑으면서
    하이라이트 "구간"들을 찾고, 각 구간의 최고점(peak) detailed_log만 반환합니다.

    라이브 코드의 change_score_to_peak()와 같은 개념: 연속으로 하이라이트로
    판정되는 구간이 이어지는 동안은 계속 더 높은 점수로 peak를 갱신하다가,
    구간이 끝나는 순간 그 peak 하나만 최종 하이라이트로 확정합니다.
    """
    if not messages:
        return []

    max_seconds = messages[-1].seconds
    window_size = analyzer.window_size
    interval = analyzer.analysis_interval

    # 슬라이딩 윈도우를 O(N) 시간에 처리하기 위한 투 포인터
    # (매 tick마다 전체 리스트를 다시 훑지 않도록 성능을 고려했습니다)
    left = 0
    right = 0

    current_streak_peak: Optional[dict] = None
    finalized_highlights: List[dict] = []
    last_highlight_seconds: Optional[float] = None

    tick = 0.0
    while tick <= max_seconds:
        window_start = tick - window_size

        while left < len(messages) and messages[left].seconds < window_start:
            left += 1
        while right < len(messages) and messages[right].seconds <= tick:
            right += 1

        window_chats = messages[left:right]

        if window_chats:
            detailed_log = analyzer.analyze_tick(tick, window_chats, last_highlight_seconds)
            score_details = detailed_log["score_components"]

            if score_details["should_create_new_highlight"]:
                current_streak_peak = detailed_log
                last_highlight_seconds = tick
            elif score_details["highlights"] and current_streak_peak is not None:
                if detailed_log["fun_score"] > current_streak_peak["fun_score"]:
                    current_streak_peak = detailed_log
            elif not score_details["highlights"] and current_streak_peak is not None:
                finalized_highlights.append(current_streak_peak)
                current_streak_peak = None

        tick += interval

    # 방송이 끝날 때까지 하이라이트 구간이 안 끝났다면 마지막 peak도 포함
    if current_streak_peak is not None:
        finalized_highlights.append(current_streak_peak)

    return finalized_highlights


def build_rule_based_timeline_comments(finalized_highlights: List[dict]) -> List[dict]:
    """
    AI 없이, 규칙 기반으로 만든 reason 문구를 그대로 text/image_text에 채워 넣습니다.
    AI 호출이 실패했을 때의 폴백(fallback)이자, --skip-ai 옵션의 결과물로도 사용됩니다.
    """
    return [
        {
            "comment_after_openDate": log["comment_after_openDate"],
            "score_difference": log["score_components"]["score_difference"],
            "text": log["reason"],
            "image_text": log["reason"],  # VOD 채팅만으로는 이미지가 없어 text와 동일하게 채움
        }
        for log in finalized_highlights
    ]


def _prepare_ai_highlight_data(finalized_highlights: List[dict]) -> List[dict]:
    """
    Gemini 프롬프트에 넣을 분석 데이터를 만듭니다.
    chat_analyzer.py의 _prepare_highlight_data()와 같은 키 스키마를 쓰되,
    이미지/시청자 데이터가 없는 항목은 각각 False/0으로 채웁니다.
    """
    highlight_data = []
    for i, log in enumerate(finalized_highlights):
        keywords = log["analysis_data"]["fun_keywords"]
        score = log["score_components"]

        highlight_data.append(
            {
                "하이라이트_ID": f"HIGHLIGHT_{i + 1}",
                "재미도_점수": log["fun_score"],
                "하이라이트_이유": log["reason"],
                "최근_채팅": log["chat_context"],
                "VOD_타임라인_시간": log["comment_after_openDate"],
                "썸네일_존재": False,  # VOD 채팅만 있고 이미지가 없으므로 항상 False
                "메시지_개수": log["analysis_data"]["message_count"],
                "시청자_수": 0,  # 시청자 데이터 없음
                "웃음_키워드_수": keywords.get("laugh", 0),
                "놀람_키워드_수": keywords.get("surprise", 0),
                "흥분_키워드_수": keywords.get("excitement", 0),
                "일반반응_키워드_수": keywords.get("reaction", 0),
                "인사_키워드_수": keywords.get("greeting", 0),
                "채팅_급증_점수": score["chat_spike_score"],
                "리액션_점수": score["reaction_score"],
                "다양성_점수": score["diversity_score"],
                "시청자_급증_점수": 0,  # 시청자 데이터 없음
                "기준_채팅_수": score["baseline_chat_count"],
                "하이라이트_여부": score["highlights"],
                "큰_하이라이트_여부": score["big_highlights"],
                "재미도_점수_차이": score["score_difference"],
            }
        )
    return highlight_data


def _create_vod_timeline_prompt(highlight_data: List[dict]) -> str:
    """
    chat_analyzer.py의 _create_timeline_prompt()와 동일한 형식이되,
    이미지가 없다는 점을 모델에게 한 번 더 명시합니다.
    (system_instruction 자체는 genai_model.py의 것을 그대로 재사용합니다.)
    """
    return f"""다음 상세 분석 데이터를 바탕으로 VOD 타임라인 댓글을 생성해주세요.

이번 요청은 채팅 로그만으로 분석한 것이라 방송 썸네일 이미지가 없습니다.
모든 하이라이트의 "썸네일_존재"가 false이니, image_text도 이미지 분석 없이
text와 마찬가지로 채팅 그룹과 점수 데이터만으로 작성해주세요.

분석 데이터:
{json.dumps(highlight_data, ensure_ascii=False, indent=2)}"""


async def generate_ai_timeline_comments(
    finalized_highlights: List[dict],
    is_emergency: bool = False,
    max_parse_retries: int = 10,
) -> List[dict]:
    """
    chat_analyzer.py의 _make_highlight_chat()과 동일한 파이프라인
    (멀티 모델 폴백 -> JSON 파싱/재시도 -> 원본 수치 복원 -> 검열)을 재사용해서
    Gemini로 하이라이트 댓글(text/image_text)을 생성합니다.

    실패하면 규칙 기반 문구(build_rule_based_timeline_comments)로 자동 대체되므로,
    호출부에서는 항상 유효한 timeline_comments 리스트를 받게 됩니다.
    """
    emergency_timeline_comments = build_rule_based_timeline_comments(finalized_highlights)

    if not finalized_highlights:
        return emergency_timeline_comments

    # GOOGLE_API_KEY가 없으면 genai_model을 import하지도 않고 바로 규칙 기반으로 대체합니다.
    # (genai_model은 import 시점에 이 환경변수를 강제로 읽으므로, 없는 채로 import하면 죽습니다)
    if not environ.get("GOOGLE_API_KEY"):
        print("[generate_ai_timeline_comments] GOOGLE_API_KEY가 설정되어 있지 않아 규칙 기반 문구로 대체합니다.")
        return emergency_timeline_comments

    from genai_model import get_genai_models, get_genai_generate_config, get_genai_model_name
    from json_repair_handler import JSONRepairHandler, ContentCensorHandler

    google_api_key_count = len(environ["GOOGLE_API_KEY"].split(","))
    highlight_data = _prepare_ai_highlight_data(finalized_highlights)
    prompt = _create_vod_timeline_prompt(highlight_data)
    msg_list = [prompt]  # 이미지가 없으므로 텍스트 프롬프트만 전달

    print(f"[generate_ai_timeline_comments] Gemini 호출: 하이라이트 {len(finalized_highlights)}개, 이미지 없음")

    # genai_cnt 역할을 하는 카운터. 라이브 코드처럼 self.init에 저장할 필요 없이
    # 이 함수 호출 범위 안에서만 쓰는 지역 변수로 충분합니다.
    genai_counter = {"value": 0}

    async def call_model_with_fallback(client_dict: dict, contents: list):
        model_priority = ["3", "2.5"]
        last_exception: Optional[Exception] = None

        for model_key in model_priority:
            client = client_dict.get(model_key)
            if client is None:
                continue

            model_name = get_genai_model_name(model_key)
            try:
                return await asyncio.to_thread(
                    client.models.generate_content,
                    model=model_name,
                    contents=contents,
                    config=get_genai_generate_config(),
                )
            except Exception as e:
                last_exception = e
                error_msg = str(e)
                is_quota_error = (
                    "429" in error_msg
                    or "quota" in error_msg.lower()
                    or "Resource exhausted" in error_msg
                    or "503" in error_msg
                )
                if not is_quota_error:
                    raise

        raise RuntimeError(f"모든 모델({model_priority}) 할당량 초과. 마지막 에러: {last_exception}")

    async def api_call(emergency_flag: Optional[bool] = None):
        if emergency_flag is None:
            emergency_flag = is_emergency
        genai_counter["value"] += 2
        client_dict = get_genai_models(genai_counter["value"], emergency_flag)
        return await call_model_with_fallback(client_dict, msg_list)

    def response_validator(response) -> bool:
        return isinstance(response, list) and len(response) > 0

    def on_retry_callback(attempt: int, max_retries: int) -> None:
        genai_counter["value"] += 10

    def on_timeout_callback(attempt: int, max_retries: int) -> None:
        print(f"[generate_ai_timeline_comments] API 요청 타임아웃 (시도 {attempt}/{max_retries})")

    def on_error_callback(attempt: int, max_retries: int, error_msg: str) -> None:
        print(f"[generate_ai_timeline_comments] API 요청 오류 (시도 {attempt}/{max_retries}): {error_msg}")

    try:
        ai_timeline_comments = await JSONRepairHandler.call_api_and_parse_json(
            api_func=api_call,
            max_retries=google_api_key_count,
            timeout=600,
            is_emergency=is_emergency,
            on_retry_callback=on_retry_callback,
            on_timeout_callback=on_timeout_callback,
            on_error_callback=on_error_callback,
            response_validator=response_validator,
            max_parse_retries=max_parse_retries,
        )
    except Exception as e:
        print(f"[generate_ai_timeline_comments] Gemini 호출 중 예외 발생, 규칙 기반으로 대체: {str(e)}")
        return emergency_timeline_comments

    if ai_timeline_comments is None:
        print("[generate_ai_timeline_comments] JSON 파싱 최종 실패, 규칙 기반 문구로 대체합니다.")
        return emergency_timeline_comments

    # AI가 재작성하면서 score_difference/comment_after_openDate 값이 바뀔 수 있으므로
    # comment_after_openDate를 키로 원본 값을 복원합니다. (chat_analyzer.py와 동일한 방식)
    source_by_time = {log["comment_after_openDate"]: log for log in finalized_highlights}
    restored_comments = []
    for comment in ai_timeline_comments:
        matched_log = source_by_time.get(comment.get("comment_after_openDate"))
        if matched_log is None:
            restored_comments.append(comment)
            continue
        restored_comments.append(
            {
                **comment,
                "comment_after_openDate": matched_log["comment_after_openDate"],
                "score_difference": matched_log["score_components"]["score_difference"],
            }
        )

    restored_comments = ContentCensorHandler.censor_timeline_comments(restored_comments)
    restored_comments.sort(key=lambda c: c.get("comment_after_openDate", ""))

    return restored_comments


def build_highlight_chat_data(
    timeline_comments: List[dict],
    last_title: str,
) -> highlight_chat_Data:
    """timeline_comments를 HighlightChatSaver가 요구하는 최종 형식으로 감쌉니다."""
    return highlight_chat_Data(
        timeline_comments=timeline_comments,
        stream_end_id="",
        last_title=last_title,
    )


async def analyze_vod_chat_and_save(
    csv_path: str,
    channel_id: str,
    channel_name: str,
    open_date: datetime,
    last_title: str = "",
    window_size: float = 30.0,
    analysis_interval: float = 5.0,
    use_ai: bool = True,
    is_emergency: bool = False,
) -> Optional[str]:
    """
    전체 파이프라인을 실행하는 엔트리 포인트.

    1) CSV 로드
    2) 하이라이트 구간/피크 추출
    3) (use_ai=True면) Gemini로 하이라이트 댓글 생성, 실패 시 규칙 기반으로 자동 대체
    4) highlight_chat_Data로 변환
    5) 기존 HighlightChatSaver로 저장

    반환값: 저장된 파일 경로 (실패 시 None)
    """
    messages = load_chat_csv(csv_path)
    if not messages:
        print("[analyze_vod_chat_and_save] 분석할 채팅이 없어 종료합니다.")
        return None

    analyzer = VodHighlightAnalyzer(window_size=window_size, analysis_interval=analysis_interval)
    finalized_highlights = extract_highlights_from_messages(messages, analyzer)

    print(f"[analyze_vod_chat_and_save] 하이라이트 {len(finalized_highlights)}개 추출 완료")
    for log in finalized_highlights:
        print(
            f"  - {log['comment_after_openDate']} "
            f"(점수 {log['fun_score']:.1f}, {log['reason']})"
        )

    if not finalized_highlights:
        print("[analyze_vod_chat_and_save] 저장할 하이라이트가 없어 종료합니다.")
        return None

    if use_ai:
        timeline_comments = await generate_ai_timeline_comments(
            finalized_highlights, is_emergency=is_emergency
        )
    else:
        timeline_comments = build_rule_based_timeline_comments(finalized_highlights)

    highlight_data = build_highlight_chat_data(timeline_comments, last_title)

    # 라이브 코드와 동일한 규칙으로 stream_start_id 생성 (기존 함수 그대로 재사용)
    stream_start_id = get_stream_start_id(channel_id, str(open_date.isoformat()))

    highlight_saver = HighlightChatSaver(channel_name)
    file_path = await highlight_saver.save_completed_stream_highlight(
        channel_id, channel_name, stream_start_id, highlight_data
    )

    if file_path:
        print(f"[analyze_vod_chat_and_save] 저장 완료: {file_path}")
    else:
        print("[analyze_vod_chat_and_save] 저장 실패")

    return file_path


# =============================================================================
# 4. CLI 진입점
# =============================================================================

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="치지직 VOD 채팅 CSV로 하이라이트 추출 및 저장")
    parser.add_argument("--csv", required=True, help="다시보기 채팅 CSV 파일 경로")
    parser.add_argument("--channel-id", required=True, help="채널 ID (예: bighead033)")
    parser.add_argument("--channel-name", required=True, help="채널 이름 (예: 빅헤드)")
    parser.add_argument(
        "--open-date",
        required=True,
        help="방송 시작 일시 (예: '2026-08-14 18:42:53')",
    )
    parser.add_argument("--last-title", default="", help="당시 방제 (선택)")
    parser.add_argument("--window-size", type=float, default=30.0, help="분석 윈도우 크기(초)")
    parser.add_argument("--interval", type=float, default=5.0, help="분석 간격(초)")
    parser.add_argument(
        "--skip-ai",
        action="store_true",
        help="Gemini 호출 없이 규칙 기반 문구만으로 저장 (빠르고, API 비용 없음)",
    )
    parser.add_argument(
        "--emergency",
        action="store_true",
        help="EMERGENCY_GOOGLE_API_KEY를 사용 (GOOGLE_API_KEY 할당량이 소진된 경우)",
    )
    return parser.parse_args()


async def main() -> None:
    # ── VSCode 디버깅용 토글 ──────────────────────────────────────────
    # try 블록 맨 위의 `raise`가 살아있는 동안은 무조건 except로 빠져서
    # 아래 하드코딩된 값을 쓰기 때문에, CLI 인자 없이 F5만 눌러도 바로
    # 실행되고 원하는 줄에 breakpoint를 걸 수 있습니다.
    #
    # 실제 배포/정식 실행 때는 이 `raise` 한 줄만 지우거나 주석 처리하면
    # 다시 정상적으로 --csv 등 커맨드라인 인자를 파싱해서 씁니다.
    try:
        raise RuntimeError("디버그 모드: 하드코딩된 값 사용")  # noqa: 의도적인 강제 분기
        args = _parse_args()

        csv_path = args.csv
        channel_id = args.channel_id
        channel_name = args.channel_name
        open_date_str = args.open_date
        last_title = args.last_title
        window_size = args.window_size
        analysis_interval = args.interval
        use_ai = not args.skip_ai
        is_emergency = args.emergency

    except Exception:
        # 여기 값들을 원하는 테스트 데이터로 자유롭게 바꿔서 디버깅하세요.
        #
        # csv_path는 "실행할 때의 작업 디렉토리(cwd)"가 아니라 "이 스크립트
        # 파일이 있는 위치"를 기준으로 절대경로를 만듭니다. 터미널에서 실행할
        # 때와 VS Code 디버거로 F5 실행할 때 cwd가 서로 다를 수 있어서
        # (VS Code는 보통 워크스페이스 루트를 cwd로 씀), 상대경로만 쓰면
        # 실행 방식에 따라 파일을 못 찾는 문제가 생길 수 있기 때문입니다.
        csv_path = str(Path(__file__).parent / "[2026-08-15]_빅헤드_14701906.csv")
        channel_id = "bighead033"
        channel_name = "빅헤드"
        open_date_str = "2026-08-14 18:42:53"
        last_title = ""
        window_size = 30.0
        analysis_interval = 5.0
        use_ai = True
        is_emergency = False

    open_date = datetime.fromisoformat(open_date_str)

    await analyze_vod_chat_and_save(
        csv_path=csv_path,
        channel_id=channel_id,
        channel_name=channel_name,
        open_date=open_date,
        last_title=last_title,
        window_size=window_size,
        analysis_interval=analysis_interval,
        use_ai=use_ai,
        is_emergency=is_emergency,
    )


if __name__ == "__main__":
    asyncio.run(main())