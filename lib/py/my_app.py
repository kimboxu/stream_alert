
from os import environ
from flask import Flask, request, jsonify, render_template, g
from base import make_list_to_dict
from flask_cors import CORS
import asyncio
from json import loads, dumps
from supabase import create_client
from dotenv import load_dotenv
from datetime import datetime, timezone
import pandas as pd
from firebase_admin import credentials, messaging
from apscheduler.schedulers.background import BackgroundScheduler
import atexit

import time
from notification_service import (
    init_notification_system, 
    initialize_firebase,
    cached_send_push_notification,
    notification_cache,
    cleanup_all_invalid_tokens,
    clear_notification_cache ,
    get_supabase_client 
)

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.notification_cache = None
CORS(app)  # 크로스 오리진 요청 허용

def init_background_tasks():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    supabase = create_client(environ["supabase_url"], environ["supabase_key"])
    userStateData = supabase.table("userStateData").select("*").execute()
    userStateData = make_list_to_dict(userStateData.data)
    userStateData.index = userStateData["discordURL"]
    loop.close()
    return userStateData

def save_user_data(discordWebhooksURL, username):
    supabase = create_client(environ["supabase_url"], environ["supabase_key"])
    supabase.table("userStateData").upsert(
        {
            "discordURL": discordWebhooksURL,
            "username": username,
        }
    ).execute()

def normalize_discord_webhook_url(webhook_url: str) -> str:
    if webhook_url is None:
        return None
    return webhook_url.replace(
        "https://discordapp.com/api/webhooks/", "https://discord.com/api/webhooks/"
    )

@app.before_request
def initialize_app():
    app.userStateData = init_background_tasks()

@app.route("/", methods=["GET"])
def index():
    return jsonify({"message": "서버가 정상적으로 실행 중입니다."})

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return jsonify({"message": "로그인 페이지입니다. POST로 요청해주세요."})

    # JSON 데이터 처리
    if request.is_json:
        data = request.get_json()
    else:
        # form-data 처리
        data = request.form

    username = data.get("username")
    discordWebhooksURL = normalize_discord_webhook_url(data.get("discordWebhooksURL"))

    if discordWebhooksURL in app.userStateData.index:
        db_username = app.userStateData.loc[discordWebhooksURL, "username"]
        check_have_id = True
    else:
        check_have_id = False

    # 로그인 정보 출력 (디버깅용)
    print(f"로그인 시도: 사용자명: {username}, 디스코드 웹훅 URL: {discordWebhooksURL}")

    # 인증 로직
    if check_have_id and db_username == username:
        # 사용자 알림 설정 조회
        user_data = (
            app.userStateData.loc[discordWebhooksURL].to_dict()
            if isinstance(app.userStateData.loc[discordWebhooksURL], pd.Series)
            else app.userStateData.loc[discordWebhooksURL]
        )

        # 기본 응답 데이터
        response_data = {
            "status": "success",
            "message": "로그인 성공",
            "notification_settings": {
                "뱅온 알림": user_data.get("뱅온 알림", ""),
                "방제 변경 알림": user_data.get("방제 변경 알림", ""),
                "방종 알림": user_data.get("방종 알림", ""),
                "유튜브 알림": user_data.get("유튜브 알림", ""),
                "cafe_user_json": user_data.get("cafe_user_json", {}),
            },
        }
        return jsonify(response_data)
    else:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "사용자명 또는 디스코드 웹훅 URL이 잘못되었습니다",
                }
            ),
            401,
        )

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return jsonify({"message": "회원가입 페이지입니다. POST로 요청해주세요."})

    # JSON 데이터 처리
    if request.is_json:
        data = request.get_json()
    else:
        # form-data 처리
        data = request.form

    username = data.get("username")
    discordWebhooksURL = normalize_discord_webhook_url(data.get("discordWebhooksURL"))

    if discordWebhooksURL in app.userStateData.index:
        check_have_id = "have_URL"
    elif not discordWebhooksURL.startswith(("https://discord.com/api/webhooks/")):
        check_have_id = "not_discord_URL"
    elif discordWebhooksURL.startswith(("https://discord.com/api/webhooks/")):
        check_have_id = "OK"
    else:
        check_have_id = "fail"

    # 로그인 정보 출력 (디버깅용)
    print(
        f"회원가입 시도: 사용자명: {username}, 디스코드 웹훅 URL: {discordWebhooksURL}"
    )
    print(check_have_id)
    # 인증 로직
    if check_have_id == "OK":
        # DB에 유저 추가 하는 기능 함수 추가하기
        save_user_data(discordWebhooksURL, username)
        return jsonify({"status": "success", "message": "회원가입 성공"})
    elif check_have_id == "have_URL":
        return (
            jsonify(
                {"status": "error", "message": "디스코드 웹훅 URL이 이미 있습니다"}
            ),
            401,
        )
    elif check_have_id == "not_discord_URL":
        return (
            jsonify(
                {"status": "error", "message": "디스코드 웹훅 URL이 잘못되었습니다"}
            ),
            401,
        )
    else:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "사용자명 또는 디스코드 웹훅 URL이 잘못되었습니다",
                }
            ),
            401,
        )

