import re
import json
import asyncio
from datetime import datetime
from typing import List, Optional, Any, Callable, Coroutine


class JSONRepairHandler:
    """
    JSON 데이터 복구 및 API 호출 관리 클래스

    주요 기능:
    - 손상된 JSON 자동 복구
    - API 호출 재시도 로직
    - JSON 파싱 실패 시 API 재호출
    - Markdown 형식 제거
    - 안전한 파싱 처리
    """

    @staticmethod
    def repair_json_string(json_str: str) -> str:
        """
        JSON 문자열의 일반적인 오류를 수정합니다.

        수정 사항:
        - 중복된 큰따옴표 제거: ""key" -> "key"
        - 마지막 항목의 쉼표 제거: },] -> }]
        - 줄바꿈 정리
        """
        if not json_str:
            return json_str

        # 1. 중복된 큰따옴표 수정 (다양한 패턴)
        # ""text": -> "text":
        json_str = re.sub(r'""([^"]*?)":', r'"\1":', json_str)
        # "text"": -> "text":
        json_str = re.sub(r'"([^"]*?)"":', r'"\1":', json_str)
        # ""text"" -> "text"
        json_str = re.sub(r'""([^"]*?)""', r'"\1"', json_str)

        # 2. 마지막 쉼표 제거 (배열/객체 닫기 전)
        json_str = re.sub(r",(\s*[}\]])", r"\1", json_str)

        # 3. 빈 줄 정리
        json_str = re.sub(r"\n\s*\n", "\n", json_str)

        # 4. 제어 문자 제거
        json_str = "".join(
            char for char in json_str if ord(char) >= 32 or char in "\n\r\t"
        )

        return json_str

    @staticmethod
    def clean_markdown(response_text: str) -> str:
        """
        API 응답에서 Markdown 형식을 제거합니다.

        Args:
            response_text: 원본 응답 텍스트

        Returns:
            정제된 텍스트
        """
        response_text = response_text.strip()

        # JSON 코드 블록 제거
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]

        return response_text.strip()

    @staticmethod
    async def validate_and_parse(json_str: str, max_retries: int = 3) -> Optional[Any]:
        """
        JSON 문자열을 파싱하되, 실패 시 자동 복구를 시도합니다.

        Args:
            json_str: 파싱할 JSON 문자열
            max_retries: 최대 재시도 횟수

        Returns:
            파싱된 Python 객체, 실패 시 None
        """
        # 첫 번째 시도: 그대로 파싱
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"초기 파싱 실패: {str(e)}")

        # 재시도 루프: 자동 복구 시도
        for attempt in range(1, max_retries + 1):
            try:
                await asyncio.sleep(0.001)
                repaired_json = JSONRepairHandler.repair_json_string(json_str)
                result = json.loads(repaired_json)
                print(f"✓ JSON 복구 성공 (시도 {attempt}/{max_retries})")
                return result
            except json.JSONDecodeError as e:
                print(f"복구 시도 {attempt} 실패: {str(e)}")
                print(json_str)
                if attempt == max_retries:
                    print("❌ 최대 재시도 횟수 초과")
                    return None

        return None

    @staticmethod
    async def call_api_with_retry(
        api_func: Callable[[], Coroutine],
        max_retries: int,
        timeout: int,
        is_emergency: bool,
        on_retry_callback: Optional[Callable[[int, int], None]] = None,
        on_timeout_callback: Optional[Callable[[int, int], None]] = None,
        on_error_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> Optional[str]:
        """
        API를 호출하며 재시도 로직을 처리합니다.

        Args:
            api_func: 호출할 비동기 API 함수
            max_retries: 최대 재시도 횟수
            timeout: 요청 타임아웃 (초)
            is_emergency: 사용량 소진시 사용
            on_retry_callback: 재시도 시 호출될 콜백 함수
            on_timeout_callback: 타임아웃 시 호출될 콜백 함수
            on_error_callback: 오류 발생 시 호출될 콜백 함수

        Returns:
            API 응답 텍스트, 실패 시 None
        """
        for attempt in range(max_retries):
            try:
                await asyncio.sleep(0.001)
                response = await asyncio.wait_for(
                    api_func(is_emergency), timeout=timeout
                )
                response_text = response.text.strip()

                return response_text

            except asyncio.TimeoutError:
                print(
                    f"{datetime.now()} ⏱️ API 요청 타임아웃 (시도 {attempt + 1}/{max_retries})"
                )

                if on_timeout_callback:
                    on_timeout_callback(attempt + 1, max_retries)

                if attempt < max_retries - 1:
                    if on_retry_callback:
                        is_emergency = False
                        on_retry_callback(attempt + 1, max_retries)
                    wait_time = 2**attempt
                    print(f"{datetime.now()} {wait_time}초 후 재시도...")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"{datetime.now()} ❌ API 요청 최종 실패 (타임아웃)")
                    return None

            except Exception as e:

                # 429 Rate Limit 에러 감지
                if "429" in str(e) and "quota" in str(e).lower():
                    print(
                        f"{datetime.now()} 🚫 API 할당량 초과 (429 Error, 시도 {attempt + 1}/{max_retries},)"
                    )

                    # retry_delay 추출 시도
                    error_message = str(e)
                    retry_match = re.search(
                        r"retry in (\d+(?:\.\d+)?)", error_message, re.IGNORECASE
                    )

                    if retry_match:
                        retry_seconds = float(retry_match.group(1))
                        print(
                            f"{datetime.now()} ⏳ API 권장 대기 시간: {retry_seconds:.1f}초"
                        )
                    else:
                        # 에러 메시지에서 retry_delay 객체 추출 시도
                        retry_delay_match = re.search(
                            r"retry_delay\s*{\s*seconds:\s*(\d+)", error_message
                        )
                        if retry_delay_match:
                            retry_seconds = float(retry_delay_match.group(1))
                            print(
                                f"{datetime.now()} ⏳ API retry_delay: {retry_seconds}초"
                            )
                        else:
                            retry_seconds = 60  # 기본값
                            print(
                                f"{datetime.now()} ⏳ 기본 대기 시간 사용: {retry_seconds}초"
                            )

                    if attempt < max_retries - 1:
                        if on_retry_callback:
                            is_emergency = False
                            on_retry_callback(attempt + 1, max_retries)
                        print(f"{datetime.now()} {retry_seconds}초 후 재시도...")
                        await asyncio.sleep(retry_seconds)
                        continue
                    else:
                        print(f"{datetime.now()} ❌ API 요청 최종 실패 (할당량 초과)")
                        return None

                print(
                    f"{datetime.now()} ⚠️ 오류 발생 (시도 {attempt + 1}/{max_retries}): {str(e)}"
                )

                if on_error_callback:
                    on_error_callback(attempt + 1, max_retries, str(e))

                if attempt < max_retries - 1:
                    if on_retry_callback:
                        is_emergency = False
                        on_retry_callback(attempt + 1, max_retries)
                    wait_time = 2**attempt
                    await asyncio.sleep(wait_time)
                else:
                    print(f"{datetime.now()} ❌ API 요청 최종 실패")
                    return None

        return None

    @staticmethod
    async def call_api_and_parse_json(
        api_func: Callable[[], Coroutine],
        max_retries: int,
        timeout: int,
        is_emergency: bool,
        on_retry_callback: Optional[Callable[[int, int], None]] = None,
        on_timeout_callback: Optional[Callable[[int, int], None]] = None,
        on_error_callback: Optional[Callable[[int, int, str], None]] = None,
        response_validator: Optional[Callable[[Any], bool]] = None,
        max_parse_retries: int = 3,
    ) -> Optional[Any]:
        """
        API를 호출하고 JSON을 파싱하며 재시도 로직을 처리합니다.
        JSON 파싱이 실패하면 API를 다시 호출합니다.

        Args:
            api_func: 호출할 비동기 API 함수
            max_retries: 최대 API 재시도 횟수
            timeout: 요청 타임아웃 (초)
            is_emergency: 사용량 소진시 사용
            on_retry_callback: 재시도 시 호출될 콜백 함수 (API 호출 실패, 파싱 실패 모두 포함)
            on_timeout_callback: 타임아웃 시 호출될 콜백 함수
            on_error_callback: 오류 발생 시 호출될 콜백 함수
            response_validator: 파싱된 응답을 검증할 함수 (bool 반환)
            max_parse_retries: JSON 파싱 실패 시 API 재호출 최대 횟수

        Returns:
            파싱된 JSON 객체, 실패 시 None
        """
        # 전체 재시도 루프 (API 호출 + JSON 파싱)
        for parse_attempt in range(max_parse_retries):
            # print(f"{datetime.now()} 🔄 전체 시도 {parse_attempt + 1}/{max_parse_retries}")
            await asyncio.sleep(0.001)

            # API 호출
            response_text = await JSONRepairHandler.call_api_with_retry(
                api_func=api_func,
                max_retries=max_retries,
                timeout=timeout,
                is_emergency=is_emergency,
                on_retry_callback=on_retry_callback,
                on_timeout_callback=on_timeout_callback,
                on_error_callback=on_error_callback,
            )

            # API 호출 자체가 실패한 경우
            if response_text is None:
                print(
                    f"{datetime.now()} ❌ API 호출 실패 (전체 시도 {parse_attempt + 1}/{max_parse_retries})"
                )
                if parse_attempt < max_parse_retries - 1:
                    if on_retry_callback:
                        on_retry_callback(parse_attempt + 1, max_parse_retries)
                    wait_time = 2**parse_attempt
                    print(f"{datetime.now()} {wait_time}초 후 전체 재시도...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    print(f"{datetime.now()} ❌ 전체 시도 최종 실패 (API 호출 불가)")
                    return None

            # Markdown 정제
            response_text = JSONRepairHandler.clean_markdown(response_text)

            # JSON 파싱 (자동 복구 포함)
            parsed_json = await JSONRepairHandler.validate_and_parse(
                response_text, max_retries=3
            )

            # JSON 파싱 실패
            if parsed_json is None:
                print(
                    f"{datetime.now()} ❌ JSON 파싱 실패 (전체 시도 {parse_attempt + 1}/{max_parse_retries})"
                )
                print(f"응답 내용:\n{response_text}")

                if parse_attempt < max_parse_retries - 1:
                    if on_retry_callback:
                        on_retry_callback(parse_attempt + 1, max_parse_retries)
                    wait_time = 2**parse_attempt
                    print(
                        f"{datetime.now()} {wait_time}초 후 API 재호출 및 파싱 재시도..."
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    print(f"{datetime.now()} ❌ 전체 시도 최종 실패 (JSON 파싱 불가)")
                    return None

            # 응답 검증 (선택사항)
            if response_validator and not response_validator(parsed_json):
                print(
                    f"{datetime.now()} ⚠️ 응답 검증 실패 (전체 시도 {parse_attempt + 1}/{max_parse_retries})"
                )
                print(f"응답 내용:\n{response_text}")

                if parse_attempt < max_parse_retries - 1:
                    if on_retry_callback:
                        on_retry_callback(parse_attempt + 1, max_parse_retries)
                    wait_time = 2**parse_attempt
                    print(
                        f"{datetime.now()} {wait_time}초 후 API 재호출 및 검증 재시도..."
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    print(f"{datetime.now()} ❌ 전체 시도 최종 실패 (검증 실패)")
                    return None

            # 성공!
            print(f"{datetime.now()} ✅ JSON 파싱 및 검증 성공")
            return parsed_json

        return None
