from os import environ
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import asyncio
import signal
from json import loads, dumps
from dotenv import load_dotenv
from datetime import datetime, timedelta
import pandas as pd
from shared_state import StateManager
from urllib.parse import unquote
from requests import get 

from notification_service import (
    initialize_firebase,
    cleanup_all_invalid_tokens,
    setup_scheduled_tasks,
    save_tokens_data,
)

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
CORS(app)

def init_background_tasks():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # StateManager를 사용해 데이터 가져오기
    state = StateManager.get_instance()
    init = state.get_init()
    if init is None: init = loop.run_until_complete(state.initialize())
    loop.close()
    return init

def save_user_data(discordWebhooksURL, username):
    # DB에 저장
    app.init.userStateData.loc[discordWebhooksURL, "username"] = username
    app.init.supabase.table("userStateData").upsert(
        {
            "discordURL": discordWebhooksURL,
            "username": username,
        }
    ).execute()

    # 사용자 데이터 변경 플래그 설정
    # asyncio.run(update_flag('user_date', True))

def normalize_discord_webhook_url(webhook_url: str) -> str:
    if webhook_url is None:
        return None
    return webhook_url.replace(
        "https://discordapp.com/api/webhooks/", "https://discord.com/api/webhooks/"
    )

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

    if discordWebhooksURL in app.init.userStateData.index:
        db_username = app.init.userStateData.loc[discordWebhooksURL, "username"]
        check_have_id = True
    else:
        check_have_id = False

    # 로그인 정보 출력 (디버깅용)
    print(f"로그인 시도: 사용자명: {username}, 디스코드 웹훅 URL: {discordWebhooksURL}")

    # 인증 로직
    if check_have_id and db_username == username:
        # 사용자 알림 설정 조회
        user_data = (
            app.init.userStateData.loc[discordWebhooksURL].to_dict()
            if isinstance(app.init.userStateData.loc[discordWebhooksURL], pd.Series)
            else app.init.userStateData.loc[discordWebhooksURL]
        )

        # 기본 응답 데이터
        response_data = {
            "status": "success",
            "message": "로그인 성공",
            "notification_settings": {
                "뱅온 알림": user_data.get("뱅온 알림", ""),
                "방제 변경 알림": user_data.get("방제 변경 알림", ""),
                "방종 알림": user_data.get("방종 알림", ""),
                "방송 하이라이트 알림": user_data.get("방송 하이라이트 알림", ""),
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

    if discordWebhooksURL in app.init.userStateData.index:
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
    if discordWebhooksURL in app.init.userStateData.index:
        db_username = app.init.userStateData.loc[discordWebhooksURL, "username"]
        if db_username != username:
            return jsonify({"status": "error", "message": "인증 실패"}), 401
    else:
        return jsonify({"status": "error", "message": "사용자를 찾을 수 없습니다"}), 404

    if discordWebhooksURL not in app.init.userStateData.index:
        return jsonify({"status": "error", "message": "설정을 찾을 수 없습니다"}), 404

    user_data = app.init.userStateData.loc[discordWebhooksURL]

    # 알림 설정 정보 추출
    settings = {
        "뱅온 알림": user_data.get("뱅온 알림", ""),
        "방제 변경 알림": user_data.get("방제 변경 알림", ""),
        "방종 알림": user_data.get("방종 알림", ""),
        "방송 하이라이트 알림": user_data.get("방송 하이라이트 알림", ""),
        "유튜브 알림": user_data.get("유튜브 알림", {}),
        "치지직 VOD": user_data.get("치지직 VOD", {}),
        "cafe_user_json": user_data.get("cafe_user_json", {}),
        "chat_user_json": user_data.get("chat_user_json", {}),
    }
    
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
    if discordWebhooksURL in app.init.userStateData.index:
        db_username = app.init.userStateData.loc[discordWebhooksURL, "username"]
        if db_username != username:
            return jsonify({"status": "error", "message": "인증 실패"}), 401
    else:
        return jsonify({"status": "error", "message": "사용자를 찾을 수 없습니다"}), 404

    # 기본 업데이트 데이터 설정
    update_data = {"discordURL": discordWebhooksURL, "username": username}
    
    # JSON 필드 목록
    json_fields = ["유튜브 알림", "치지직 VOD", "cafe_user_json", "chat_user_json"]
    
    # 일반 텍스트 필드 목록
    text_fields = ["뱅온 알림", "방제 변경 알림", "방종 알림", "방송 하이라이트 알림"]
    
    # 모든 필드 처리
    for field in text_fields + json_fields:
        if field in data:
            field_data = data.get(field)
            
            # JSON 필드 처리
            if field in json_fields:
                update_data[field] = loads(field_data)
                app.init.userStateData.at[discordWebhooksURL, field] = update_data[field]

            # 일반 텍스트 필드 처리
            else:
                update_data[field] = field_data
                app.init.userStateData.at[discordWebhooksURL, field] = field_data

    # Supabase에 설정 업데이트
    try:
        result = app.init.supabase.table("userStateData").upsert(update_data).execute()
        print(f"사용자 설정 저장 성공: {discordWebhooksURL}")
    except Exception as e:
        print(f"데이터베이스 저장 오류: {e}")
        return jsonify({"status": "error", "message": f"데이터베이스 저장 오류: {str(e)}"}), 500

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
    discordWebhooksURL = normalize_discord_webhook_url(data.get("discordWebhooksURL"))
    new_username = data.get("newUsername")

    if not old_username or not discordWebhooksURL or not new_username:
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
    if discordWebhooksURL in app.init.userStateData.index:
        db_username = app.init.userStateData.loc[discordWebhooksURL, "username"]
        if db_username != old_username:
            return jsonify({"status": "error", "message": "인증 실패"}), 401
    else:
        return jsonify({"status": "error", "message": "사용자를 찾을 수 없습니다"}), 404

    try:
        save_user_data(discordWebhooksURL, new_username)

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
        # init 객체에서 직접 데이터를 가져와 JSON 직렬화 가능한 형태로 변환
        afreecaIDList = app.init.afreecaIDList.to_dict('records')
        chzzkIDList = app.init.chzzkIDList.to_dict('records')
        cafeData = app.init.cafeData.to_dict('records')
        chzzk_video = app.init.chzzk_video.to_dict('records')
        youtubeData = app.init.youtubeData.to_dict('records')
        chzzk_chatFilter = app.init.chzzk_chatFilter.to_dict('records')
        afreeca_chatFilter = app.init.afreeca_chatFilter.to_dict('records')

        return jsonify(
            {
                "status": "success",
                "afreecaStreamers":     afreecaIDList,
                "chzzkStreamers":       chzzkIDList,
                "cafeStreamers":        cafeData,
                "chzzkVideoStreamers":  chzzk_video,
                "youtubeStreamers":     youtubeData,
                "chzzkChatFilter":      chzzk_chatFilter,
                "afreecaChatFilter":    afreeca_chatFilter,
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

@app.route("/proxy-image", methods=["GET"])
def proxy_image():
    """
    CORS 우회를 위한 이미지 프록시 엔드포인트
    사용법: /proxy-image?url=인코딩된_이미지_URL
    """
    image_url = request.args.get("url")
    source = request.args.get("source")
    
    if not image_url:
        return jsonify({"status": "error", "message": "URL 매개변수가 필요합니다"}), 400
    
    try:
        # URL 디코딩
        decoded_url = unquote(image_url)
        
        # 요청 헤더 설정
        # 네이버 이미지인 경우 특별 처리
        if source == 'naver':
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Referer': 'https://cafe.naver.com/'
            }
        else:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Referer': 'https://streamalert-a07d2.web.app/'
            }
        
        # 소스 서버에서 이미지 가져오기 (스트리밍)
        response = get(decoded_url, headers=headers, stream=True, timeout=10)
        
        if response.status_code != 200:
            return jsonify({
                "status": "error", 
                "message": f"이미지를 불러오는데 실패했습니다. 상태 코드: {response.status_code}.{decoded_url}"
            }), response.status_code
        
        # 응답 헤더 설정
        headers = {
            'Content-Type': response.headers.get('Content-Type', 'image/jpeg'),
            'Content-Length': response.headers.get('Content-Length', ''),
            'Cache-Control': 'public, max-age=86400',  # 24시간 캐싱
            'Access-Control-Allow-Origin': '*',  # CORS 허용
            'Access-Control-Allow-Methods': 'GET, OPTIONS',
            'Access-Control-Allow-Headers': 'Origin, X-Requested-With, Content-Type, Accept',
        }
        
        # 스트리밍 응답 반환
        return Response(
            stream_with_context(response.iter_content(chunk_size=1024)),
            status=response.status_code,
            headers=headers
        )
        
    except Exception as e:
        print(f"이미지 프록시 오류: {e}")
        return jsonify({
            "status": "error", 
            "message": f"이미지 프록시 처리 중 오류: {str(e)}"
        }), 500


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
    if discordWebhooksURL in app.init.userStateData.index:
        db_username = app.init.userStateData.loc[discordWebhooksURL, "username"]
        if db_username != username:
            return jsonify({"status": "error", "message": "인증 실패"}), 401
    else:
        return jsonify({"status": "error", "message": "사용자를 찾을 수 없습니다"}), 404


    if discordWebhooksURL not in app.init.userStateData.index:
        return jsonify({"status": "error", "message": "설정을 찾을 수 없습니다"}), 404

    user_data = app.init.userStateData.loc[discordWebhooksURL]

    # 알림 내역 추출
    notifications = user_data.get("notifications", [])

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
    if discordWebhooksURL in app.init.userStateData.index:
        db_username = app.init.userStateData.loc[discordWebhooksURL, "username"]
        if db_username != username:
            return jsonify({"status": "error", "message": "인증 실패"}), 401
    else:
        return jsonify({"status": "error", "message": "사용자를 찾을 수 없습니다"}), 404

    if discordWebhooksURL not in app.init.userStateData.index:
        return jsonify({"status": "error", "message": "설정을 찾을 수 없습니다"}), 404

    user_data = app.init.userStateData.loc[discordWebhooksURL]

    # 알림 내역 추출
    notifications = user_data.get("notifications", [])

    # 읽음 표시 업데이트
    updated_notifications = []
    for notification in notifications:
        if notification.get("id") in notification_ids:
            notification["read"] = True
        updated_notifications.append(notification)

    save_notifications(app.init, discordWebhooksURL, updated_notifications)

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
    if discordWebhooksURL in app.init.userStateData.index:
        db_username = app.init.userStateData.loc[discordWebhooksURL, "username"]
        if db_username != username:
            return jsonify({"status": "error", "message": "인증 실패"}), 401
    else:
        return jsonify({"status": "error", "message": "사용자를 찾을 수 없습니다"}), 404

    save_user_data(discordWebhooksURL, username)

    

    return jsonify({"status": "success", "message": "모든 알림이 삭제되었습니다"})

# FCM 토큰 등록 엔드포인트
@app.route("/register_fcm_token", methods=["POST"])
def register_fcm_token():
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form

    username = data.get("username")
    discordWebhooksURL = normalize_discord_webhook_url(data.get("discordWebhooksURL"))
    fcm_token = data.get("fcm_token")
    device_id = data.get("device_id")  # 기기 식별자

    if not username or not discordWebhooksURL or not fcm_token:
        return (
            jsonify({"status": "error", "message": "필수 정보가 누락되었습니다"}),
            400,
        )

    # 기기 식별자가 없는 경우 기본값 생성
    if not device_id:
        device_id = f"unknown_{fcm_token[:8]}"

    try:
        # 기존 사용자 확인
        if discordWebhooksURL not in app.init.userStateData.index:
            return (
                jsonify({"status": "error", "message": "사용자를 찾을 수 없습니다"}),
                404,
            )

        # 현재 사용자의 데이터 가져오기
        user_data = app.init.userStateData.loc[discordWebhooksURL]

        # 토큰 데이터 형식 확인 및 초기화
        tokens_data = user_data.get("fcm_tokens_data", [])
        if not isinstance(tokens_data, list):
            tokens_data = []
            
        # 같은 기기가 다른 계정에 로그인하는 경우 처리
        for other_webhook_url in app.init.userStateData.index:
            # 현재 사용자는 건너뛰기
            if other_webhook_url == discordWebhooksURL:
                continue
                
            other_user_data = app.init.userStateData.loc[other_webhook_url]
            other_tokens_data = other_user_data.get("fcm_tokens_data", [])
            
            if not isinstance(other_tokens_data, list) or not other_tokens_data:
                continue
                
            # 이 기기 ID를 가진 토큰이 있는지 확인
            has_this_device = any(token_item.get("device_id") == device_id for token_item in other_tokens_data)
            
            if has_this_device:
                # 이 기기 ID를 제외한 다른 토큰만 유지
                updated_tokens = [item for item in other_tokens_data if item.get("device_id") != device_id]
                
                # 다른 사용자의 토큰 목록 업데이트
                if len(updated_tokens) != len(other_tokens_data):
                    save_tokens_data(app.init, other_webhook_url, updated_tokens)
                    print(f"다른 사용자({other_webhook_url[:10]}...)에서 기기 ID({device_id})를 가진 토큰을 제거했습니다.")
        
        # 현재 사용자의 토큰 데이터 업데이트
        # 같은 기기 ID를 가진 기존 토큰 찾기
        existing_device = False
        current_time = datetime.now().isoformat()
        
        for i, token_data in enumerate(tokens_data):
            if token_data.get("device_id") == device_id:
                # 같은 기기 ID가 있으면 토큰 업데이트
                existing_device = True
                tokens_data[i] = {
                    "token": fcm_token,
                    "device_id": device_id,
                    "updated_at": current_time,
                    "registered_at": token_data.get("registered_at", current_time)
                }
                break
        
        # 같은 기기 ID가 없으면 새로 추가
        if not existing_device:
            tokens_data.append({
                "token": fcm_token,
                "device_id": device_id,
                "registered_at": current_time,
                "updated_at": current_time
            })
        
        # 토큰 데이터 저장
        save_tokens_data(app.init, discordWebhooksURL, tokens_data)

        return jsonify({"status": "success", "message": "FCM 토큰이 등록되었습니다"})

    except Exception as e:
        print(f"FCM 토큰 등록 중 오류: {e}")
        return (
            jsonify(
                {"status": "error", "message": f"토큰 등록 중 오류 발생: {str(e)}"}
            ),
            500,
        )
    
# FCM 토큰 제거 엔드포인트
@app.route("/remove_fcm_token", methods=["POST"])
def remove_fcm_token():
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form

    username = data.get("username")
    discordWebhooksURL = normalize_discord_webhook_url(data.get("discordWebhooksURL"))
    fcm_token = data.get("fcm_token")
    device_id = data.get("device_id")  # 기기 ID 추가

    if not username or not discordWebhooksURL:
        return (
            jsonify({"status": "error", "message": "필수 정보가 누락되었습니다"}),
            400,
        )

    try:
        # 사용자 데이터 가져오기
        user_data = app.init.userStateData.loc[discordWebhooksURL]
        
        # 토큰 데이터 형식 확인
        tokens_data = user_data.get("fcm_tokens_data", [])
        if not isinstance(tokens_data, list):
            tokens_data = []

        # 제거 방식 결정 (기기 ID로 제거 또는 토큰으로 제거)
        original_count = len(tokens_data)
        if device_id:
            # 기기 ID로 제거
            tokens_data = [item for item in tokens_data if item.get("device_id") != device_id]
        elif fcm_token:
            # 특정 토큰 제거
            tokens_data = [item for item in tokens_data if item.get("token") != fcm_token]
        else:
            # 기기 ID나 토큰 정보가 없으면 모든 토큰 제거
            tokens_data = []

        # 변경사항이 있으면 저장
        if len(tokens_data) != original_count:
            save_tokens_data(app.init, discordWebhooksURL, tokens_data)

        return jsonify({"status": "success", "message": "FCM 토큰이 제거되었습니다"})

    except Exception as e:
        print(f"FCM 토큰 제거 중 오류: {e}")
        return (
            jsonify(
                {"status": "error", "message": f"토큰 제거 중 오류 발생: {str(e)}"}
            ),
            500,
        )

#성능 통계 조회 엔드포인트
@app.route("/get_performance_stats", methods=["GET"])
def get_performance_stats():
    try:
        days = request.args.get('days', default=7, type=int)
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            from base import get_realtime_statistics
            stats = loop.run_until_complete(get_realtime_statistics(days))
            
            if stats:
                return jsonify({
                    "status": "success",
                    **stats
                })
            else:
                return jsonify({
                    "status": "error",
                    "message": "통계 계산 실패"
                }), 500
                
        finally:
            loop.close()
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"통계 조회 실패: {str(e)}"
        }), 500