@app.route("/get_user_settings", methods=["GET"])
def get_user_settings():
    discordWebhooksURL = request.args.get("discordWebhooksURL")
    username = request.args.get("username")

    if not discordWebhooksURL or not username:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "디스코드 웹훅 URL과 사용자명이 필요합니다",
                }
            ),
            400,
        )

    # 사용자 인증 확인
    if discordWebhooksURL in app.userStateData.index:
        db_username = app.userStateData.loc[discordWebhooksURL, "username"]
        if db_username != username:
            return jsonify({"status": "error", "message": "인증 실패"}), 401
    else:
        return jsonify({"status": "error", "message": "사용자를 찾을 수 없습니다"}), 404

    # Supabase에서 사용자 설정 가져오기
    supabase = create_client(environ["supabase_url"], environ["supabase_key"])
    result = (
        supabase.table("userStateData")
        .select("*")
        .eq("discordURL", discordWebhooksURL)
        .execute()
    )

    if not result.data:
        return jsonify({"status": "error", "message": "설정을 찾을 수 없습니다"}), 404

    user_data = result.data[0]

    # 알림 설정 정보 추출
    settings = {
        "뱅온 알림": user_data.get("뱅온 알림", ""),
        "방제 변경 알림": user_data.get("방제 변경 알림", ""),
        "방종 알림": user_data.get("방종 알림", ""),
        "유튜브 알림": user_data.get("유튜브 알림", ""),
        "치지직 VOD": user_data.get("치지직 VOD", ""),
        "cafe_user_json": user_data.get("cafe_user_json", "{}"),
        "chat_user_json": user_data.get("chat_user_json", "{}"),
    }
    settings["cafe_user_json"] = str(settings["cafe_user_json"])
    settings["chat_user_json"] = str(settings["chat_user_json"])

    return jsonify({"status": "success", "settings": settings})

@app.route("/save_user_settings", methods=["POST"])
def save_user_settings():
    # JSON 데이터 처리
    if request.is_json:
        data = request.get_json()
    else:
        # form-data 처리
        data = request.form

    discordWebhooksURL = data.get("discordWebhooksURL")
    username = data.get("username")

    if not discordWebhooksURL or not username:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "디스코드 웹훅 URL과 사용자명이 필요합니다",
                }
            ),
            400,
        )

    # 사용자 인증 확인
    if discordWebhooksURL in app.userStateData.index:
        db_username = app.userStateData.loc[discordWebhooksURL, "username"]
        if db_username != username:
            return jsonify({"status": "error", "message": "인증 실패"}), 401
    else:
        return jsonify({"status": "error", "message": "사용자를 찾을 수 없습니다"}), 404

    # 업데이트할 설정 데이터 추출
    update_data = {"discordURL": discordWebhooksURL, "username": username}

    # 선택적 설정 필드 추가
    for field in [
        "뱅온 알림",
        "방제 변경 알림",
        "방종 알림",
        "유튜브 알림",
        "치지직 VOD",
        "cafe_user_json",
        "chat_user_json",
    ]:
        if field in data:
            update_data[field] = data.get(field)

    update_data["유튜브 알림"] = loads(update_data["유튜브 알림"].replace('"', '"'))
    update_data["치지직 VOD"] = loads(update_data["치지직 VOD"].replace('"', '"'))
    update_data["cafe_user_json"] = loads(
        update_data["cafe_user_json"].replace('"', '"')
    )
    update_data["chat_user_json"] = loads(
        update_data["chat_user_json"].replace('"', '"')
    )

    # Supabase에 설정 업데이트
    supabase = create_client(environ["supabase_url"], environ["supabase_key"])
    result = supabase.table("userStateData").upsert(update_data).execute()
    update_result = supabase.table("date_update").upsert({"idx": 0, "user_date": True}).execute()

    # 캐시 무효화
    notification_cache.invalidate(discordWebhooksURL)

    return jsonify({"status": "success", "message": "설정이 저장되었습니다"})

