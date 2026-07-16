import math
import logging
import asyncio
import threading
import pandas as pd
from json import loads
from os import environ
from requests import post
from random import randint
from typing import Any, Dict
from dotenv import load_dotenv
from timeit import default_timer
from dataclasses import dataclass
from supabase import create_client
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from discord_webhook_sender import DiscordWebhookSender
from improved_get_message import initialize_session_manager


class initVar:
    # 초기화 클래스: 프로그램의 기본 설정값과 상태를 관리함
    load_dotenv()
    DO_TEST = False  # 테스트 모드 여부

    printCount = 1000  # 1000회마다 카운트 출력
    countTimeList = []
    countTimeList.append(default_timer())  # 실행 시간 측정용
    countTimeList.append(default_timer())
    SEC = 1000000  # 까지만 표시(넘어서면 0부터)
    count = 0

    stream_status = {}
    highlight_chat = {}
    wait_make_highlight_chat = {}
    chat_user_index = defaultdict(list)

    supabase = create_client(
        environ["supabase_url"], environ["supabase_key"]
    )  # Supabase DB 클라이언트
    GOOGLE_API_KEY_LIST = environ["GOOGLE_API_KEY"].split(",")
    genai_cnt = randint(0, (len(GOOGLE_API_KEY_LIST) - 1) * 10 - 1)
    youtube_key_index = randint(0, 17 * 4 - 1)
    IMGBB_API_KEY_LIST = environ["IMGBB_API_KEY_LIST"].split(",")
    api_key_cnt = randint(0, len(IMGBB_API_KEY_LIST) - 1)

    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # httpx 로깅 수준 조정

    # 모든 로거의 레벨을 높이려면
    # logging.getLogger().setLevel(logging.WARNING)
    initialize_session_manager()

    print("start!")


_TABLE_LOCKS: Dict[str, asyncio.Lock] = {}
_TABLE_LOCKS_LOCK = threading.Lock()
_CURRENT_LOOP_ID = None


def get_table_lock(table_name: str) -> asyncio.Lock:

    global _CURRENT_LOOP_ID

    try:
        current_loop = asyncio.get_running_loop()
        current_loop_id = id(current_loop)
    except RuntimeError:
        raise RuntimeError("비동기 컨텍스트에서만 호출 가능")

    with _TABLE_LOCKS_LOCK:
        # 이벤트 루프가 바뀌었으면 모든 Lock 초기화
        if _CURRENT_LOOP_ID != current_loop_id:
            _TABLE_LOCKS.clear()
            _CURRENT_LOOP_ID = current_loop_id

        # Lock이 없으면 생성
        if table_name not in _TABLE_LOCKS:
            _TABLE_LOCKS[table_name] = asyncio.Lock()

        return _TABLE_LOCKS[table_name]


# 각 플랫폼의 아이콘 URL을 저장하는 데이터 클래스
@dataclass
class iconLinkData:

    chzzk_icon: str = environ["CHZZK_ICON"]
    afreeca_icon: str = environ["AFREECA_ICON"]
    soop_icon: str = environ["SOOP_ICON"]
    black_img: str = environ["BLACK_IMG"]
    youtube_icon: str = environ["YOUTUBE_ICON"]
    cafe_icon: str = environ["CAFE_ICON"]


# 오류 로깅 함수: Discord 웹훅을 통해 오류 메시지 전송
async def log_error(
    message, is_Do_test=False, webhook_url=environ.get("errorPostBotURL")
):
    await DiscordWebhookSender()._log_error(message, is_Do_test, webhook_url)

