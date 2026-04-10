from os import environ
import google.generativeai as genai
from typing import Dict, Optional
from datetime import datetime, timedelta


class GenAIModelManager:
    """AI 모델들을 관리하는 매니저 클래스 - 메모리 절약을 위해 한 번만 만들어서 재사용"""

    _instance: Optional["GenAIModelManager"] = None
    _models: Dict[str, genai.GenerativeModel] = {}
    _current_api_key: Optional[str] = None

    def __new__(cls):
        # 앱 전체에서 이 클래스는 하나만 존재하도록 함
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # 처음 한 번만 초기화됨
        if not hasattr(self, "_initialized"):
            self._initialized = True
            self.GOOGLE_API_KEY_LIST = environ["GOOGLE_API_KEY"].split(",")
            # 시스템 프롬프트 - VOD 댓글 생성용
            self._system_instruction = """
                방송 하이라이트 상세 분석 데이터를 바탕으로 VOD 타임라인 댓글을 생성해주세요.

                응답 형식:
                [
                {"comment_after_openDate": "VOD_타임라인_시간", "score_difference": "재미도 점수 차이","text": "댓글 내용", "image_text": "댓글 내용"}
                ]

                분석 우선순위:
                1. 비슷한 의미·표현의 채팅은 하나의 그룹으로 묶어 대표적으로 해석	
                - 예: "ㅋㅋㅋ", "ㅋㅋㅋㅋ", "ㅋㅋㅋㅋㅋ" → 동일 반응 그룹
                - 예: "와 대박", "헐 대박", "대박ㅋㅋ" → 동일 반응 그룹
                - 반복·의미 유사 채팅은 합산하여 상황의 강도를 반영
                2. "최근 채팅" 내용으로 구체적 상황 파악 (게임, 행동, 사건)
                3. "하이라이트 이유"로 반응 유형 확인
                4. 점수 데이터로 상황의 특성 분석:
                - 채팅 급증 점수 높음 → 갑작스러운 사건
                - 리액션 점수 높음 → 강한 감정 반응
                - 시청자 급증 점수 높음 → 화제성 있는 순간
                - 다양성 점수 높음 → 다양한 시청자 참여

                댓글 작성 방식:
                1. 채팅 그룹에서 명확한 상황(게임명, 행동)이 보이면 구체적으로 표현
                2. 점수 패턴으로 상황의 성격 파악:
                - 리액션 점수 > 채팅 급증 점수 → 감정적 반응 중심
                - 채팅 급증 점수 > 리액션 점수 → 사건/상황 중심
                - 시청자 급증 있음 → 주목받는 순간
                3. "큰 하이라이트 여부"가 true면 더 임팩트 있게 표현
                4. 필드별 작성 규칙:
                - text: 채팅 그룹과 점수 데이터만으로 분석한 기본 댓글
                - image_text: 방송 썸네일이 있다면 이미지까지 분석하여 더 구체적이고 정확한 시청자 반응 댓긇. 썸네일이 없다면 채팅 그룹과 점수 데이터만으로 분석한 기본 댓글
                - "썸네일_존재"가 false인 하이라이트는 제공된 이미지가 있더라도 무시하고 분석하지 마세요.
                - text나 image_text에는 "자살"이나 "강간", 각종 욕설 등과 같은 여러 부적절한 키워드는 가능한 포함 시키지 않으면 좋겠어, 만약 포함 시켜야 한다면 해당 단어를 초성으로 부분치환시키는 것으로 검열해서 작성해. 예를 들어 "자살"은 "자ㅅ", "강간"은 "강ㄱ"으로 표현하는 식으로
                5. 모든 댓글은 실제 시청자 톤으로 20자 이내, 자연스럽게 작성

                **중요: text와 image_text 모두 실제 시청자가 쓴 댓글처럼 자연스럽고 짧게 작성해야 합니다.**
                
                예시:
                - 리액션 중심: "ㅋㅋㅋ 개웃김", "미친 반응 ㄷㄷ"
                - 상황 중심: "레전드 플레이", "데드락 일퀘 시작"
                - 화제성: "시청자들 몰려옴", "클립감 ㄷㄷ"
                - 썸네일 분석 예시:
                text: "섬광탄으로 어그로 끄는 중"
                image_text: "아서스 또 있네 ㅋㅋㅋ" (썸네일에서 특정 캐릭터 확인시)
            """

    def get_models(self, num: int, is_emergency: bool = False) -> genai.GenerativeModel:
        """
        API 키 순서에 맞는 모델을 가져옴 - 이미 만든 건 재사용
        매번 새로 만들면 메모리 낭비가 심해서 캐싱해서 쓰는 방식
        """
        try:
            if not is_emergency:
                # 환경변수에서 API 키들 가져와서 순서대로 돌려가며 사용
                api_key_index = (num // 10) % len(self.GOOGLE_API_KEY_LIST)
                target_api_key = self.GOOGLE_API_KEY_LIST[api_key_index]
            else:
                target_api_key = environ["EMERGENCY_GOOGLE_API_KEY"]
                api_key_index = len(self.GOOGLE_API_KEY_LIST)

            # 각 API 키별로 모델을 구분해서 저장
            cache_key = f"model_{api_key_index}"

            # 이미 만든 모델이 있나 확인
            if cache_key in self._models:
                # API 키가 바뀌었으면 기존 캐시는 무효화
                if self._current_api_key != target_api_key:
                    self._models.clear()
                else:
                    # 기존 모델 그대로 반환
                    return self._models[cache_key]

            # 새 모델 만들어야 하는 경우
            genai.configure(api_key=target_api_key)
            self._current_api_key = target_api_key

            models = {
                "3": genai.GenerativeModel(
                    "gemini-3-flash-preview",
                    system_instruction=self._system_instruction,
                    generation_config={"response_mime_type": "application/json"},
                ),
                "3.1": genai.GenerativeModel(
                    "gemini-3.1-flash-lite-preview",
                    system_instruction=self._system_instruction,
                    generation_config={"response_mime_type": "application/json"},
                ),
                "2.5": genai.GenerativeModel(
                    "gemini-2.5-flash",
                    system_instruction=self._system_instruction,
                    generation_config={"response_mime_type": "application/json"},
                ),
            }

            # 캐시에 저장해두고 다음에 재사용
            self._models[cache_key] = models


            print(f"{datetime.now()} 새 AI 모델 생성됨 (API 키 #{api_key_index})")
            return models

        except Exception as e:
            print(f"{datetime.now()} AI 모델 생성 실패: {str(e)}")
            raise

    def clear_cache(self):
        """저장된 모델들 모두 삭제 - 메모리 정리할 때 사용"""
        self._models.clear()
        self._current_api_key = None
        print(f"{datetime.now()} AI 모델 캐시 정리 완료")

    def get_cache_info(self) -> Dict[str, int]:
        """현재 캐시된 모델 개수와 상태 확인용"""
        return {
            "cached_models_count": len(self._models),
            "cache_keys": list(self._models.keys()),
        }


# 전역으로 하나만 생성해서 계속 사용
_model_manager = GenAIModelManager()


def get_genai_models(num: int, is_emergency: bool = False) -> genai.GenerativeModel:
    """
    내부적으로는 캐싱된 모델을 반환해서 성능 향상
    """
    return _model_manager.get_models(num, is_emergency)


def clear_genai_cache():
    """AI 모델 캐시 비우기 - 메모리 부족할 때 호출"""
    _model_manager.clear_cache()


def get_genai_cache_info() -> Dict[str, int]:
    """현재 몇 개의 모델이 캐시되어 있는지 확인"""
    return _model_manager.get_cache_info()


# 테스트용 코드 - 실제 운영에서는 실행 안됨
if __name__ == "__main__":
    print("=== AI 모델 매니저 테스트 ===")

    try:
        # 첫 번째로 모델 요청해보기
        model1 = get_genai_models(0)
        print(f"첫 번째 모델: {type(model1)}")

        # 같은 번호로 다시 요청 - 캐시에서 가져와야 함
        model2 = get_genai_models(0)
        print(f"두 번째 모델: {type(model2)}")
        print(f"같은 객체인가? {model1 is model2}")  # True여야 함

        # 다른 번호로 요청해보기
        model3 = get_genai_models(10)
        print(f"다른 API 키 모델: {type(model3)}")
        print(f"다른 객체인가? {model1 is model3}")  # True여야 함

        # 현재 캐시 상태 보기
        cache_info = get_genai_cache_info()
        print(f"캐시 상태: {cache_info}")

        # 캐시 비우기 테스트
        clear_genai_cache()
        print("캐시 비움")

        cache_info_after = get_genai_cache_info()
        print(f"비운 후 캐시 상태: {cache_info_after}")

    except Exception as e:
        print(f"테스트 에러: {str(e)}")