@app.route("/update_username", methods=["POST"])
def update_username():
    # JSON 데이터 처리
    if request.is_json:
        data = request.get_json()
    else:
        # form-data 처리
        data = request.form

    old_username = data.get("oldUsername")
    discord_webhooks_url = normalize_discord_webhook_url(data.get("discordWebhooksURL"))
    new_username = data.get("newUsername")

    if not old_username or not discord_webhooks_url or not new_username:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "필수 정보가 누락되었습니다",
                }
            ),
            400,
        )

    # 사용자 확인
    if discord_webhooks_url in app.userStateData.index:
        db_username = app.userStateData.loc[discord_webhooks_url, "username"]
        if db_username != old_username:
            return jsonify({"status": "error", "message": "인증 실패"}), 401
    else:
        return jsonify({"status": "error", "message": "사용자를 찾을 수 없습니다"}), 404

    try:
        # 사용자 이름 업데이트
        supabase = create_client(environ["supabase_url"], environ["supabase_key"])
        supabase.table("userStateData").update({"username": new_username}).eq(
            "discordURL", discord_webhooks_url
        ).execute()

        # 앱 객체의 캐시도 업데이트
        app.userStateData.loc[discord_webhooks_url, "username"] = new_username

        return jsonify({"status": "success", "message": "사용자 이름이 변경되었습니다"})
    except Exception as e:
        print(f"사용자 이름 변경 중 오류: {e}")
        return (
            jsonify(
                {"status": "error", "message": f"사용자 이름 변경 중 오류 발생: {str(e)}"}
            ),
            500,
        )
    
@app.route("/get_streamers", methods=["GET"])
def get_streamers():
    try:
        # Supabase 연결
        supabase = create_client(environ["supabase_url"], environ["supabase_key"])

        # 아프리카TV 스트리머 정보 가져오기
        afreecaIDList = supabase.table("afreecaIDList").select("*").execute()

        # 치지직 스트리머 정보 가져오기
        chzzkIDList = supabase.table("chzzkIDList").select("*").execute()

        # 카페 정보 가져오기
        cafeData = supabase.table("cafeData").select("*").execute()
        chzzk_video = supabase.table("chzzk_video").select("*").execute()
        youtubeData = supabase.table("youtubeData").select("*").execute()
        chzzk_chatFilter = supabase.table("chzzk_chatFilter").select("*").execute()
        afreeca_chatFilter = supabase.table("afreeca_chatFilter").select("*").execute()

        afreecaIDList = afreecaIDList.data
        chzzkIDList = chzzkIDList.data
        cafeData = cafeData.data
        chzzk_video = chzzk_video.data
        youtubeData = youtubeData.data
        chzzk_chatFilter = chzzk_chatFilter.data
        afreeca_chatFilter = afreeca_chatFilter.data

        return jsonify(
            {
                "status": "success",
                "afreecaStreamers": afreecaIDList,
                "chzzkStreamers": chzzkIDList,
                "cafeStreamers": cafeData,
                "chzzkVideoStreamers": chzzk_video,
                "youtubeStreamers": youtubeData,
                "chzzkChatFilter": chzzk_chatFilter,
                "afreecaChatFilter": afreeca_chatFilter,
            }
        )

    except Exception as e:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": f"스트리머 정보를 가져오는데 실패했습니다: {str(e)}",
                }
            ),
            500,
        )