# 사용자 데이터 업데이트 함수
async def userDataVar(init: initVar):
    date_update = None
    
    try:
        # 데이터베이스에서 업데이트 정보 조회
        date_update = await asyncio.to_thread(
            lambda: init.supabase.table("date_update").select("*").execute()
        )

        # 응답 유효성 검증
        if not _is_valid_response(date_update):
            print(
                f"{datetime.now()} ERROR: 유효하지 않은 응답 - "
                f"data: {date_update.data if date_update else 'None'}"
            )
            return False

        update_data = date_update.data[0]

        # 단순 속성 설정
        _set_simple_attributes(init, update_data)

        # 비동기 작업 준비
        tasks = _prepare_async_tasks(init, update_data)

        # 모든 비동기 작업 실행
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        return True

    except Exception as e:
        error_str = str(e)

        ignorable_errors = [
            # 네트워크/프로토콜
            "Server disconnected",
            "EOF occurred in violation of protocol",
            "Received pseudo-header in trailer",
            "COMPRESSION_ERROR",
            "PROTOCOL_ERROR",
            "timed out",
            "None",

            # 5xx 서버 에러
            "Internal server error",
            "Error code 500",
            "Error code 502",
            "Error code 503",
            "Error code 504",
            "code': 5",
            "code\": 5",
            "JSON could not be generated",
            "Cloudflare",
        ]

        if any(err in error_str for err in ignorable_errors):
            return False

        error_details = f"Error in userDataVar: {error_str}"
        if hasattr(e, "response"):
            error_details += f"\nResponse: {e.response.text}"
        if date_update:
            error_details += f"\nLast date_update: {date_update}"

        await log_error(error_details[:500])
        print(f"{datetime.now()} {error_details}")
        return False



def _is_valid_response(response: Any) -> bool:
    """응답이 유효한지 검증합니다."""
    return (
        response is not None
        and hasattr(response, 'data')
        and response.data
        and isinstance(response.data, list)
        and len(response.data) > 0
    )


def _set_simple_attributes(init: initVar, update_data: Dict[str, Any]) -> None:
    """단순 속성들을 설정합니다."""
    simple_attributes = {
        'chat_json': 'chat_json',
        'is_vod_json': 'is_vod_json',
        'is_vod_chat_json': 'is_vod_chat_json',
        'is_use_description': 'is_use_description',
        'is_use_AI': 'is_use_AI',
        'is_hot_clip': 'is_hot_clip',
        'is_save_highlight_data': 'is_save_highlight_data',
        'is_state_control': 'is_state_control',
    }

    for init_attr, data_key in simple_attributes.items():
        setattr(init, init_attr, update_data.get(data_key))


def _prepare_async_tasks(init: initVar, update_data: Dict[str, Any]) -> list:
    """비동기로 실행할 작업들을 준비합니다."""
    tasks = []

    state_control = update_data.get("is_state_control", {})
    if isinstance(state_control, dict):
        if state_control.get("user_date"):
            tasks.append(load_user_state_data(init))
        if state_control.get("all_date"):
            tasks.append(DataBaseVars(init))
        if state_control.get("is_print_log"):
            tasks.append(print_log(init))
        if state_control.get("save_highlights_dict_cache"):
            tasks.append(save_highlights_dict_cache_allChannelID(init))

    highlight_data = update_data.get("is_save_highlight_data", {})
    if isinstance(highlight_data, dict):
        for channel_id, state in highlight_data.items():
            if state:
                tasks.append(save_highlight_data(init, channel_id))

    return tasks


## 사용자 상태 데이터 로드
async def load_user_state_data(init: initVar):
    userStateData = await asyncio.to_thread(
        lambda: init.supabase.table("userStateData").select("*").execute()
    )
    init.userStateData = make_list_to_dict(userStateData.data)
    init.userStateData.index = list(init.userStateData["discordURL"])
    build_chat_user_index(init)

    # 플래그 업데이트
    init.is_state_control["user_date"] = False
    await update_flag(init.supabase, "is_state_control", init.is_state_control)


def build_chat_user_index(init: initVar):
    index = defaultdict(list)

    for discordURL in init.userStateData.index:
        chat_json = init.userStateData.loc[discordURL, "chat_user_json"]
        if not isinstance(chat_json, dict):
            continue

        for channelID, user_list in chat_json.items():
            for name in user_list:
                index[(channelID, name)].append(discordURL)

    init.chat_user_index = index