#저장된 일일 통계 조회
@app.route("/get_daily_statistics", methods=["GET"])
def get_daily_statistics():
    try:
        days = request.args.get('days', default=7, type=int)
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)
        
        # 로컬 파일에서 통계 로드
        from base import load_daily_statistics
        all_stats = load_daily_statistics()
        
        # 날짜 범위 필터링
        filtered_stats = []
        for date_str, stat_data in all_stats.items():
            stat_date = datetime.fromisoformat(date_str).date()
            if start_date <= stat_date <= end_date:
                filtered_stats.append(stat_data)
        
        # 날짜순 정렬 (최신 순)
        filtered_stats.sort(key=lambda x: x['date'], reverse=True)
        
        return jsonify({
            "status": "success",
            "data": filtered_stats,
            "period": f"{start_date} ~ {end_date}",
            "source": "local_file"
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"일일 통계 조회 실패: {str(e)}"
        }), 500
    
#수동으로 일일 통계 계산 트리거 (테스트용)
@app.route("/trigger_daily_stats", methods=["POST"])
def trigger_daily_stats():
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            from base import calculate_and_save_daily_statistics
            loop.run_until_complete(calculate_and_save_daily_statistics())
            
            return jsonify({
                "status": "success",
                "message": "일일 통계 계산이 완료되었습니다"
            })
            
        finally:
            loop.close()
            
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"일일 통계 계산 실패: {str(e)}"
        }), 500