# FCM 토큰 등록 엔드포인트
@app.route("/register_fcm_token", methods=["POST"])
def register_fcm_token():
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form

    username = data.get("username")
    discord_webhook_url = normalize_discord_webhook_url(data.get("discordWebhooksURL"))
    fcm_token = data.get("fcm_token")

    if not username or not discord_webhook_url or not fcm_token:
        return (
            jsonify({"status": "error", "message": "필수 정보가 누락되었습니다"}),
            400,
        )

    try:
        # Supabase에 FCM 토큰 저장
        supabase = get_supabase_client()

        # 기존 사용자 확인
        result = (
            supabase.table("userStateData")
            .select("*")
            .eq("discordURL", discord_webhook_url)
            .execute()
        )

        if not result.data:
            return (
                jsonify({"status": "error", "message": "사용자를 찾을 수 없습니다"}),
                404,
            )

        # 사용자 데이터 가져오기
        user_data = result.data[0]

        # 기존 토큰 목록 가져오기 (JSON 배열로 저장)
        existing_tokens = user_data.get("fcm_tokens", [])
        
        # 데이터베이스에서 JSON 배열로 저장되지 않은 경우 변환
        if not isinstance(existing_tokens, list):
            try:
                if isinstance(existing_tokens, str) and existing_tokens:
                    # 문자열로 저장된 경우 파싱 시도
                    existing_tokens = [t.strip() for t in existing_tokens.split(",") if t.strip()]
                else:
                    existing_tokens = []
            except Exception:
                existing_tokens = []
        
        # 중복 방지
        if fcm_token not in existing_tokens:
            existing_tokens.append(fcm_token)

        # 업데이트
        update_data = {
            "fcm_tokens": existing_tokens,  # JSON 배열로 저장
            "last_token_update": datetime.now().isoformat(),
        }

        supabase.table("userStateData").update(update_data).eq(
            "discordURL", discord_webhook_url
        ).execute()
        
        # 캐시 무효화
        notification_cache.invalidate(discord_webhook_url)

        return jsonify({"status": "success", "message": "FCM 토큰이 등록되었습니다"})

    except Exception as e:
        print(f"FCM 토큰 등록 중 오류: {e}")
        return (
            jsonify(
                {"status": "error", "message": f"토큰 등록 중 오류 발생: {str(e)}"}
            ),
            500,
        )
# 유효하지 않은 토큰 제거 함수
async def cleanup_invalid_fcm_tokens(user_data: dict) -> tuple[bool, int]:
    """
    유효하지 않은 FCM 토큰을 식별하고 제거합니다.
    
    Args:
        user_data: 사용자 정보를 담고 있는 딕셔너리
    
    Returns:
        tuple[bool, int]: (변경 여부, 제거된 토큰 수)
    """
    try:
        # JSON 배열로 저장된 FCM 토큰 가져오기
        fcm_tokens = user_data.get("fcm_tokens", [])
        
        # 데이터베이스에서 JSON 배열로 저장되지 않은 경우 변환
        if not isinstance(fcm_tokens, list):
            try:
                if isinstance(fcm_tokens, str) and fcm_tokens:
                    # 문자열로 저장된 경우 파싱 시도
                    fcm_tokens = [t.strip() for t in fcm_tokens.split(",") if t.strip()]
                else:
                    fcm_tokens = []
            except Exception:
                fcm_tokens = []
                
        if not fcm_tokens:
            return False, 0  # 토큰이 없으면 처리할 것이 없음
            
        original_count = len(fcm_tokens)
        
        if original_count == 0:
            return False, 0
            
        # 유효하지 않은 토큰 식별
        invalid_tokens = []
        
        # Firebase Admin SDK는 bulk validation API를 제공하지 않으므로
        # 개별적으로 각 토큰 검증
        for token in fcm_tokens:
            if not token.strip():  # 빈 토큰 제거
                invalid_tokens.append(token)
                continue
                
            try:
                # 테스트 메시지 생성
                message = messaging.Message(
                    data={'validate': 'true'},
                    token=token
                )
                # dry_run=True로 설정하여 실제로 메시지를 보내지 않고 유효성만 확인
                messaging.send(message, dry_run=True)
            except Exception as e:
                # 알 수 없는 오류 로깅
                print(f"토큰 검증 중 오류: {token[:10]}...: {str(e)}")
                # FirebaseError, UnregisteredError 등의 오류가 발생하면 토큰 제거
                if ('unregistered' in str(e).lower() or 'invalid' in str(e).lower() or 'requested entity was not found' in str(e).lower()
                    or 'the registration token is not a valid fcm registration token' in str(e).lower()):
                    invalid_tokens.append(token)
        
        # 유효하지 않은 토큰 제거
        valid_tokens = [token for token in fcm_tokens if token not in invalid_tokens and token.strip()]
        
        # 변경 사항이 있는지 확인
        if len(valid_tokens) == original_count:
            return False, 0  # 변경 없음
            
        # 토큰 목록 업데이트 - JSON 배열로 저장
        user_data["fcm_tokens"] = valid_tokens
        
        # 변경 사항 반환
        return True, len(invalid_tokens)
        
    except Exception as e:
        print(f"토큰 정리 중 오류 발생: {e}")
        return False, 0