# 비동기로 플래그 업데이트
async def update_flag(supabase, field, value):
    table_name = "date_update"
    lock = get_table_lock(table_name)
    async with lock:
        await safe_update(
            supabase,
            table_name,
            match={"idx": 0},
            data={field: value},
        )

def restore_highlights_dict_cache(title_data: pd.DataFrame) -> pd.DataFrame:
    from chat_analyzer import StreamHighlight
    """DB에서 불러온 highlights_dict_cache의 dict들을 StreamHighlight 객체로 복원"""
    if "highlights_dict_cache" not in title_data.columns:
        return title_data

    def restore_cell(cell):
        if not isinstance(cell, dict):
            return cell
        return {
            stream_id: [
                StreamHighlight.from_dict(h) if isinstance(h, dict) else h
                for h in highlights
            ]
            for stream_id, highlights in cell.items()
        }

    title_data["highlights_dict_cache"] = title_data["highlights_dict_cache"].apply(restore_cell)
    return title_data

## db 초기화 함수
async def DataBaseVars(init: initVar, is_start=False):

    while True:
        try:

            # 모든 테이블 이름을 리스트로 정의
            table_names = [
                "IDList",
                "titleData",
                "chatFilter",
                "chat_commands",
                "video_data",
                "hot_clip_data",
                "userStateData",
                "cafeData",
                "youtubeData",
            ]

            # 모든 테이블의 데이터를 비동기로 가져오기
            tasks = [fetch_data(init.supabase, name) for name in table_names]
            results = await asyncio.gather(*tasks)

            # 결과를 딕셔너리로 변환
            data_dict = {
                name: make_list_to_dict(result.data)
                for name, result in zip(table_names, results)
            }

            # init 객체에 데이터 할당
            for name, data in data_dict.items():
                setattr(init, name, data)

            # index 설정
            index_mappings = {
                "userStateData": "discordURL",
                "youtubeData": "YoutubeChannelID",
                "cafeData": "channelID",
            }

            for table_name, index_col in index_mappings.items():
                data = getattr(init, table_name)
                if not data.empty:  # 데이터가 있을 때만 인덱스 설정
                    data.index = list(data[index_col])
            build_chat_user_index(init)

            for attr in ["titleData"]:
                df = getattr(init, attr)
                if df is not None and not df.empty:
                    df = restore_highlights_dict_cache(df)
                    setattr(init, attr, df)

            def preprocess_by_platform(df, index_col):
                if df is None or df.empty:
                    return {}

                return {
                    platform: g.set_index(index_col, drop=False)
                    for platform, g in df.groupby("platform")
                }

            preprocess_targets = {
                "chatFilter": "uid",
                "IDList": "channelID",
                "titleData": "channelID",
                "chat_commands": "channelID",
                "hot_clip_data": "channelID",
                "video_data": "channelID",
            }

            for attr, index_col in preprocess_targets.items():
                df = getattr(init, attr)
                setattr(init, attr, preprocess_by_platform(df, index_col))

            init.platform_chat_server_last_close_time = {}
            init.platform_vod_last_chat_send_time = {}
            for platform in list(init.titleData):
                init.platform_chat_server_last_close_time[platform] = datetime.now().isoformat()
                init.platform_vod_last_chat_send_time[platform] = datetime.now().isoformat()
                
            if not is_start:
                init.is_state_control["all_date"] = False
                await update_flag(
                    init.supabase, "is_state_control", init.is_state_control
                )

            break

        except Exception as e:
            asyncio.create_task(log_error((f"Error in DataBaseVars: {str(e)}")))
            if init.count != 0:
                break
            await asyncio.sleep(0.1)


