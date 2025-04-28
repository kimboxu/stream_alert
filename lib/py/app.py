import os
import asyncio
import logging
from base import make_list_to_dict, log_error
import pandas as pd
from time import sleep
from requests import post
from typing import Dict, Any, List, Optional
from supabase import create_client, Client
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

# 로깅 설정
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)



def process_notifications(data: list) -> pd.DataFrame:
    """
    알림 데이터를 처리하여 DataFrame으로 변환합니다.
    문자열 비교를 위해 webhook_url을 문자열로 유지합니다.
    """
    if not data:
        return pd.DataFrame(columns=['webhook_url', 'settings'])
    
    # 데이터를 DataFrame으로 변환
    df = pd.DataFrame(data)
    
    # webhook_url이 숫자 형식이면 문자열로 변환 (필요한 경우)
    if 'webhook_url' in df.columns:
        df['webhook_url'] = df['webhook_url'].astype(str)
    
    # 디버깅을 위한 로깅 추가
    logger.info(f"데이터프레임 변환 결과: {len(df)} 행")
    if not df.empty and 'webhook_url' in df.columns:
        logger.info(f"webhook_url 데이터 유형: {df['webhook_url'].dtype}")
        for i, url in enumerate(df['webhook_url']):
            logger.info(f"webhook_url {i+1}: {url}")
    
    return df


@app.route("/")
def index():
    """메인 페이지를 렌더링합니다."""
    return render_template("index.html")


def normalize_webhook_url(webhook_url: str) -> str:
    """디스코드 웹훅 URL을 정규화하여 discord.com 형태로 변환합니다."""
    if webhook_url.startswith("https://discordapp.com/api/webhooks/"):
        return webhook_url.replace(
            "https://discordapp.com/api/webhooks/", "https://discord.com/api/webhooks/"
        )
    return webhook_url


@app.route("/save_all_notifications", methods=["POST"])
def save_all_notifications():
    """
    모든 알림 설정을 저장합니다.

    요청 형식:
    {
        "webhook_url": "https://discord.com/api/webhooks/...",
        "settings": { ... }
    }
    """
    try:
        data: Dict[str, Any] = request.json
        webhook_url: str = data.get("webhook_url", "")
        webhook_url = normalize_webhook_url(webhook_url)
        settings: Dict[str, Any] = data.get("settings", {})

        # Supabase 클라이언트 초기화
        url: str = os.environ["supabase_url"]
        key: str = os.environ["supabase_key"]
        supabase: Client = create_client(url, key)

        # 알림 설정 저장
        supabase.table("notifications").upsert(
            {"webhook_url": webhook_url, "settings": settings}
        ).execute()

        # 첫 메시지 전송 및 설정 저장
        firstMessage(webhook_url, settings, supabase)

        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error in save_all_notifications: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/get_notifications', methods=['POST'])