# 알림 가져오기 엔드포인트
@app.route("/get_notifications", methods=["GET"])
def get_notifications():
    discordWebhooksURL = request.args.get("discordWebhooksURL")
    username = request.args.get("username")
    page = request.args.get("page", default=1, type=int)
    limit = request.args.get(
        "limit", default=50, type=int
    )  # 한 번에 가져올 알림 수 제한

    if not discordWebhooksURL or not username:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "디스코드 웹훅 URL과 사용자명이 필요합니다",
                }
            ),
            400,
        )

    # 사용자 인증 확인
    if discordWebhooksURL in app.userStateData.index:
        db_username = app.userStateData.loc[discordWebhooksURL, "username"]
        if db_username != username:
            return jsonify({"status": "error", "message": "인증 실패"}), 401
    else:
        return jsonify({"status": "error", "message": "사용자를 찾을 수 없습니다"}), 404

    # Supabase에서 사용자 설정 가져오기
    supabase = create_client(environ["supabase_url"], environ["supabase_key"])
    result = (
        supabase.table("userStateData")
        .select("*")
        .eq("discordURL", discordWebhooksURL)
        .execute()
    )

    if not result.data:
        return jsonify({"status": "error", "message": "설정을 찾을 수 없습니다"}), 404

    user_data = result.data[0]

    # 알림 내역 추출
    notifications = user_data.get("notifications", "[]")
    if not isinstance(notifications, list):
        try:
            notifications = loads(notifications)
        except:
            notifications = []

    # 전체 알림 수
    total_count = len(notifications)

    # 페이지네이션 적용 (최신 순으로 정렬 후 페이지 계산)
    sorted_notifications = sorted(
        notifications, key=lambda x: x.get("timestamp", ""), reverse=True
    )
    start = (page - 1) * limit
    end = min(start + limit, len(sorted_notifications))
    paginated_notifications = sorted_notifications[start:end]

    return jsonify(
        {
            "status": "success",
            "notifications": paginated_notifications,
            "pagination": {
                "total": total_count,
                "page": page,
                "limit": limit,
                "pages": (total_count + limit - 1) // limit,
            },
        }
    )