# 하이라이트 챗 캐시 데이터 저장 (메모리 관리), 프로그램 종료 직전에만 사용하기
async def save_highlight_data(init, channelID="all"):
    # StateManager에서 init과 하이라이트 인스턴스들 가져오기
    from shared_state import StateManager

    state_manager = StateManager.get_instance()

    if not init:
        return {"status": "error", "message": "시스템 초기화가 완료되지 않았습니다."}

    save_results = {"processed_channels": [], "total_highlights_saved": 0, "errors": []}
    try:
        # StateManager에서 하이라이트가 있는 챗 인스턴스들 가져오기
        instances_with_highlights = state_manager.get_chat_instances_with_highlights()

        print(
            f"{datetime.now()} 하이라이트 데이터가 있는 채널 {len(instances_with_highlights)}개 발견"
        )
        await change_field_state(
            init.supabase,
            "is_save_highlight_data",
            init.is_save_highlight_data,
            channelID,
            False,
        )

        # 각 인스턴스에 대해 highlight_processing 실행
        for instance_info in instances_with_highlights:
            try:
                channel_id = instance_info["channel_id"]
                channel_name = instance_info["channel_name"]
                platform = instance_info["platform"]
                highlights_count = instance_info["highlights_count"]
                chat_instance = instance_info["instance"]

                if channelID not in ["all"] and channelID != channel_id:
                    continue

                print(
                    f"{datetime.now()} [{platform}] {channel_name}: {highlights_count}개 하이라이트 저장 중..."
                )

                # highlight_processing 실행하여 하이라이트 저장
                await chat_instance.highlight_processing()

                save_results["processed_channels"].append(
                    {
                        "channel_id": channel_id,
                        "channel_name": channel_name,
                        "platform": platform,
                        "highlights_saved": highlights_count,
                    }
                )
                save_results["total_highlights_saved"] += highlights_count

                print(
                    f"{datetime.now()} [{platform}] {channel_name}: 하이라이트 저장 완료"
                )

            except Exception as channel_error:
                error_msg = f"채널 {instance_info.get('channel_name', 'Unknown')} 처리 중 오류: {str(channel_error)}"
                save_results["errors"].append(error_msg)
                print(f"{datetime.now()} {error_msg}")
                continue

        # 결과 반환
        if save_results["total_highlights_saved"] > 0:
            print(
                f"{datetime.now()} 하이라이트 챗 캐시 데이터 저장 완료: 총 {save_results['total_highlights_saved']}개 하이라이트 저장"
            )
            print(f"save_results:{save_results}")
        else:
            print(f"{datetime.now()} 저장할 하이라이트 데이터가 없습니다")

    except Exception as e:
        asyncio.create_task(log_error(f"하이라이트 데이터 저장 실패: {str(e)}"))


async def print_log(init):
    print(f"{datetime.now()} is_print_log", flush=True)
    init.is_state_control["is_print_log"] = False
    await asyncio.sleep(0.3)
    await update_flag(init.supabase, "is_state_control", init.is_state_control)


# db에서 데이터 가져오는 함수
async def fetch_data(supabase, date_name):
    return supabase.table(date_name).select("*").execute()


# 리스트를 딕셔너리로 변환하는 함수
def make_list_to_dict(data):
    if not data:
        return pd.DataFrame()

    # Dictionary comprehension을 사용하여 더 간단하게 표현
    return pd.DataFrame({key: [item[key] for item in data] for key in data[0].keys()})


# 카운트 증가 및 주기적 출력 함수
def fCount(init: initVar):
    if init.count >= init.SEC:
        init.count = 0

    if init.count % init.printCount == 0:
        printCount(init)
    init.count += 1


## 스레드 수행 시간 조절 함수(너무 빨리 돌지 않게 하기 위해)
async def fSleep(init: initVar):

    current_time = default_timer()
    init.countTimeList.append(current_time)

    # 리스트 길이 관리를 더 효율적으로 수정
    if len(init.countTimeList) > (init.printCount + 1):
        init.countTimeList.pop(0)

    # 시간 차이 계산 및 sleep 시간 결정
    time_diff = current_time - init.countTimeList[-2]
    sleepTime = max(0.01, min(1.00, 1.00 - time_diff))

    await asyncio.sleep(sleepTime)
    init.countTimeList[-1] += sleepTime


# 온라인 채널이 있는지 여부 확인하는 함수
def get_online_count(data):
    return sum(
        1
        for channel_id in data["live_state"].index
        if data.loc[channel_id, "live_state"] == "OPEN"
    )