def get_notifications():
    """
    사용자의 알림 설정을 가져옵니다.
    
    요청 형식:
    {
        "webhook_url": "https://discord.com/api/webhooks/..."
    }
    """
    try:
        data: Dict[str, Any] = request.json
        webhook_url: str = data.get('webhook_url', '')
        webhook_url = normalize_webhook_url(webhook_url)
        
        # 로깅 추가
        logger.info(f"요청된 웹훅 URL: {webhook_url}")
        
        # Supabase 클라이언트 초기화
        url: str = os.environ['supabase_url']
        key: str = os.environ['supabase_key']
        supabase: Client = create_client(url, key)
        
        # 모든 알림 설정 가져오기
        notification_data = supabase.table("notifications").select("*").execute().data
        
        # 디버깅을 위한 로깅 추가
        logger.info(f"총 {len(notification_data)}개의 알림 설정을 찾았습니다.")
        for i, notification in enumerate(notification_data):
            logger.info(f"설정 {i+1}: webhook_url = {notification.get('webhook_url')}")
        
        # 알림 설정 처리
        notifications = process_notifications(notification_data)
        
        if notifications.empty:
            logger.info("알림 설정이 없습니다.")
            return jsonify({})

        # 정확히 일치하는 웹훅 URL 찾기
        matching_notification = notifications[notifications['webhook_url'] == webhook_url]
        
        # 일치 여부 로깅
        logger.info(f"일치하는 웹훅 URL 수: {len(matching_notification)}")
        
        if not matching_notification.empty:
            notification = matching_notification.iloc[0]
            logger.info(f"일치하는 설정 찾음: {notification['webhook_url']}")
            logger.info(f"설정 내용: {notification['settings']}")
            return jsonify({
                'webhook_url': notification['webhook_url'],
                'settings': notification['settings']
            })
        else:
            # 정확히 일치하는 것이 없으면 문자열 비교 시도
            for _, row in notifications.iterrows():
                db_webhook_url = str(row['webhook_url'])
                # URL을 정규화하여 비교
                if normalize_webhook_url(db_webhook_url) == webhook_url:
                    logger.info(f"문자열 비교로 일치하는 설정 찾음: {db_webhook_url}")
                    return jsonify({
                        'webhook_url': db_webhook_url,
                        'settings': row['settings']
                    })
            
            logger.info("일치하는 설정을 찾을 수 없습니다.")
            return jsonify({})
    except Exception as e:
        logger.error(f"Error in get_notifications: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

def get_streamer_list_by_setting(
    settings: Dict[str, Any], setting_key: str
) -> List[str]:
    """
    특정 설정 키에 대해 해당 설정이 활성화된 스트리머 목록을 반환합니다.
    """
    return [
        channelName
        for channelName in settings
        if settings[channelName].get(setting_key, False)
    ]


def get_streamer_map_from_cafe_data(cafe_data: pd.DataFrame) -> Dict[str, str]:
    """
    cafeData에서 스트리머 이름과 채널 ID 매핑을 생성합니다.
    """
    streamer_map = {}
    for idx, row in cafe_data.iterrows():
        if "channelName" in row and "channelID" in row:
            streamer_map[row["channelName"]] = row["channelID"]
    return streamer_map


def get_selected_chat_users(
    settings: Dict[str, Any], cafe_data: pd.DataFrame
) -> Dict[str, List[str]]:
    """
    선택된 채팅 사용자 목록을 채널 ID를 키로 하는 딕셔너리로 반환합니다.
    """
    result = {}
    streamer_map = get_streamer_map_from_cafe_data(cafe_data)

    for channel_name in settings:
        chat_users = settings[channel_name].get("chatUsers", {})
        selected_users = [
            user for user, is_selected in chat_users.items() if is_selected
        ]

        if channel_name in streamer_map and selected_users:
            channel_id = streamer_map[channel_name]
            result[channel_id] = selected_users

    return result


def get_selected_cafe_users(
    settings: Dict[str, Any], cafe_data: pd.DataFrame
) -> Dict[str, List[str]]:
    """
    선택된 카페 사용자 목록을 채널 ID를 키로 하는 딕셔너리로 반환합니다.
    """
    result = {}
    streamer_map = get_streamer_map_from_cafe_data(cafe_data)

    for channel_name in settings:
        cafe_users = settings[channel_name].get("cafeList", {})
        selected_users = [
            user for user, is_selected in cafe_users.items() if is_selected
        ]

        if channel_name in streamer_map and selected_users:
            channel_id = streamer_map[channel_name]
            result[channel_id] = selected_users

    return result


def get_selected_youtube_channels(
    settings: Dict[str, Any], cafe_data: pd.DataFrame
) -> Dict[str, List[str]]:
    """
    선택된 유튜브 채널 목록을 채널 ID를 키로 하는 딕셔너리로 반환합니다.
    """
    result = {}
    streamer_map = get_streamer_map_from_cafe_data(cafe_data)

    for channel_name in settings:
        youtube_channels = settings[channel_name].get("channelList", {})
        selected_channels = [
            channel for channel, is_selected in youtube_channels.items() if is_selected
        ]

        if channel_name in streamer_map and selected_channels:
            channel_id = streamer_map[channel_name]
            result[channel_id] = selected_channels

    return result


def get_selected_vod_channels(
    settings: Dict[str, Any], cafe_data: pd.DataFrame
) -> Dict[str, List[str]]:
    """
    선택된 VOD 채널 목록을 채널 ID를 키로 하는 딕셔너리로 반환합니다.
    """
    result = {}
    streamer_map = get_streamer_map_from_cafe_data(cafe_data)

    for channel_name in settings:
        is_vod_selected = settings[channel_name].get("VOD", False)

        if is_vod_selected and channel_name in streamer_map:
            channel_id = streamer_map[channel_name]
            result[channel_id] = [channel_name]  # 채널 이름을 값으로 사용

    return result


def format_list_to_string(
    items: List[str], default_msg: str = "", separator: str = ", "
) -> str:
    """
    리스트를 문자열로 변환합니다. 리스트가 비어있으면 기본 메시지를 반환합니다.
    """
    if not items:
        return default_msg
    return separator.join(items)


def format_dict_with_defaults(
    data: Dict[str, List[str]], cafe_data: pd.DataFrame, default_msg: str = ""
) -> Dict[str, str]:
    """
    딕셔너리의 값 리스트를 문자열로 변환합니다. 키가 없거나 값이 비어있으면 기본 메시지를 설정합니다.
    """
    result = {}
    channel_ids = set()

    # cafe_data에서 모든 채널 ID 추출
    for idx, row in cafe_data.iterrows():
        if "channelID" in row:
            channel_ids.add(row["channelID"])

    for channel_id in channel_ids:
        if channel_id in data and data[channel_id]:
            result[channel_id] = ", ".join(data[channel_id])
        else:
            result[channel_id] = default_msg

    return result


def send_discord_message(webhook_url: str, content: Dict[str, Any]) -> bool:
    """
    디스코드 웹훅을 통해 메시지를 전송합니다.
    """
    try:
        post(webhook_url, json=content, timeout=10)
        return True
    except Exception as e:
        logger.error(f"Discord webhook 전송 실패: {str(e)}")
        return False


def postSeting(
    webhook_url: str, settings: Dict[str, Any], cafe_data: pd.DataFrame, msg: str
) -> None:
    """
    사용자의 알림 설정 상태를 디스코드로 전송합니다.
    """
    # 스트리머 이름-채널 ID 매핑 생성
    streamer_map = get_streamer_map_from_cafe_data(cafe_data)

    # 채팅 및 카페 사용자 딕셔너리 생성
    chat_users_dict = get_selected_chat_users(settings, cafe_data)
    cafe_users_dict = get_selected_cafe_users(settings, cafe_data)

    # 유튜브 및 VOD 채널 딕셔너리 생성
    youtube_channels_dict = get_selected_youtube_channels(settings, cafe_data)
    vod_channels_dict = get_selected_vod_channels(settings, cafe_data)

    # 형식화된 딕셔너리 생성
    formatted_chat_users = format_dict_with_defaults(
        chat_users_dict, cafe_data, default_msg="없음"
    )
    formatted_cafe_users = format_dict_with_defaults(
        cafe_users_dict, cafe_data, default_msg="없음"
    )

    # 초기 메시지 전송
    initial_message = {
        "content": msg,
        "username": "개발자 알림",
        "avatar_url": "https://cdn.discordapp.com/attachments/1101488061713502288/1256215353747312692/28148904654ea963.jpg?ex=66849277&is=668340f7&hm=bdac000e72347a141a11f502da9f7ee9bf1881d0e8fb0fc9ecd8712ca3410da4&",
    }
    send_discord_message(webhook_url, initial_message)
    sleep(0.2)

    # 각 스트리머별 알림 설정 메시지 전송
    check_post = 0
    for channel_name in settings:
        channel_id = streamer_map.get(channel_name)

        # 방송 관련 알림 목록
        broadcast_notifications = []
        if settings[channel_name].get("startNotification", False):
            broadcast_notifications.append("방송 시작")
        if settings[channel_name].get("titleChangeNotification", False):
            broadcast_notifications.append("방송 제목 변경")
        if settings[channel_name].get("endNotification", False):
            broadcast_notifications.append("방송 종료")
        if settings[channel_name].get("VOD", False):
            broadcast_notifications.append("치지직 VOD")

        # 유튜브 채널 목록
        youtube_channels = []
        for channel, is_selected in (
            settings[channel_name].get("channelList", {}).items()
        ):
            if is_selected:
                youtube_channels.append(channel)

        # 알림 목록 형식화
        broadcast_text = format_list_to_string(broadcast_notifications, default_msg="없음")
        youtube_text = format_list_to_string(youtube_channels, default_msg="없음")

        # 알림 섹션 구성
        notification_sections = []
        if broadcast_text != "없음":
            notification_sections.append(f"* **방송**\n\t- {broadcast_text}")
        if youtube_text != "없음":
            notification_sections.append(f"* **유튜브**\n\t- {youtube_text}")

        notification_text = format_list_to_string(notification_sections, separator="\n")

        # 임베드 필드 구성
        fields = []
        if notification_sections:
            fields.append({"name": "알림 유형", "value": notification_text})

        # 채팅 알림 필드 추가
        if (
            channel_id
            and channel_id in formatted_chat_users
            and formatted_chat_users[channel_id] != "없음"
        ):
            fields.append(
                {"name": "채팅 알림 멤버", "value": formatted_chat_users[channel_id]}
            )

        # 카페 알림 필드 추가
        if (
            channel_id
            and channel_id in formatted_cafe_users
            and formatted_cafe_users[channel_id] != "없음"
        ):
            cafe_name = "카페"
            try:
                cafe_idx = cafe_data[cafe_data["channelID"] == channel_id].index[0]
                cafe_name = cafe_data.loc[cafe_idx, "cafeName"]
            except:
                pass

            fields.append(
                {
                    "name": f"{cafe_name} 카페 알림 멤버",
                    "value": formatted_cafe_users[channel_id],
                }
            )

        # 필드가 있는 경우에만 메시지 전송
        if fields:
            embed_message = {
                "username": "개발자 알림",
                "avatar_url": "https://cdn.discordapp.com/attachments/1101488061713502288/1256215353747312692/28148904654ea963.jpg?ex=66849277&is=668340f7&hm=bdac000e72347a141a11f502da9f7ee9bf1881d0e8fb0fc9ecd8712ca3410da4&",
                "embeds": [
                    {"color": 0, "title": f"{channel_name} 알림 설정", "fields": fields}
                ],
            }
            send_discord_message(webhook_url, embed_message)
            check_post = 1

    # 선택된 항목이 없는 경우 안내 메시지 전송
    if not check_post:
        guide_message = {
            "content": "체크된 항목이 없어서 알림을 받을 항목이 없습니다.\n원하는 스트리머의 프로필 이미지를 클릭해서 알림을 받을 항목들을 체크해 주세요.",
            "username": "개발자 알림",
            "avatar_url": "https://cdn.discordapp.com/attachments/1101488061713502288/1256215353747312692/28148904654ea963.jpg?ex=66849277&is=668340f7&hm=bdac000e72347a141a11f502da9f7ee9bf1881d0e8fb0fc9ecd8712ca3410da4&",
        }
        send_discord_message(webhook_url, guide_message)


def saveURLData(
    supabase: Client,
    webhook_url: str,
    settings: Dict[str, Any],
    cafe_data: pd.DataFrame,
) -> None:
    """
    사용자의 URL 관련 데이터를 저장합니다.
    """
    try:
        # 기본 알림 설정 추출
        online_list = get_streamer_list_by_setting(settings, "startNotification")
        title_change_list = get_streamer_list_by_setting(
            settings, "titleChangeNotification"
        )
        offline_list = get_streamer_list_by_setting(settings, "endNotification")

        # 채팅, 카페, 유튜브, VOD 설정 추출
        chat_users_dict = get_selected_chat_users(settings, cafe_data)
        cafe_users_dict = get_selected_cafe_users(settings, cafe_data)
        youtube_channels_dict = get_selected_youtube_channels(settings, cafe_data)
        vod_channels_dict = get_selected_vod_channels(settings, cafe_data)

        # 문자열 형식으로 변환
        online_str = format_list_to_string(online_list)
        title_change_str = format_list_to_string(title_change_list)
        offline_str = format_list_to_string(offline_list)

        # Supabase에 데이터 저장
        supabase.table("userStateData").upsert(
            {
                "discordURL": webhook_url,
                "뱅온 알림": online_str,
                "방제 변경 알림": title_change_str,
                "방종 알림": offline_str,
                "유튜브 알림": youtube_channels_dict,  # 딕셔너리 형태로 저장
                "cafe_user_json": cafe_users_dict,
                "chat_user_json": chat_users_dict,
                "치지직 VOD": vod_channels_dict,  # 딕셔너리 형태로 저장
            }
        ).execute()

        # 업데이트 날짜 갱신
        supabase.table("date_update").upsert({"idx": 0, "user_date": True}).execute()

    except Exception as e:
        logger.error(f"URL 데이터 저장 중 오류 발생: {str(e)}", exc_info=True)
        asyncio.create_task(log_error(f"error saving URL {e}"))


def extract_discord_urls(data_list) -> List[str]:
    """
    데이터 리스트에서 Discord URL을 추출합니다.
    """
    discord_urls = []
    for item in data_list.data:
        if "discordURL" in item:
            discord_urls.append(item["discordURL"])
    return discord_urls


def firstMessage(webhook_url: str, settings: Dict[str, Any], supabase: Client) -> None:
    """
    설정 저장 후 첫 메시지를 전송합니다.
    """
    # 데이터 업데이트 상태 확인
    is_data_updated = (
        supabase.table("date_update").select("*").execute().data[0]["user_date"]
    )

    # 사용자 상태 데이터 가져오기
    user_state_data = supabase.table("userStateData").select("*").execute()
    discord_url_list = list(make_list_to_dict(user_state_data.data)["discordURL"])

    # 카페 데이터 가져오기
    cafe_data_response = supabase.table("cafeData").select("*").execute()
    cafe_data = make_list_to_dict(cafe_data_response.data)
    cafe_data.index = list(cafe_data["channelName"])

    # 개발자 웹훅 URL 가져오기
    developer_webhook_url = os.environ["developerWebhookURL"]

    # 새 URL인지 또는 기존 URL인지 확인하여 메시지 설정
    if webhook_url in discord_url_list:
        msg = "디스코드 봇 설정이 수정되었습니다.\n"
        log_msg = f"new seting url {webhook_url}"
    else:
        msg = "디스코드 봇과 정상적으로 연결되었습니다.\n"
        log_msg = f"new url {webhook_url}"

    # 로그 전송
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(
        log_error(log_msg, webhook_url=developer_webhook_url)
    )
    loop.close()

    # 사용자에게 설정 상태 전송
    postSeting(webhook_url, settings, cafe_data, msg)

    # URL 데이터 저장 (실패 시 재시도)
    try:
        saveURLData(supabase, webhook_url, settings, cafe_data)
    except Exception as e:
        logger.error(f"URL 데이터 첫 번째 저장 시도 실패: {str(e)}", exc_info=True)
        try:
            saveURLData(supabase, webhook_url, settings, cafe_data)
        except Exception as e:
            logger.error(
                f"URL 데이터 두 번째 저장 시도도 실패: {str(e)}", exc_info=True
            )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7777, debug=False)