def save_notifications(init, discordWebhooksURL, notifications):
    init.userStateData.loc[discordWebhooksURL, "notifications"] = notifications

    # 업데이트된 알림 저장
    init.supabase.table("userStateData").update({"notifications": init.userStateData.loc[discordWebhooksURL, "notifications"]}).eq(
        "discordURL", discordWebhooksURL
    ).execute()

    # asyncio.run(update_flag('user_date', True))

async def force_save_all(init):
    # 모든 userStateData를 supabase에 upsert (비동기)
    for webhook_url in init.userStateData.index:
        try:
            await asyncio.to_thread(
                lambda: init.supabase.table('userStateData')
                    .upsert({
                        'discordURL': webhook_url,
                        'notifications': init.userStateData.loc[webhook_url, 'notifications'],
                        'last_db_save_time': datetime.now().astimezone().isoformat()
                    })
                    .execute()
            )
        except Exception as e:
            print(f"[종료시 저장오류] {webhook_url}: {e}")

# SIGTERM/SIGINT 핸들러 등록

def graceful_shutdown_handler(signum, frame):
    print("서버 종료 감지! 모든 데이터를 저장합니다...")
    loop = asyncio.get_event_loop()
    try:
        # 사용자 데이터 저장
        loop.run_until_complete(force_save_all(app.init))
        print("[완료] 서버 종료 전 모든 사용자 데이터를 DB에 저장했습니다.")
        
        # 통계 데이터 저장
        from base import save_all_cached_data
        loop.run_until_complete(save_all_cached_data())
        print("[완료] 서버 종료 전 모든 통계 데이터를 로컬 파일에 저장했습니다.")
        
    except Exception as e:
        print(f"[종료시 저장실패] {e}")
    import sys
    sys.exit(0)

if __name__ == "__main__":

    # Only initialize once for the main process, not the reloader
    if environ.get("WERKZEUG_RUN_MAIN") != "true":
        # Initialize Firebase here
        firebase_initialized_globally = initialize_firebase(False)
        if not firebase_initialized_globally:
            print("경고: Firebase 초기화에 실패했습니다. 푸시 알림 기능이 작동하지 않을 수 있습니다.")

        # FCM 토큰 정리 작업 실행 (한 번만)
        asyncio.run(cleanup_all_invalid_tokens())
        print("FCM 토큰 정리 작업이 완료되었습니다.")

    # 예약 작업 설정 (추가됨)
    setup_scheduled_tasks()

    # App initialization
    with app.app_context():
        app.init = init_background_tasks()
        # 안전 종료 핸들러 등록 (init 생성 후)
        signal.signal(signal.SIGTERM, graceful_shutdown_handler)
        signal.signal(signal.SIGINT, graceful_shutdown_handler)
    
    app.run(host="0.0.0.0", port=443, debug=False)