# 각 플랫폼의 온라인 카운트 계산
def printCount(init: initVar):
    online_counts = {}
    for platform in list(init.titleData):
        online_counts[platform] = get_online_count(init.titleData[platform])

    # 모든 플랫폼이 오프라인인지 확인
    all_offline = not any(online_counts.values())

    # 시간 관련 데이터 계산
    current_time = datetime.now()
    count = str(init.count).zfill(len(str(init.SEC)))
    elapsed_time = round(init.countTimeList[-1] - init.countTimeList[0], 3)

    # 결과 출력
    status_prefix = "All offLine, " if all_offline else ""
    print(f"{status_prefix}{current_time} count {count} TIME {elapsed_time:.1f} SEC")


# HTML 엔티티를 일반 문자로 변환하는 함수
def subjectReplace(subject: str) -> str:
    replacements = {
        "&lt;": "<",
        "&gt;": ">",
        "&amp;": "&",
        "&quot;": '"',
        "&#035;": "#",
        "&#35;": "#",
        "&#039;": "'",
        "&#39;": "'",
    }

    for old, new in replacements.items():
        subject = subject.replace(old, new)

    return subject


# 트위치 API 요청용 헤더 생성 함수(트위치 관련 기능들은 전부 현재는 사용 안함)
def getTwitchHeaders():
    twitch_Client_ID = environ["twitch_Client_ID"]
    twitch_Client_secret = environ["twitch_Client_secret"]

    oauth_key = post(
        "https://id.twitch.tv/oauth2/token?client_id="
        + twitch_Client_ID
        + "&client_secret="
        + twitch_Client_secret
        + "&grant_type=client_credentials"
    )
    authorization = "Bearer " + loads(oauth_key.text)["access_token"]
    return {"client-id": twitch_Client_ID, "Authorization": authorization}  # 헤더 반환


# 기본 HTTP 요청 헤더 반환
def getDefaultHeaders():
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }


# 치지직 사이트 접속용 쿠키 반환
def getChzzkCookie():
    return {"NID_AUT": environ["NID_AUT"], "NID_SES": environ["NID_SES"]}


# 아프리카 사이트 접속용 쿠키 반환
def getAfreecaCookie():
    return {
        "AuthTicket": environ["AuthTicket"],
    }


# 카페 검색 파라미터 설정 함수
def cafe_params(cafeNum, page_num):
    return {
        "search.queryType": "lastArticle",
        "ad": "False",
        "search.clubid": str(cafeNum),
        "search.page": str(page_num),
    }


# ISO 시간을 UTC로 변환하는 함수 (한국시간 -9시간)
def changeUTCtime(time_str):
    time = datetime.fromisoformat(time_str)
    time -= timedelta(hours=9)
    return time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# 지정된 시간 이후인지 확인하는 함수 (기본 300초/5분)
# def if_after_time(time_str, sec=300):
#     try:
#         time = datetime.fromisoformat(time_str) + timedelta(seconds=sec)
#         return time <= datetime.now()
#     except Exception as e:
#         log_error(f"if_after_time error: {str(e)}")
#         return time <= datetime.now().astimezone()
    
def if_after_time(time_value, sec=300):
    try:
        if isinstance(time_value, (int, float)):
            time = datetime.fromtimestamp(time_value, tz=timezone.utc)
        else:
            time = datetime.fromisoformat(time_value)

        now = datetime.now(time.tzinfo) if time.tzinfo else datetime.now()
        return time + timedelta(seconds=sec) <= now

    except Exception as e:
        asyncio.create_task(
            log_error(f"if_after_time error: {time_value}, {str(e)}")
        )
        return False



# 방송 세션을 구분하는 고유 ID 생성
def get_stream_start_id(channel_id: str, start_time: str) -> str:
    # start_time을 기반으로 고유한 스트림 ID 생성
    timestamp = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
    return f"{channel_id}_{timestamp.strftime('%Y%m%d_%H%M%S')}"