# 알림 읽음 표시 엔드포인트
@app.route("/mark_notifications_read", methods=["POST"])
def mark_notifications_read():
    # JSON 데이터 처리
    if request.is_json:
        data = request.get_json()
    else:
        # form-data 처리
        data = request.form

    discordWebhooksURL = normalize_discord_webhook_url(data.get("discordWebhooksURL"))
    username = data.get("username")
    notification_ids = data.get("notification_ids")

    if not discordWebhooksURL or not username:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "디스코드 웹훅 URL과 사용자명이 필요합니다",
                }
            ),
            400,
        )

    try:
        notification_ids = loads(notification_ids) if notification_ids else []
    except:
        notification_ids = []

    # 사용자 인증 확인
    if discordWebhooksURL in app.userStateData.index:
        db_username = app.userStateData.loc[discordWebhooksURL, "username"]
        if db_username != username:
            return jsonify({"status": "error", "message": "인증 실패"}), 401
    else:
        return jsonify({"status": "error", "message": "사용자를 찾을 수 없습니다"}), 404

    # Supabase에서 사용자 설정 가져오기
    supabase = create_client(environ["supabase_url"], environ["supabase_key"])
    result = (
        supabase.table("userStateData")
        .select("*")
        .eq("discordURL", discordWebhooksURL)
        .execute()
    )

    if not result.data:
        return jsonify({"status": "error", "message": "설정을 찾을 수 없습니다"}), 404

    user_data = result.data[0]

    # 알림 내역 추출
    notifications = user_data.get("notifications", "[]")
    if not isinstance(notifications, list):
        try:
            notifications = loads(notifications)
        except:
            notifications = []

    # 읽음 표시 업데이트
    updated_notifications = []
    for notification in notifications:
        if notification.get("id") in notification_ids:
            notification["read"] = True
        updated_notifications.append(notification)

    # 업데이트된 알림 저장
    supabase.table("userStateData").update({"notifications": updated_notifications}).eq(
        "discordURL", discordWebhooksURL
    ).execute()

    return jsonify({"status": "success", "message": "알림이 읽음으로 표시되었습니다"})

# 알림 전체 삭제 엔드포인트
@app.route("/clear_notifications", methods=["POST"])
def clear_notifications():
    # JSON 데이터 처리
    if request.is_json:
        data = request.get_json()
    else:
        # form-data 처리
        data = request.form

    discordWebhooksURL = normalize_discord_webhook_url(data.get("discordWebhooksURL"))
    username = data.get("username")

    if not discordWebhooksURL or not username:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "디스코드 웹훅 URL과 사용자명이 필요합니다",
                }
            ),
            400,
        )

    # 사용자 인증 확인
    if discordWebhooksURL in app.userStateData.index:
        db_username = app.userStateData.loc[discordWebhooksURL, "username"]
        if db_username != username:
            return jsonify({"status": "error", "message": "인증 실패"}), 401
    else:
        return jsonify({"status": "error", "message": "사용자를 찾을 수 없습니다"}), 404

    # Supabase에서 알림 목록 초기화
    supabase = create_client(environ["supabase_url"], environ["supabase_key"])
    supabase.table("userStateData").update({"notifications": []}).eq(
        "discordURL", discordWebhooksURL
    ).execute()

    return jsonify({"status": "success", "message": "모든 알림이 삭제되었습니다"})

# FCM 토큰 제거 엔드포인트 (로그아웃 시 사용)
@app.route("/remove_fcm_token", methods=["POST"])
def remove_fcm_token():
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form

    username = data.get("username")
    discord_webhook_url = normalize_discord_webhook_url(data.get("discordWebhooksURL"))
    
    # fcm_token 파라미터는 이제 선택적입니다
    fcm_token = data.get("fcm_token")

    if not username or not discord_webhook_url:
        return (
            jsonify({"status": "error", "message": "필수 정보가 누락되었습니다"}),
            400,
        )

    try:
        # Supabase 연결
        supabase = create_client(environ["supabase_url"], environ["supabase_key"])

        # 기존 사용자 확인
        result = (
            supabase.table("userStateData")
            .select("*")
            .eq("discordURL", discord_webhook_url)
            .execute()
        )

        if not result.data:
            return (
                jsonify({"status": "error", "message": "사용자를 찾을 수 없습니다"}),
                404,
            )

        # 사용자 데이터 가져오기
        user_data = result.data[0]

        # 특정 토큰만 제거할지, 모든 토큰을 제거할지 결정
        if fcm_token:
            # 특정 토큰만 제거
            existing_tokens = user_data.get("fcm_tokens", "")
            if existing_tokens:
                tokens_list = existing_tokens.split(",")
                if fcm_token in tokens_list:
                    tokens_list.remove(fcm_token)
                tokens_str = ",".join(tokens_list)
            else:
                tokens_str = ""
        else:
            # 모든 토큰 제거
            tokens_str = ""

        # 업데이트
        update_data = {
            "fcm_tokens": tokens_str,
            "last_token_update": datetime.now().isoformat(),
        }

        supabase.table("userStateData").update(update_data).eq(
            "discordURL", discord_webhook_url
        ).execute()

        return jsonify({"status": "success", "message": "FCM 토큰이 제거되었습니다"})

    except Exception as e:
        print(f"FCM 토큰 제거 중 오류: {e}")
        return (
            jsonify(
                {"status": "error", "message": f"토큰 제거 중 오류 발생: {str(e)}"}
            ),
            500,
        )