# 스트림 ID에서 타임스탬프 추출
def get_timestamp_from_stream_id(stream_id: str) -> datetime:
    try:
        # stream_id 형식: "channelID_YYYYMMDD_HHMMSS"
        parts = stream_id.split("_")
        if len(parts) >= 3:
            date_part = parts[-2]  # YYYYMMDD
            time_part = parts[-1]  # HHMMSS
            time_str = f"{date_part}_{time_part}"
            return datetime.strptime(time_str, "%Y%m%d_%H%M%S")
        else:
            raise ValueError(f"Invalid stream_id format: {stream_id}")
    except (ValueError, IndexError) as e:
        raise ValueError(
            f"Cannot parse timestamp from stream_id '{stream_id}': {str(e)}"
        )


def format_time_for_comment(total_seconds: int, del_sec: int = 0) -> str:
    """초 단위 시간을 댓글용 HH:MM:SS 형식으로 변환"""
    try:
        # 오프셋 적용 (음수 방지)
        adjusted_seconds = max(0, total_seconds - del_sec)

        # 시:분:초로 변환
        hours, remainder = divmod(adjusted_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    except (ValueError, TypeError) as e:
        print(f"[FORMAT_DEBUG] 예외 발생: {str(e)}")
        print(
            f"[FORMAT_DEBUG] 입력값: total_seconds={total_seconds}, del_sec={del_sec}"
        )
        return "00:00:00"


# 두 스트림 ID 사이의 시간 차이를 초 단위로 계산
def calculate_stream_duration(stream_start_id: str, stream_end_id: str) -> float:
    try:
        start_time = get_timestamp_from_stream_id(stream_start_id)
        end_time = get_timestamp_from_stream_id(stream_end_id)
        return (end_time - start_time).total_seconds()
    except ValueError as e:
        print(f"{datetime.now()} 스트림 지속시간 계산 오류: {str(e)}")
        return 0.0


# 치지직 API URL 생성 함수
def chzzk_getLink(uid: str):
    return f"https://api.chzzk.naver.com/service/v2/channels/{uid}/live-detail"


# 아프리카 API URL 생성 함수
def afreeca_getLink(afreeca_id: str):
    return f"https://chapi.sooplive.co.kr/api/{afreeca_id}/station"


# 트위치 채널 상태 데이터 추출 함수
def twitch_getChannelOffStateData(offStateList, twitchID):
    try:
        for offState in offStateList:
            if offState["broadcaster_login"] == twitchID:
                return (
                    offState["is_live"],
                    offState["title"],
                    offState["thumbnail_url"],
                )
        return None, None, None
    except Exception as e:
        asyncio.create_task(log_error(f"error getChannelOffStateData twitch {str(e)}"))
        return None, None, None


# 치지직 채널 상태 데이터 추출 함수
def chzzk_getChannelOffStateData(stateData, chzzkID, profile_image=""):
    try:
        if stateData["channel"]["channelId"] == chzzkID:
            return (
                stateData["status"],
                stateData["liveTitle"],
                stateData["channel"]["channelImageUrl"],
            )
        return None, None, profile_image
    except Exception as e:
        asyncio.create_task(log_error(f"error getChannelOffStateData chzzk {str(e)}"))
        return None, None, profile_image


# 아프리카 채널 상태 데이터 추출 함수
def afreeca_getChannelOffStateData(stateData, afreeca_id, profile_image=""):
    try:
        if stateData["station"]["user_id"] == afreeca_id:
            live = int(stateData["broad"] is not None)
            title = stateData["broad"]["broad_title"] if live else None
            profile_image = stateData["profile_image"]
            if profile_image.startswith("//"):
                profile_image = f"https:{profile_image}"
            return live, title, profile_image
        return None, None, profile_image
    except Exception as e:
        asyncio.create_task(log_error(f"error getChannelOffStateData afreeca {str(e)}"))

async def safe_update(supabase, table_name: str, match: dict, data: dict, retry: int = 3) -> bool:
    if not data:
        return True  # 변경사항 없으면 네트워크 요청 자체를 하지 않음

    for i in range(retry):
        try:
            await asyncio.to_thread(
                lambda: (
                    supabase.table(table_name)
                    .update(data)
                    .match(match)
                    .execute()
                )
            )
            return True
        except Exception as e:
            if i == retry - 1:
                print(data)
                asyncio.create_task(log_error(f"Supabase update fail: {e}"))
            else:
                await asyncio.sleep(0.5 * (i + 1))
    return False

def sanitize_for_json(value):
    from chat_analyzer import StreamHighlight
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, StreamHighlight):
        return sanitize_for_json(value.to_dict())
    if isinstance(value, dict):
        return {k: sanitize_for_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_for_json(v) for v in value]
    if isinstance(value, set):
        return [sanitize_for_json(v) for v in value]
    return value

async def save_highlights_dict_cache_allChannelID(init: initVar):
    tasks = []
    for platform in list(init.titleData):
        for channelID in list(init.titleData[platform].index):
            tasks.append(
                save_airing_data(
                    init.supabase,
                    init.titleData[platform],
                    platform,
                    channelID,
                    updated_keys={"baseline_metrics", "highlights_dict_cache"},
                )
            )

    # 모든 저장 작업을 동시에 실행하고 완료까지 대기
    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        # 실패한 태스크 로깅
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                await log_error(
                    f"save_highlights_dict_cache: 태스크 {i} 실패: {result}"
                )

    # 모든 저장이 완료된 후에 플래그 업데이트
    init.is_state_control["save_highlights_dict_cache"] = False
    await update_flag(init.supabase, "is_state_control", init.is_state_control)

# 방송 정보 데이터 저장 함수
async def save_airing_data(
    supabase,
    titleData,
    platform: str,
    id_,
    updated_keys: set[str] = {
        "live_state", "title1", "title2", "chatChannelId",
        "oldChatChannelId", "state_update_time", "category",
        "baseline_metrics", "highlights_dict_cache"
    },
):
    table_name = "titleData"
    lock = get_table_lock(table_name)
    async with lock:
        try:
            data = {
                key: sanitize_for_json(titleData.loc[id_, key])
                for key in updated_keys
            }
        except KeyError as e:
            await log_error(
                f"save_airing_data KeyError: platform={platform}, id={id_}, key={e}"
            )
            return

        await safe_update(
            supabase,
            table_name,
            match={"channelID": id_, "platform": platform},
            data=data,
        )

# 프로필 이미지 url 저장 함수
async def save_profile_data(supabase, IDList, platform: str, id_):
    table_name = "IDList"
    lock = get_table_lock(table_name)
    async with lock:
        await safe_update(
            supabase,
            table_name,
            match={"channelID": id_, "platform": platform},
            data={"profile_image": IDList[platform].loc[id_, "profile_image"]},
        )
# 필드 데이터 상태 변경 함수
async def change_field_state(supabase, field, field_data, channel_id, field_state=True):
    table_name = "date_update"
    lock = get_table_lock(table_name)
    async with lock:
        field_data[channel_id] = field_state
        await safe_update(
            supabase,
            table_name,
            match={"idx": 0},
            data={field: field_data},
        )

# 비디오 데이터 저장 함수
async def save_video_data(supabase, video_data, id_, platform: str):
    table_name = "video_data"
    lock = get_table_lock(table_name)
    async with lock:
        await safe_update(
            supabase,
            table_name,
            match={"channelID": id_, "platform": platform},
            data={"VOD_json": video_data[platform].loc[id_, "VOD_json"]},
        )

# 카페 데이터 저장 함수
async def saveCafeData(
    supabase,
    cafeData,
    id_,
    updated_keys: set[str] = {"update_time", "cafe_json", "cafeNameDict"},
):
    table_name = "cafeData"
    lock = get_table_lock(table_name)
    async with lock:
        data = {
            key: int(cafeData.loc[id_, key])
            if key == "update_time"
            else cafeData.loc[id_, key]
            for key in updated_keys
        }
        await safe_update(
            supabase,
            table_name,
            match={"channelID": id_},
            data=data,
        )