async def send_push_notification(messages, json_data, firebase_initialized_globally=True):
    """
    푸시 알림을 전송하는 개선된 함수
    
    Args:
        messages: 웹훅 URL 목록
        json_data: 알림 데이터
        firebase_initialized_globally: Firebase 초기화 상태
    """
    start_time = time.time()
    
    # 성능 측정을 위한 기본 정보 로깅
    recipient_count = len(messages)
    print(f"푸시 알림 전송 시작: {recipient_count}명 대상")
    
    # 캐시를 활용한 알림 전송 함수 호출
    result = await cached_send_push_notification(messages, json_data, firebase_initialized_globally)
    
    # 성능 측정 결과 로깅
    end_time = time.time()
    duration = end_time - start_time
    print(f"푸시 알림 전송 완료: {duration:.2f}초 소요 (결과: {'성공' if result else '실패'})")
    
    return result

# 예약 작업 설정 함수 추가
def setup_scheduled_tasks():
    """주기적인 백그라운드 작업 설정"""
    scheduler = BackgroundScheduler()
    
    # 알림 캐시를 15분마다 비워 최신 데이터 유지
    scheduler.add_job(
        func=clear_notification_cache,
        trigger="interval",
        minutes=15
    )
    
    # 유효하지 않은 FCM 토큰을 매일 정리 (트래픽이 적은 시간에)
    scheduler.add_job(
        func=lambda: asyncio.run(cleanup_all_invalid_tokens()),
        trigger="cron",
        hour=3,  # 새벽 3시
        minute=0
    )
    
    scheduler.start()
    
    # 앱 종료 시 스케줄러 종료
    atexit.register(lambda: scheduler.shutdown())