# 유튜브 데이터 저장 함수
async def saveYoutubeData(
    supabase,
    youtubeData,
    youtubeChannelID: str,
    updated_keys: set[str] = {"videoCount", "video_count_check", "uploadTime", "oldVideo", "thumbnail_link"},
):
    int_keys = {"videoCount", "video_count_check"}
    table_name = "youtubeData"
    lock = get_table_lock(table_name)
    async with lock:
        data = {
            key: int(youtubeData.loc[youtubeChannelID, key])
            if key in int_keys
            else youtubeData.loc[youtubeChannelID, key]
            for key in updated_keys
        }
        await safe_update(
            supabase,
            table_name,
            match={"YoutubeChannelID": youtubeChannelID},
            data=data,
        )

# 유저 챗 데이터 저장 함수
async def save_user_chat_user_json(
    supabase,
    webhook_url: str,
    chat_user_json,
):
    table_name = "userStateData"
    lock = get_table_lock(table_name)
    async with lock:
        await safe_update(
            supabase,
            table_name,
            match={"discordURL": webhook_url},
            data={"chat_user_json": chat_user_json},
        )

# 보낸 클립 UID 저장 함수
async def save_sent_notifications(supabase, channel_id: str, hot_clip_data, platform: str):
    table_name = "hot_clip_data"
    lock = get_table_lock(table_name)
    async with lock:
        await safe_update(
            supabase,
            table_name,
            match={"channelID": channel_id, "platform": platform},
            data={
                "last_updated": datetime.now().isoformat(),
                "sent_clip_uids": hot_clip_data[platform].loc[channel_id, "sent_clip_uids"],
            },
        )

# 챗 명령어 데이터 저장 함수
async def save_chat_command_data(supabase, chat_command_data, id_: str, platform: str):
    table_name = "chat_commands"
    lock = get_table_lock(table_name)
    async with lock:
        await safe_update(
            supabase,
            table_name,
            match={"channelID": id_, "platform": platform},
            data={"chat_command": chat_command_data[platform].loc[id_, "chat_command"]},
        )

# 닉네임 필터 저장 함수
async def save_chatFilter_name(init, user_id: str, user_name: str, platform: str):
    table_name = "chatFilter"
    lock = get_table_lock(table_name)
    async with lock:
        init.chatFilter[platform].loc[user_id, "channelName"] = user_name
        await safe_update(
            init.supabase,
            table_name,
            match={"uid": user_id, "platform": platform},
            data={"channelName": user_name},
        )

# 닉네임 변경시 db 데이터 변경 및 사용자 설정 변경
async def change_nickname(init, user_id, nickname, platform: str):
    try:
        old_name = init.chatFilter[platform].loc[user_id, "channelName"]
        if nickname == old_name:
            return
         
        print(f"닉네임 변경 시도 {platform}:{old_name} -> {nickname}")
        channel_id_list = list(init.IDList[platform]["channelID"])
        for channel_id in channel_id_list:
            key = (channel_id, old_name)
            targets = init.chat_user_index.get(key, [])

            for discordURL in targets:
                chat_json = init.userStateData.loc[discordURL, "chat_user_json"]
                if not isinstance(chat_json, dict):
                    continue

                user_list = chat_json.get(channel_id)
                if not user_list:
                    continue

                while old_name in user_list:
                    idx = user_list.index(old_name)
                    user_list[idx] = nickname

                asyncio.create_task(
                    save_user_chat_user_json(init.supabase, discordURL, chat_json)
                )

            if targets:
                new_key = (channel_id, nickname)
                init.chat_user_index[new_key].extend(targets)
                if key in init.chat_user_index:
                    del init.chat_user_index[key]

        asyncio.create_task(
            log_error(f"닉네임 변경됨 {platform}:{old_name} -> {nickname}")
        )
        asyncio.create_task(
            save_chatFilter_name(init, user_id, nickname, platform=platform)
        )

    except Exception as e:
        asyncio.create_task(log_error(f"change_nickname, {platform}, {nickname} error: {e}"))