# 시작 시 한 번만 실행할 FCM 토큰 정리 함수
async def one_time_fcm_token_cleanup():
    """
    애플리케이션 시작 시 한 번만 실행되는 FCM 토큰 정리 함수
    """
    try:
        print(f"{datetime.now()} FCM 토큰 일회성 정리 시작")
        
        # Supabase 클라이언트 생성
        supabase = get_supabase_client()
        
        # 모든 사용자 데이터 가져오기
        result = supabase.table("userStateData").select("*").execute()
        
        if not result.data:
            print("정리할 사용자 데이터가 없습니다")
            return
            
        total_users = len(result.data)
        cleaned_users = 0
        total_removed_tokens = 0
        
        for user_data in result.data:
            discord_url = user_data.get("discordURL")
            if not discord_url:
                continue
                
            changed, removed_count = await cleanup_invalid_fcm_tokens(user_data)
            
            if changed:
                # Supabase 업데이트 - JSON 배열로 저장
                update_data = {
                    "fcm_tokens": user_data["fcm_tokens"],  # 이미 JSON 배열 형식
                    "last_token_update": datetime.now().isoformat(),
                }
                
                supabase.table("userStateData").update(update_data).eq(
                    "discordURL", discord_url
                ).execute()
                
                cleaned_users += 1
                total_removed_tokens += removed_count
        
        print(f"{datetime.now()} FCM 토큰 정리 완료: {cleaned_users}/{total_users} 사용자, {total_removed_tokens}개 토큰 제거")
        
    except Exception as e:
        print(f"토큰 정리 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()

@app.route("/remove_specific_token", methods=["POST"])
def remove_specific_token():
    """특정 FCM 토큰만 제거하는 엔드포인트"""
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form

    username = data.get("username")
    discord_webhook_url = normalize_discord_webhook_url(data.get("discordWebhooksURL"))
    fcm_token = data.get("fcm_token")

    if not username or not discord_webhook_url or not fcm_token:
        return (
            jsonify({"status": "error", "message": "필수 정보가 누락되었습니다"}),
            400,
        )

    try:
        # Supabase 연결
        supabase = create_client(environ["supabase_url"], environ["supabase_key"])

        # 기존 사용자 확인
        result = (
            supabase.table("userStateData")
            .select("*")
            .eq("discordURL", discord_webhook_url)
            .execute()
        )

        if not result.data:
            return (
                jsonify({"status": "error", "message": "사용자를 찾을 수 없습니다"}),
                404,
            )

        # 사용자 데이터 가져오기
        user_data = result.data[0]

        # 기존 토큰 목록 가져오기
        existing_tokens = user_data.get("fcm_tokens", "")
        if not existing_tokens:
            return jsonify({"status": "success", "message": "제거할 토큰이 없습니다"})

        tokens_list = existing_tokens.split(",")
        
        # 특정 토큰이 목록에 있는지 확인
        if fcm_token not in tokens_list:
            return jsonify({"status": "success", "message": "해당 토큰이 존재하지 않습니다"})
            
        # 토큰 제거
        tokens_list.remove(fcm_token)
        tokens_str = ",".join(tokens_list)

        # 업데이트
        update_data = {
            "fcm_tokens": tokens_str,
            "last_token_update": datetime.now().isoformat(),
        }

        supabase.table("userStateData").update(update_data).eq(
            "discordURL", discord_webhook_url
        ).execute()

        return jsonify({"status": "success", "message": "토큰이 성공적으로 제거되었습니다"})

    except Exception as e:
        print(f"특정 토큰 제거 중 오류: {e}")
        return (
            jsonify(
                {"status": "error", "message": f"토큰 제거 중 오류 발생: {str(e)}"}
            ),
            500,
        )

# 디버깅용 FCM 토큰 유효성 검사하는 유틸리티 함수
def validate_fcm_token(token):
    """
    FCM 토큰의 유효성을 검사합니다.
    
    Args:
        token: 검사할 FCM 토큰
        
    Returns:
        bool: 토큰이 유효하면 True, 그렇지 않으면 False
    """
    try:
        # 더미 메시지 생성
        message = messaging.Message(
            data={'validate': 'true'},
            token=token
        )
        
        # 실제로 보내지 않고 유효성 확인만 (dry_run=True)
        messaging.send(message, dry_run=True)
        return True
    except messaging.UnregisteredError:
        # 등록되지 않은 토큰 (앱 삭제 등)
        return False
    except messaging.InvalidArgumentError:
        # 유효하지 않은 형식의 토큰
        return False
    except Exception as e:
        print(f"토큰 검증 중 오류: {e}")
        # 확실하지 않은 경우 일단 유효하다고 가정
        return True

if __name__ == "__main__":

    # Only initialize once for the main process, not the reloader
    if environ.get("WERKZEUG_RUN_MAIN") != "true":
        # Initialize Firebase here
        firebase_initialized_globally = initialize_firebase(False)
        if not firebase_initialized_globally:
            print("경고: Firebase 초기화에 실패했습니다. 푸시 알림 기능이 작동하지 않을 수 있습니다.")

        # FCM 토큰 정리 작업 실행 (한 번만)
        asyncio.run(one_time_fcm_token_cleanup())
        print("FCM 토큰 정리 작업이 완료되었습니다.")

    # 예약 작업 설정 (추가됨)
    setup_scheduled_tasks()

    # App initialization
    with app.app_context():
        app.userStateData = init_background_tasks()
        app.notification_cache = init_notification_system()  # 알림 캐시 초기화
    
    app.run(host="0.0.0.0", port=5000, debug=False)
