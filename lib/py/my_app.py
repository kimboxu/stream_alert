from os import environ
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import asyncio
import signal
import threading
from uuid import uuid4
from json import loads, dumps
from dotenv import load_dotenv
from datetime import datetime, timedelta
import pandas as pd
from shared_state import StateManager
from urllib.parse import unquote
from requests import get 
from base import get_timestamp_from_stream_id
from notification_service import (
    initialize_firebase,
    cleanup_all_invalid_tokens,
    setup_scheduled_tasks,
    save_tokens_data,
    file_notification_manager,
)

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
                "하이라이트 알림": user_data.get("하이라이트 알림", ""),
                "핫클립 알림": user_data.get("핫클립 알림", ""),
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
        "하이라이트 알림": user_data.get("하이라이트 알림", ""),
        "핫클립 알림": user_data.get("핫클립 알림", ""),
        "유튜브 알림": user_data.get("유튜브 알림", {}),
        "VOD 알림": user_data.get("VOD 알림", {}),
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
    json_fields = ["유튜브 알림", "VOD 알림", "cafe_user_json", "chat_user_json"]
    
    # 일반 텍스트 필드 목록
    text_fields = ["뱅온 알림", "방제 변경 알림", "방종 알림", "하이라이트 알림", "핫클립 알림"]
    
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
        print(f"{datetime.now()} 사용자 설정 저장 성공: {discordWebhooksURL}")
    except Exception as e:
        print(f"{datetime.now()} 데이터베이스 저장 오류: {str(e)}")
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
        print(f"{datetime.now()} 사용자 이름 변경 중 오류: {str(e)}")
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
        videoData = app.init.video_data.to_dict('records')
        youtubeData = app.init.youtubeData.to_dict('records')
        chzzk_chatFilter = app.init.chzzk_chatFilter.to_dict('records')
        afreeca_chatFilter = app.init.afreeca_chatFilter.to_dict('records')

        return jsonify(
            {
                "status": "success",
                "afreecaStreamers":     afreecaIDList,
                "chzzkStreamers":       chzzkIDList,
                "cafeStreamers":        cafeData,
                "videoDataStreamers":  videoData,
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
        print(f"{datetime.now()} 이미지 프록시 오류: {str(e)}")
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
    limit = request.args.get("limit", default=50, type=int)

    if not discordWebhooksURL or not username:
        return (
            jsonify({
                "status": "error",
                "message": "디스코드 웹훅 URL과 사용자명이 필요합니다",
            }),
            400,
        )

    # 사용자 인증 확인
    if discordWebhooksURL in app.init.userStateData.index:
        db_username = app.init.userStateData.loc[discordWebhooksURL, "username"]
        if db_username != username:
            return jsonify({"status": "error", "message": "인증 실패"}), 401
    else:
        return jsonify({"status": "error", "message": "사용자를 찾을 수 없습니다"}), 404

    try:
        # 파일에서 알림 내역 로드
        notifications = file_notification_manager.load_notifications(discordWebhooksURL)
        
        # 전체 알림 수
        total_count = len(notifications)

        # 페이지네이션 적용 (최신 순으로 정렬 후 페이지 계산)
        sorted_notifications = sorted(
            notifications, key=lambda x: x.get("timestamp", ""), reverse=True
        )
        start = (page - 1) * limit
        end = min(start + limit, len(sorted_notifications))
        paginated_notifications = sorted_notifications[start:end]

        return jsonify({
            "status": "success",
            "notifications": paginated_notifications,
            "pagination": {
                "total": total_count,
                "page": page,
                "limit": limit,
                "pages": (total_count + limit - 1) // limit,
            },
        })
        
    except Exception as e:
        print(f"{datetime.now()} 알림 조회 중 오류: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"알림을 가져오는 중 오류가 발생했습니다: {str(e)}"
        }), 500

# 알림 읽음 표시 엔드포인트
@app.route("/mark_notifications_read", methods=["POST"])
def mark_notifications_read():
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form

    discordWebhooksURL = normalize_discord_webhook_url(data.get("discordWebhooksURL"))
    username = data.get("username")
    notification_ids = data.get("notification_ids")

    if not discordWebhooksURL or not username:
        return (
            jsonify({
                "status": "error",
                "message": "디스코드 웹훅 URL과 사용자명이 필요합니다",
            }),
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

    try:
        # 파일에서 알림 내역 로드
        notifications = file_notification_manager.load_notifications(discordWebhooksURL)

        # 읽음 표시 업데이트
        updated_notifications = []
        for notification in notifications:
            if notification.get("id") in notification_ids:
                notification["read"] = True
            updated_notifications.append(notification)

        # 파일에 저장
        success = file_notification_manager.save_notifications(
            discordWebhooksURL, 
            updated_notifications,
            force_save=True  # 읽음 표시는 즉시 저장
        )
        
        if success:
            return jsonify({"status": "success", "message": "알림이 읽음으로 표시되었습니다"})
        else:
            return jsonify({"status": "error", "message": "알림 상태 업데이트에 실패했습니다"}), 500
            
    except Exception as e:
        print(f"{datetime.now()} 알림 읽음 표시 중 오류: {str(e)}")
        return jsonify({
            "status": "error", 
            "message": f"알림 상태 업데이트 중 오류가 발생했습니다: {str(e)}"
        }), 500

# 알림 전체 삭제 엔드포인트
@app.route("/clear_notifications", methods=["POST"])
def clear_notifications():
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form

    discordWebhooksURL = normalize_discord_webhook_url(data.get("discordWebhooksURL"))
    username = data.get("username")

    if not discordWebhooksURL or not username:
        return (
            jsonify({
                "status": "error",
                "message": "디스코드 웹훅 URL과 사용자명이 필요합니다",
            }),
            400,
        )

    # 사용자 인증 확인
    if discordWebhooksURL in app.init.userStateData.index:
        db_username = app.init.userStateData.loc[discordWebhooksURL, "username"]
        if db_username != username:
            return jsonify({"status": "error", "message": "인증 실패"}), 401
    else:
        return jsonify({"status": "error", "message": "사용자를 찾을 수 없습니다"}), 404

    try:
        # 빈 알림 목록으로 덮어쓰기 (모든 알림 삭제)
        success = file_notification_manager.save_notifications(
            discordWebhooksURL, 
            [],  # 빈 목록
            force_save=True
        )
        
        if success:
            return jsonify({"status": "success", "message": "모든 알림이 삭제되었습니다"})
        else:
            return jsonify({"status": "error", "message": "알림 삭제에 실패했습니다"}), 500
            
    except Exception as e:
        print(f"{datetime.now()} 알림 삭제 중 오류: {str(e)}")
        return jsonify({
            "status": "error", 
            "message": f"알림 삭제 중 오류가 발생했습니다: {str(e)}"
        }), 500

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
                    print(f"{datetime.now()} 다른 사용자({other_webhook_url[:10]}...)에서 기기 ID({device_id})를 가진 토큰을 제거했습니다.")
        
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
        print(f"{datetime.now()} FCM 토큰 등록 중 오류: {str(e)}")
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
        print(f"{datetime.now()} FCM 토큰 제거 중 오류: {str(e)}")
        return (
            jsonify(
                {"status": "error", "message": f"토큰 제거 중 오류 발생: {str(e)}"}
            ),
            500,
        )

# 활성 하이라이트 챗 조회 (현재 메모리에 있는 데이터)
@app.route("/get_active_highlight_chats", methods=["GET"])
def get_active_highlight_chats():
    """현재 메모리에 저장된 활성 하이라이트 챗 데이터 조회"""
    try:
        channel_id = request.args.get("channel_id")  # 특정 채널만 조회 (옵션)
        include_details = request.args.get("include_details", "false").lower() == "true"
        
        active_chats = {}
        
        # 특정 채널 또는 전체 채널 처리
        channels_to_check = [channel_id] if channel_id else list(app.init.highlight_chat.keys())
        
        for ch_id in channels_to_check:
            if ch_id not in app.init.highlight_chat:
                continue
                
            channel_data = app.init.highlight_chat[ch_id]
            active_chats[ch_id] = {}
            
            for stream_id, highlight_data in channel_data.items():
                try:
                    # 기본 정보 추출
                    basic_info = {
                        "stream_id": stream_id,
                        "last_title": getattr(highlight_data, 'last_title', ''),
                        "stream_end_id": getattr(highlight_data, 'stream_end_id', ''),
                        "timeline_comments_count": len(getattr(highlight_data, 'timeline_comments', [])),
                        "has_ended": bool(getattr(highlight_data, 'stream_end_id', '')),
                        "created_time": get_timestamp_from_stream_id(stream_id).isoformat() if stream_id else None
                    }
                    
                    # 상세 정보 포함 시
                    if include_details:
                        timeline_comments = getattr(highlight_data, 'timeline_comments', [])
                        basic_info.update({
                            "timeline_comments": timeline_comments,
                            "latest_comments": timeline_comments[-5:] if timeline_comments else []  # 최근 5개
                        })
                    
                    active_chats[ch_id][stream_id] = basic_info
                    
                except Exception as e:
                    print(f"{datetime.now()} 하이라이트 데이터 처리 오류 ({ch_id}, {stream_id}): {str(e)}")
                    continue
        
        # 채널 이름 추가
        result = {}
        for ch_id, streams in active_chats.items():
            try:
                # 채널명 찾기 (chzzk 또는 afreeca에서)
                channel_name = "Unknown"
                if ch_id in app.init.chzzkIDList.index:
                    channel_name = app.init.chzzkIDList.loc[ch_id, 'channelName']
                elif ch_id in app.init.afreecaIDList.index:
                    channel_name = app.init.afreecaIDList.loc[ch_id, 'channelName']
                
                result[ch_id] = {
                    "channel_name": channel_name,
                    "active_streams": len(streams),
                    "streams": streams
                }
            except Exception as e:
                print(f"{datetime.now()} 채널 정보 처리 오류 ({ch_id}): {str(e)}")
                result[ch_id] = {
                    "channel_name": "Unknown",
                    "active_streams": len(streams),
                    "streams": streams
                }
        
        return jsonify({
            "status": "success",
            "total_channels": len(result),
            "total_active_streams": sum(data["active_streams"] for data in result.values()),
            "data": result,
            "retrieved_at": datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"활성 하이라이트 챗 조회 실패: {str(e)}"
        }), 500

# 저장된 하이라이트 챗 파일 목록 조회
@app.route("/get_saved_highlight_files", methods=["GET"])
def get_saved_highlight_files():
    """저장된 하이라이트 챗 파일 목록 조회"""
    try:
        channel_name = request.args.get("channel_name")  # 특정 채널만 조회 (옵션)
        limit = request.args.get("limit", default=50, type=int)  # 결과 제한
        
        # HighlightChatSaver 인스턴스 생성
        from highlight_chat_saver import HighlightChatSaver
        saver = HighlightChatSaver()
        
        # 파일 정보 조회
        files_info = saver.get_saved_files_info(channel_name)
        
        # 제한 적용
        if limit > 0:
            files_info = files_info[:limit]
        
        return jsonify({
            "status": "success",
            "total_files": len(files_info),
            "filtered_by_channel": channel_name,
            "files": files_info,
            "retrieved_at": datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"저장된 하이라이트 파일 목록 조회 실패: {str(e)}"
        }), 500

# 특정 하이라이트 챗 상세 조회
@app.route("/get_highlight_chat_detail", methods=["GET"])
def get_highlight_chat_detail():
    """특정 하이라이트 챗의 상세 정보 조회"""
    try:
        # 파라미터 처리
        channel_id = request.args.get("channel_id")
        stream_id = request.args.get("stream_id")
        file_path = request.args.get("file_path")  # 파일에서 직접 조회하는 경우
        
        if not any([channel_id and stream_id, file_path]):
            return jsonify({
                "status": "error",
                "message": "channel_id와 stream_id 또는 file_path가 필요합니다"
            }), 400
        
        result_data = None
        
        # 메모리에서 조회 (활성 데이터)
        if channel_id and stream_id:
            if (channel_id in app.init.highlight_chat and 
                stream_id in app.init.highlight_chat[channel_id]):
                
                highlight_data = app.init.highlight_chat[channel_id][stream_id]
                
                # 채널 정보 추가
                channel_name = "Unknown"
                if channel_id in app.init.chzzkIDList.index:
                    channel_name = app.init.chzzkIDList.loc[channel_id, 'channelName']
                elif channel_id in app.init.afreecaIDList.index:
                    channel_name = app.init.afreecaIDList.loc[channel_id, 'channelName']
                
                result_data = {
                    "source": "active_memory",
                    "channel_id": channel_id,
                    "channel_name": channel_name,
                    "stream_id": stream_id,
                    "last_title": getattr(highlight_data, 'last_title', ''),
                    "stream_end_id": getattr(highlight_data, 'stream_end_id', ''),
                    "timeline_comments": getattr(highlight_data, 'timeline_comments', []),
                    "is_active": not bool(getattr(highlight_data, 'stream_end_id', '')),
                    "created_time": get_timestamp_from_stream_id(stream_id).isoformat() if stream_id else None
                }
            else:
                return jsonify({
                    "status": "error",
                    "message": f"활성 데이터를 찾을 수 없습니다: {channel_id}/{stream_id}"
                }), 404
        
        # 파일에서 조회 (저장된 데이터)
        elif file_path:
            import json
            from pathlib import Path
            
            try:
                file_path = Path(file_path)
                if not file_path.exists():
                    return jsonify({
                        "status": "error",
                        "message": f"파일을 찾을 수 없습니다: {file_path}"
                    }), 404
                
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)
                
                result_data = {
                    "source": "saved_file",
                    "file_path": str(file_path),
                    **file_data
                }
                
            except Exception as e:
                return jsonify({
                    "status": "error",
                    "message": f"파일 읽기 실패: {str(e)}"
                }), 500
        
        # 통계 정보 추가
        if result_data and "timeline_comments" in result_data:
            comments = result_data["timeline_comments"]
            stats = {
                "total_comments": len(comments),
                "comments_with_scores": len([c for c in comments if "score_difference" in c]),
                "avg_score": 0,
                "max_score": 0,
                "score_distribution": {"0-20": 0, "21-40": 0, "41-60": 0, "61-80": 0, "81-100": 0}
            }
            
            # 점수 관련 통계 계산
            scores = []
            for comment in comments:
                if "score_difference" in comment:
                    try:
                        score = float(comment["score_difference"])
                        scores.append(score)
                        
                        # 분포 계산
                        if score <= 20:
                            stats["score_distribution"]["0-20"] += 1
                        elif score <= 40:
                            stats["score_distribution"]["21-40"] += 1
                        elif score <= 60:
                            stats["score_distribution"]["41-60"] += 1
                        elif score <= 80:
                            stats["score_distribution"]["61-80"] += 1
                        else:
                            stats["score_distribution"]["81-100"] += 1
                    except (ValueError, TypeError):
                        continue
            
            if scores:
                stats["avg_score"] = round(sum(scores) / len(scores), 2)
                stats["max_score"] = round(max(scores), 2)
            
            result_data["statistics"] = stats
        
        return jsonify({
            "status": "success",
            "data": result_data,
            "retrieved_at": datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"하이라이트 챗 상세 조회 실패: {str(e)}"
        }), 500

# 하이라이트 챗 통계 조회
@app.route("/get_highlight_chat_statistics", methods=["GET"])
def get_highlight_chat_statistics():
    """전체 하이라이트 챗 시스템 통계 조회"""
    try:
        include_channel_breakdown = request.args.get("include_channels", "false").lower() == "true"
        
        # 활성 데이터 통계
        active_stats = {
            "total_channels": 0,
            "total_active_streams": 0,
            "total_timeline_comments": 0,
            "channels_with_data": [],
            "recent_activity": []
        }
        
        for channel_id, channel_data in app.init.highlight_chat.items():
            if not channel_data:
                continue
                
            active_stats["total_channels"] += 1
            
            # 채널명 찾기
            channel_name = "Unknown"
            try:
                if channel_id in app.init.chzzkIDList.index:
                    channel_name = app.init.chzzkIDList.loc[channel_id, 'channelName']
                elif channel_id in app.init.afreecaIDList.index:
                    channel_name = app.init.afreecaIDList.loc[channel_id, 'channelName']
            except:
                pass
            
            channel_info = {
                "channel_id": channel_id,
                "channel_name": channel_name,
                "active_streams": len(channel_data),
                "total_comments": 0
            }
            
            # 스트림별 통계
            for stream_id, highlight_data in channel_data.items():
                active_stats["total_active_streams"] += 1
                
                try:
                    comments = getattr(highlight_data, 'timeline_comments', [])
                    comments_count = len(comments)
                    channel_info["total_comments"] += comments_count
                    active_stats["total_timeline_comments"] += comments_count
                    
                    # 최근 활동 (최근 1시간 내 업데이트된 스트림)
                    try:
                        stream_time = get_timestamp_from_stream_id(stream_id)
                        if (datetime.now() - stream_time).total_seconds() < 3600:  # 1시간
                            active_stats["recent_activity"].append({
                                "channel_id": channel_id,
                                "channel_name": channel_name,
                                "stream_id": stream_id,
                                "comments_count": comments_count,
                                "last_title": getattr(highlight_data, 'last_title', ''),
                                "stream_time": stream_time.isoformat()
                            })
                    except:
                        pass
                        
                except Exception as e:
                    print(f"{datetime.now()} 스트림 통계 처리 오류 ({channel_id}, {stream_id}): {str(e)}")
                    continue
            
            if include_channel_breakdown:
                active_stats["channels_with_data"].append(channel_info)
        
        # 최근 활동 정렬 (최신순)
        active_stats["recent_activity"] = sorted(
            active_stats["recent_activity"][-10:],  # 최근 10개만
            key=lambda x: x["stream_time"], 
            reverse=True
        )
        
        # 저장된 파일 통계
        try:
            from highlight_chat_saver import HighlightChatSaver
            saver = HighlightChatSaver()
            saved_files = saver.get_saved_files_info()
            
            saved_stats = {
                "total_saved_files": len(saved_files),
                "total_saved_highlights": sum(f.get("total_highlights", 0) for f in saved_files),
                "storage_size_mb": sum(f.get("size_mb", 0) for f in saved_files),
                "date_range": {
                    "oldest": min((f.get("stream_start_time", "") for f in saved_files), default=""),
                    "newest": max((f.get("stream_start_time", "") for f in saved_files), default="")
                } if saved_files else {"oldest": "", "newest": ""}
            }
        except Exception as e:
            print(f"{datetime.now()} 저장된 파일 통계 처리 오류: {str(e)}")
            saved_stats = {
                "total_saved_files": 0,
                "total_saved_highlights": 0,
                "storage_size_mb": 0,
                "date_range": {"oldest": "", "newest": ""}
            }
        
        return jsonify({
            "status": "success",
            "active_data": active_stats,
            "saved_data": saved_stats,
            "system_health": {
                "memory_usage_normal": active_stats["total_active_streams"] < 100,  # 임계치 기준
                "recent_activity_detected": len(active_stats["recent_activity"]) > 0,
                "storage_healthy": saved_stats["storage_size_mb"] < 1000  # 1GB 기준
            },
            "retrieved_at": datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"하이라이트 챗 통계 조회 실패: {str(e)}"
        }), 500

# 하이라이트 챗 데이터 정리 (메모리 관리)
@app.route("/cleanup_highlight_data", methods=["POST"])
def cleanup_highlight_data():
    """오래된 하이라이트 데이터 정리 (관리자용)"""
    try:
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form
        
        days_threshold = int(data.get("days_threshold", 7))  # 기본 7일
        force_cleanup = data.get("force", "false").lower() == "true"
        
        cleanup_results = {
            "cleaned_channels": [],
            "total_streams_removed": 0,
            "total_comments_removed": 0,
            "errors": []
        }
        
        for channel_id in list(app.init.highlight_chat.keys()):
            try:
                # 채널명 찾기
                channel_name = "Unknown"
                if channel_id in app.init.chzzkIDList.index:
                    channel_name = app.init.chzzkIDList.loc[channel_id, 'channelName']
                elif channel_id in app.init.afreecaIDList.index:
                    channel_name = app.init.afreecaIDList.loc[channel_id, 'channelName']
                
                channel_data = app.init.highlight_chat[channel_id]
                streams_to_remove = []
                comments_removed = 0
                
                current_time = datetime.now()
                threshold_time = current_time - timedelta(days=days_threshold)
                
                for stream_id in list(channel_data.keys()):
                    try:
                        # 스트림 시간 확인
                        stream_timestamp = get_timestamp_from_stream_id(stream_id)
                        
                        # 정리 조건 확인
                        should_cleanup = (
                            stream_timestamp < threshold_time or
                            (force_cleanup and bool(getattr(channel_data[stream_id], 'stream_end_id', '')))
                        )
                        
                        if should_cleanup:
                            # 댓글 수 계산
                            comments = getattr(channel_data[stream_id], 'timeline_comments', [])
                            comments_removed += len(comments)
                            
                            streams_to_remove.append(stream_id)
                            del app.init.highlight_chat[channel_id][stream_id]
                            
                    except ValueError as e:
                        cleanup_results["errors"].append(
                            f"스트림 ID 파싱 실패 ({channel_id}/{stream_id}): {str(e)}"
                        )
                        continue
                
                if streams_to_remove:
                    cleanup_results["cleaned_channels"].append({
                        "channel_id": channel_id,
                        "channel_name": channel_name,
                        "streams_removed": len(streams_to_remove),
                        "comments_removed": comments_removed
                    })
                    cleanup_results["total_streams_removed"] += len(streams_to_remove)
                    cleanup_results["total_comments_removed"] += comments_removed
                
                # 빈 채널 데이터 제거
                if not app.init.highlight_chat[channel_id]:
                    del app.init.highlight_chat[channel_id]
                    
            except Exception as e:
                cleanup_results["errors"].append(f"채널 정리 오류 ({channel_id}): {str(e)}")
                continue
        
        return jsonify({
            "status": "success",
            "message": f"{days_threshold}일 기준으로 데이터 정리 완료",
            "cleanup_results": cleanup_results,
            "cleaned_at": datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"하이라이트 데이터 정리 실패: {str(e)}"
        }), 500
    
@app.route("/get_memory_highlights_summary", methods=["GET"])
def get_memory_highlights_summary():
    """현재 메모리(chat_analyzer)에 있는 하이라이트 요약 정보 - 저장 전 상태 확인용"""
    try:
        state_manager = StateManager.get_instance()
        
        # 하이라이트가 있는 인스턴스들 가져오기 (메모리에서)
        instances_with_highlights = state_manager.get_chat_instances_with_highlights()
        for instances_with_highlight in instances_with_highlights:
            if instances_with_highlight['instance']:
                del instances_with_highlight['instance']

        # 전체 챗 인스턴스 통계
        all_chat_instances = state_manager.get_chat_instances()
        total_chzzk_instances = len(all_chat_instances.get('chzzk', {}))
        total_afreeca_instances = len(all_chat_instances.get('afreeca', {}))
        
        # 메모리 상태 요약 (저장되지 않은 하이라이트만)
        memory_summary = {
            'total_chat_instances': {
                'chzzk': total_chzzk_instances,
                'afreeca': total_afreeca_instances,
                'total': total_chzzk_instances + total_afreeca_instances
            },
            'channels_with_unsaved_highlights': len(instances_with_highlights),
            'total_unsaved_highlights': sum(info['highlights_count'] for info in instances_with_highlights),
            'unsaved_highlight_details': instances_with_highlights,
            'ready_for_save': len(instances_with_highlights) > 0
        }

        return jsonify({
            "status": "success",
            "memory_highlights_summary": memory_summary,
            "note": "이것은 아직 저장되지 않은 메모리의 하이라이트 데이터입니다",
            "checked_at": datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"메모리 하이라이트 상태 확인 실패: {str(e)}"
        }), 500
    
# 하이라이트 챗 캐시 데이터 저장 (메모리 관리), 프로그램 종료 직전에만 사용하기
@app.route("/save_highlight_data", methods=["GET"])
def save_highlight_data():
    """하이라이트 챗 캐시 데이터 저장 (관리자용) - """
    try:
        task_id = str(uuid4())
        
        # SSE 응답 생성 함수
        def generate_sse_updates():
            """SSE 형식으로 작업 상태를 실시간 전송"""
            
            try:
                state_manager = StateManager.get_instance()
                
                # 초기 상태 설정
                initial_data = {
                    "status": "starting",
                    "task_id": task_id,
                    "progress": 0,
                    "message": "작업 초기화 중...",
                    "timestamp": datetime.now().isoformat()
                }
                state_manager.add_task_status(task_id, initial_data)
                
                # 클라이언트에 초기 상태 전송
                yield f"data: {dumps(initial_data, ensure_ascii=False)}\n\n"
                
                # 백그라운드 스레드에서 실제 작업 시작
                thread = threading.Thread(
                    target=run_background_save_with_state_manager,
                    args=(task_id,),
                    daemon=True
                )
                thread.start()
                print(f"{datetime.now()} [{task_id}] 하이라이트 저장 작업 시작됨 (백그라운드 스레드에서 실행 중)")
                
                # 작업 상태를 주기적으로 확인하고 전송
                loop = asyncio.new_event_loop()
                
                max_wait_time = 600
                start_time = datetime.now()
                last_progress = 0
                
                while True:
                    task_data = state_manager.get_task_status(task_id)
                    elapsed_time = (datetime.now() - start_time).total_seconds()
                    
                    if elapsed_time >= max_wait_time:
                        timeout_data = {
                            "status": "timeout",
                            "message": f"작업 시간 초과 ({max_wait_time}초)",
                            "timestamp": datetime.now().isoformat()
                        }
                        yield f"data: {dumps(timeout_data, ensure_ascii=False)}\n\n"
                        print(f"{datetime.now()} [{task_id}] 작업 시간 초과")
                        break
                    
                    if task_data is None:
                        error_data = {
                            "status": "error",
                            "message": "작업을 찾을 수 없습니다",
                            "timestamp": datetime.now().isoformat()
                        }
                        yield f"data: {dumps(error_data, ensure_ascii=False)}\n\n"
                        break
                    
                    # 진행 상황 변경시에만 전송
                    current_progress = task_data.get('progress', 0)
                    if current_progress != last_progress:
                        task_data['timestamp'] = datetime.now().isoformat()
                        yield f"data: {dumps(task_data, ensure_ascii=False)}\n\n"
                        last_progress = current_progress
                        print(f"{datetime.now()} [{task_id}] 진행율: {current_progress}% - {task_data.get('message', '')}")
                    
                    # 작업 완료 또는 에러 상태 확인
                    status = task_data.get('status', '')
                    if status in ['completed', 'error']:
                        task_data['timestamp'] = datetime.now().isoformat()
                        yield f"data: {dumps(task_data, ensure_ascii=False)}\n\n"
                        print(f"{datetime.now()} [{task_id}] 작업 {status}: {task_data.get('message', '')}")
                        break
                    
                    # 비동기 대기 (0.5초)
                    try:
                        loop.run_until_complete(asyncio.sleep(0.5))
                    except:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                
            except Exception as e:
                error_data = {
                    "status": "error",
                    "message": f"SSE 스트림 중 오류: {str(e)}",
                    "timestamp": datetime.now().isoformat(),
                    "error_type": type(e).__name__
                }
                yield f"data: {dumps(error_data, ensure_ascii=False)}\n\n"
                print(f"{datetime.now()} SSE 스트림 오류: {str(e)}")
        
        # SSE 응답 설정
        response = Response(
            generate_sse_updates(),
            mimetype='text/event-stream; charset=utf-8',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
                'Connection': 'keep-alive',
                'Content-Type': 'text/event-stream; charset=utf-8',
                'Access-Control-Allow-Origin': '*',
                'Transfer-Encoding': 'chunked',
                'Content-Encoding': 'utf-8'  # 명시적 UTF-8 인코딩
            }
        )
        response.charset = 'utf-8'
        response.timeout = None
        
        return response
        
    except Exception as e:
        print(f"{datetime.now()} SSE 연결 실패: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"SSE 연결 실패: {str(e)}"
        }), 500

def run_background_save_with_state_manager(task_id):
    """StateManager를 활용한 백그라운드 저장 작업"""
    try:
        # 새로운 이벤트 루프 생성
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # 비동기 작업 실행
        loop.run_until_complete(background_save_task_with_state_manager(task_id))
        
    except Exception as e:
        # StateManager에 에러 상태 업데이트
        state_manager = StateManager.get_instance()
        state_manager.update_task_status(task_id, {
            "status": "error",
            "error": f"이벤트 루프 생성 실패: {str(e)}",
            "failed_at": datetime.now().isoformat()
        })
        print(f"백그라운드 작업 실패: {str(e)}")
    finally:
        try:
            loop.close()
        except:
            pass

async def background_save_task_with_state_manager(task_id):
    """StateManager를 활용한 하이라이트 저장 작업"""
    try:
        # StateManager 인스턴스 가져오기
        state_manager = StateManager.get_instance()
        init = state_manager.get_init()
        # 작업 시작 상태로 업데이트
        state_manager.update_task_status(task_id, {
            "status": "processing",
            "message": "하이라이트 데이터 수집 중...",
            "progress": 5
        })
        
        # StateManager에서 하이라이트 인스턴스들 가져오기
        instances_with_highlights = state_manager.get_chat_instances_with_highlights()
        total_channels = len(instances_with_highlights)
        
        if total_channels == 0:
            state_manager.update_task_status(task_id, {
                "status": "completed",
                "progress": 100,
                "message": "저장할 하이라이트 데이터가 없습니다",
                "results": {
                    "processed_channels": [],
                    "total_highlights_saved": 0,
                    "errors": []
                },
                "completed_at": datetime.now().isoformat()
            })
            return
        
        # 진행률 업데이트
        state_manager.update_task_status(task_id, {
            "total_channels": total_channels,
            "processed_channels": 0,
            "message": f"총 {total_channels}개 채널 병렬 처리 시작",
            "progress": 10
        })
        
        save_results = {
            "processed_channels": [],
            "total_highlights_saved": 0,
            "errors": []
        }
        
        # 병렬 처리를 위한 세마포어 (최대 3개 동시 실행)
        max_concurrent = min(3, total_channels)
        semaphore = asyncio.Semaphore(max_concurrent)
        completed_count = 0
        
        async def process_single_channel(instance_info):
            """단일 채널 처리 함수 (세마포어 적용)"""
            nonlocal completed_count
            
            async with semaphore:
                try:
                    channel_id = instance_info['channel_id']
                    channel_name = instance_info['channel_name']
                    platform = instance_info['platform']
                    highlights_count = instance_info['highlights_count']
                    chat_instance = instance_info['instance']
                    
                    # print(f"{datetime.now()} [{platform}] {channel_name}: {highlights_count}개 하이라이트 저장 시작")
                    
                    # 하이라이트 처리 실행
                    await chat_instance.highlight_processing()
                    
                    # 작업 완료 대기 로직
                    # wait_make_highlight_chat이 True가 될 때까지 대기
                    max_wait_time = 300  # 최대 5분 대기
                    wait_interval = 1    # 1초마다 체크
                    elapsed_time = 0
                    await asyncio.sleep(5)
                    while elapsed_time < max_wait_time:
                        # 현재 상태 확인
                        is_completed = init.wait_make_highlight_chat.get(channel_id, True)
                        
                        if not is_completed:
                            # print(f"{datetime.now()} [{platform}] {channel_name}: 작업 완료 감지")
                            break
                        
                        # 1초 대기
                        await asyncio.sleep(wait_interval)
                        elapsed_time += wait_interval
                        
                        # 진행 상황 출력 (매 10초마다)
                        if elapsed_time % 10 == 0:
                            print(f"{datetime.now()} [{platform}] {channel_name}: 작업 대기 중... ({elapsed_time}초)")
                    
                    if elapsed_time >= max_wait_time:
                        print(f"{datetime.now()} [{platform}] {channel_name}: 작업 시간 초과 (최대 {max_wait_time}초)")
                    
                    # 결과 수집
                    result = {
                        "channel_id": channel_id,
                        "channel_name": channel_name,
                        "platform": platform,
                        "highlights_saved": highlights_count,
                        "wait_completed": init.wait_make_highlight_chat.get(channel_id, True),
                        "wait_time_seconds": elapsed_time,
                    }
                    save_results["processed_channels"].append(result)
                    save_results["total_highlights_saved"] += highlights_count
                    
                    print(f"{datetime.now()} [{platform}] {channel_name}: 하이라이트 저장 완료")
                    
                except Exception as channel_error:
                    error_msg = f"채널 {instance_info.get('channel_name', 'Unknown')} 처리 중 오류: {str(channel_error)}"
                    save_results["errors"].append(error_msg)
                    print(f"{datetime.now()} {error_msg}")
                
                finally:
                    # 완료 카운트 업데이트
                    completed_count += 1
                    progress = 10 + int((completed_count / total_channels) * 80)
                    
                    state_manager.update_task_status(task_id, {
                        "progress": progress,
                        "processed_channels": completed_count,
                        "message": f"처리 완료: {completed_count}/{total_channels} (병렬 처리 중...)"
                    })
        
        # 모든 채널을 병렬로 처리
        print(f"{datetime.now()} 병렬 처리 시작: {max_concurrent}개 동시 실행")
        
        # asyncio.gather를 사용하여 모든 작업을 동시에 실행
        tasks = [process_single_channel(instance) for instance in instances_with_highlights]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # 완료 상태 업데이트
        state_manager.update_task_status(task_id, {
            "status": "completed",
            "progress": 100,
            "processed_channels": total_channels,
            "results": save_results,
            "message": f"완료: {save_results['total_highlights_saved']}개 하이라이트 저장",
            "completed_at": datetime.now().isoformat()
        })
        
        print(f"{datetime.now()} 하이라이트 저장 작업 완료: 총 {save_results['total_highlights_saved']}개")
        
    except Exception as e:
        state_manager.update_task_status(task_id, {
            "status": "error",
            "error": str(e),
            "message": f"작업 실패: {str(e)}",
            "failed_at": datetime.now().isoformat()
        })
        print(f"{datetime.now()} 하이라이트 저장 작업 실패: {str(e)}")

def get_task_status(task_id):
    try:
        # stream 파라미터 확인 (SSE 스트리밍 여부)
        stream = request.args.get('stream', 'true').lower() == 'true'
        
        # 스트리밍이 아닌 경우 JSON으로 반환 (기존 동작)
        if not stream:
            state_manager = StateManager.get_instance()
            task_data = state_manager.get_task_status(task_id)
            
            if task_data is None:
                return jsonify({
                    "status": "error",
                    "message": "작업을 찾을 수 없습니다"
                }), 404
            
            return jsonify({
                "status": "success",
                "task_data": task_data
            })
        
        # SSE 스트리밍 모드
        def generate_task_updates():
            """작업 상태를 실시간으로 전송"""
            try:
                state_manager = StateManager.get_instance()
                
                # 첫 번째 상태 확인
                task_data = state_manager.get_task_status(task_id)
                if task_data is None:
                    error_data = {
                        "status": "error",
                        "message": "작업을 찾을 수 없습니다",
                        "timestamp": datetime.now().isoformat()
                    }
                    yield f"data: {dumps(error_data, ensure_ascii=False)}\n\n"
                    return
                
                # 초기 상태 전송
                task_data['timestamp'] = datetime.now().isoformat()
                yield f"data: {dumps(task_data, ensure_ascii=False)}\n\n"
                
                # 상태가 완료될 때까지 주기적으로 업데이트 전송
                max_wait_time = 600  # 최대 10분
                elapsed_time = 0
                last_progress = task_data.get('progress', 0)
                last_status = task_data.get('status', '')
                
                loop = asyncio.new_event_loop()
                start_time = datetime.now()
                
                while True:
                    elapsed_time = (datetime.now() - start_time).total_seconds()
                    
                    if elapsed_time >= max_wait_time:
                        break
                    
                    # 현재 상태 확인
                    current_task_data = state_manager.get_task_status(task_id)
                    
                    if current_task_data is None:
                        break
                    
                    # 진행률 또는 상태가 변경되면 전송
                    current_progress = current_task_data.get('progress', 0)
                    current_status = current_task_data.get('status', '')
                    
                    if current_progress != last_progress or current_status != last_status:
                        current_task_data['timestamp'] = datetime.now().isoformat()
                        yield f"data: {dumps(current_task_data, ensure_ascii=False)}\n\n"
                        last_progress = current_progress
                        last_status = current_status
                        
                        print(f"{datetime.now()} [Task {task_id[:8]}...] 상태 업데이트: {current_status} - {current_progress}%")
                    
                    # 완료 또는 에러 상태면 종료
                    if current_status in ['completed', 'error', 'timeout']:
                        break
                    
                    # 비동기 대기 (0.5초)
                    try:
                        loop.run_until_complete(asyncio.sleep(0.5))
                    except:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                
                print(f"{datetime.now()} [Task {task_id[:8]}...] SSE 스트리밍 종료")
                
            except Exception as e:
                error_data = {
                    "status": "error",
                    "message": f"스트리밍 중 오류 발생: {str(e)}",
                    "timestamp": datetime.now().isoformat(),
                    "error_type": type(e).__name__
                }
                yield f"data: {dumps(error_data, ensure_ascii=False)}\n\n"
                print(f"{datetime.now()} Task 상태 스트리밍 오류: {str(e)}")
        
        # SSE 응답 설정
        response = Response(
            generate_task_updates(),
            mimetype='text/event-stream; charset=utf-8',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
                'Connection': 'keep-alive',
                'Content-Type': 'text/event-stream; charset=utf-8',
                'Access-Control-Allow-Origin': '*'
            }
        )
        response.charset = 'utf-8'
        response.timeout = None
        
        return response
        
    except Exception as e:
        print(f"{datetime.now()} Task 상태 조회 실패: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"작업 상태 조회 실패: {str(e)}"
        }), 500

@app.route("/get_all_active_tasks", methods=["GET"])
def get_all_active_tasks():
    """StateManager를 통한 모든 작업 상태 조회"""
    state_manager = StateManager.get_instance()
    all_tasks = state_manager.get_task_status()
    
    # 활성 작업만 필터링
    active_tasks = {
        task_id: task_data for task_id, task_data in all_tasks.items()
        if task_data.get('status') not in ['completed', 'error']
    }
    
    return jsonify({
        "status": "success",
        "total_tasks": len(all_tasks),
        "active_tasks": len(active_tasks),
        "tasks": all_tasks
    })

@app.route("/cleanup_old_tasks", methods=["POST"])
def cleanup_old_tasks():
    """StateManager를 통한 오래된 작업 정리"""
    try:
        hours = request.args.get('hours', default=6, type=int)
        
        state_manager = StateManager.get_instance()
        removed_count = state_manager.cleanup_completed_tasks(hours)
        
        return jsonify({
            "status": "success",
            "message": f"{removed_count}개의 오래된 작업이 정리되었습니다",
            "remaining_tasks": len(state_manager.get_task_status())
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"작업 정리 실패: {str(e)}"
        }), 500

#성능 통계 조회 엔드포인트
@app.route("/get_performance_stats", methods=["GET"])
def get_performance_stats():
    try:
        days = request.args.get('days', default=7, type=int)
        api_type = request.args.get('api_type', default=None, type=str)  # 특정 API 타입 필터
        
        # StateManager에서 성능 매니저 가져오기
        state_manager = StateManager.get_instance()
        performance_manager = state_manager.get_performance_manager()
        
        if not performance_manager:
            return jsonify({
                "status": "error", 
                "message": "성능 매니저를 사용할 수 없습니다"
            }), 500
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # API 타입 필터링 지원
            stats = loop.run_until_complete(
                performance_manager.get_statistics(
                    days=days, 
                    stat_type="realtime", 
                    api_type=api_type
                )
            )
            
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
    
# API 건강도 조회 엔드포인트 
@app.route("/get_api_health", methods=["GET"])
def get_api_health():
    try:
        days = request.args.get('days', default=7, type=int)
        api_type = request.args.get('api_type', default=None, type=str)
        
        state_manager = StateManager.get_instance()
        performance_manager = state_manager.get_performance_manager()
        
        if not performance_manager:
            return jsonify({
                "status": "error",
                "message": "성능 매니저를 사용할 수 없습니다"
            }), 500
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            health_stats = loop.run_until_complete(
                performance_manager.get_statistics(
                    days=days, 
                    stat_type="api_health", 
                    api_type=api_type
                )
            )
            
            return jsonify({
                "status": "success",
                **health_stats
            })
            
        finally:
            loop.close()
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"API 건강도 조회 실패: {str(e)}"
        }), 500

# API 성능 요약 조회 엔드포인트
@app.route("/get_performance_summary", methods=["GET"])
def get_performance_summary():
    try:
        days = request.args.get('days', default=7, type=int)
        
        state_manager = StateManager.get_instance()
        performance_manager = state_manager.get_performance_manager()
        
        if not performance_manager:
            return jsonify({
                "status": "error",
                "message": "성능 매니저를 사용할 수 없습니다"
            }), 500
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            summary = loop.run_until_complete(
                performance_manager.get_statistics(
                    days=days, 
                    stat_type="performance_summary"
                )
            )
            
            return jsonify({
                "status": "success",
                **summary
            })
            
        finally:
            loop.close()
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"성능 요약 조회 실패: {str(e)}"
        }), 500

# API 비교 분석 엔드포인트
@app.route("/compare_apis", methods=["GET"])
def compare_apis():
    try:
        days = request.args.get('days', default=7, type=int)
        api_types = request.args.get('api_types', default='', type=str)
        
        # API 타입들을 쉼표로 분리
        if not api_types:
            return jsonify({
                "status": "error",
                "message": "비교할 API 타입들을 지정해주세요 (예: api_types=chzzk_api,afreeca_api,cafe_api)"
            }), 400
            
        api_types_list = [api_type.strip() for api_type in api_types.split(',')]
        
        state_manager = StateManager.get_instance()
        performance_manager = state_manager.get_performance_manager()
        
        if not performance_manager:
            return jsonify({
                "status": "error",
                "message": "성능 매니저를 사용할 수 없습니다"
            }), 500
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            comparison = loop.run_until_complete(
                performance_manager.get_api_comparison(api_types_list, days)
            )
            
            return jsonify({
                "status": "success",
                **comparison
            })
            
        finally:
            loop.close()
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"API 비교 분석 실패: {str(e)}"
        }), 500

# 저장된 일일 통계 조회
@app.route("/get_daily_statistics", methods=["GET"])
def get_daily_statistics():
    try:
        days = request.args.get('days', default=7, type=int)
        summary = request.args.get('summary', default='false', type=str).lower() == 'true'
        api_type = request.args.get('api_type', default=None, type=str)

        state_manager = StateManager.get_instance()
        performance_manager = state_manager.get_performance_manager()
        
        if not performance_manager:
            return jsonify({
                "status": "error",
                "message": "성능 매니저를 사용할 수 없습니다"
            }), 500
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            if summary:
                # 요약 정보 포함된 일일 통계
                result = loop.run_until_complete(
                    performance_manager.get_statistics(
                        days=days, 
                        stat_type="daily_summary"
                    )
                )
            else:
                # 기본 일일 통계 리스트
                result = loop.run_until_complete(
                    performance_manager.get_statistics(
                        days=days, 
                        stat_type="daily", 
                        api_type=api_type
                    )
                )
            
            return jsonify({
                "status": "success",
                **result
            })
            
        finally:
            loop.close()
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"일일 통계 조회 실패: {str(e)}"
        }), 500

# 특정 API 상세 분석 엔드포인트
@app.route("/analyze_api", methods=["GET"])
def analyze_api():
    try:
        api_type = request.args.get('api_type', type=str)
        days = request.args.get('days', default=7, type=int)
        
        if not api_type:
            return jsonify({
                "status": "error",
                "message": "분석할 API 타입을 지정해주세요 (예: api_type=chzzk_api)"
            }), 400
        
        state_manager = StateManager.get_instance()
        performance_manager = state_manager.get_performance_manager()
        
        if not performance_manager:
            return jsonify({
                "status": "error",
                "message": "성능 매니저를 사용할 수 없습니다"
            }), 500
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # 실시간 통계
            realtime_stats = loop.run_until_complete(
                performance_manager.get_statistics(
                    days=days, 
                    stat_type="realtime", 
                    api_type=api_type
                )
            )
            
            # 건강도 분석
            health_stats = loop.run_until_complete(
                performance_manager.get_statistics(
                    days=days, 
                    stat_type="api_health", 
                    api_type=api_type
                )
            )
            
            # 일별 트렌드
            daily_trend = loop.run_until_complete(
                performance_manager.get_statistics(
                    days=days, 
                    stat_type="daily", 
                    api_type=api_type
                )
            )
            
            return jsonify({
                "status": "success",
                "api_type": api_type,
                "analysis_period_days": days,
                "realtime_statistics": realtime_stats,
                "health_analysis": health_stats,
                "daily_trend": daily_trend
            })
            
        finally:
            loop.close()
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"API 분석 실패: {str(e)}"
        }), 500

# 모든 활성 API 타입 목록 조회 엔드포인트
@app.route("/get_active_api_types", methods=["GET"])
def get_active_api_types():
    try:
        days = request.args.get('days', default=7, type=int)
        
        state_manager = StateManager.get_instance()
        performance_manager = state_manager.get_performance_manager()
        
        if not performance_manager:
            return jsonify({
                "status": "error",
                "message": "성능 매니저를 사용할 수 없습니다"
            }), 500
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # 전체 통계에서 활성 API 타입들 추출
            stats = loop.run_until_complete(
                performance_manager.get_statistics(days=days, stat_type="realtime")
            )
            
            active_api_types = stats.get('summary', {}).get('active_api_types', [])
            
            return jsonify({
                "status": "success",
                "active_api_types": active_api_types,
                "total_api_types": len(active_api_types),
                "period_days": days
            })
            
        finally:
            loop.close()
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"활성 API 타입 조회 실패: {str(e)}"
        }), 500

# API 알림 설정 (성능 문제 감지 시 알림) - 향후 확장용
@app.route("/set_performance_alerts", methods=["POST"])
def set_performance_alerts():
    try:
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form
        
        # 향후 구현: 특정 API의 성능이 임계치 이하로 떨어질 때 알림
        return jsonify({
            "status": "success",
            "message": "성능 알림 설정이 저장되었습니다 (향후 구현 예정)"
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"성능 알림 설정 실패: {str(e)}"
        }), 500

# 수동으로 일일 통계 계산 트리거 (테스트/관리용)
@app.route("/trigger_daily_stats", methods=["POST"])
def trigger_daily_stats():
    try:
        # 특정 날짜 지정 가능 (옵션)
        target_date_str = request.args.get('date')  # YYYY-MM-DD 형식
        target_date = None
        
        if target_date_str:
            try:
                target_date = datetime.strptime(target_date_str, '%Y-%m-%d')
            except ValueError:
                return jsonify({
                    "status": "error",
                    "message": "날짜 형식이 잘못되었습니다 (YYYY-MM-DD 형식 사용)"
                }), 400
        
        state_manager = StateManager.get_instance()
        performance_manager = state_manager.get_performance_manager()
        
        if not performance_manager:
            return jsonify({
                "status": "error",
                "message": "성능 매니저를 사용할 수 없습니다"
            }), 500
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                performance_manager.calculate_and_save_daily_statistics(target_date)
            )
            
            if result:
                return jsonify({
                    "status": "success",
                    "message": f"일일 통계 계산이 완료되었습니다: {result['date']}",
                    "data": result
                })
            else:
                return jsonify({
                    "status": "error",
                    "message": "일일 통계 계산에 실패했습니다"
                }), 500
            
        finally:
            loop.close()
            
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"일일 통계 계산 실패: {str(e)}"
        }), 500


if __name__ == "__main__":
    # Only initialize once for the main process, not the reloader
    if environ.get("WERKZEUG_RUN_MAIN") != "true":
        # Initialize Firebase here
        firebase_initialized_globally = initialize_firebase(False)
        if not firebase_initialized_globally:
            print(f"{datetime.now()} 경고: Firebase 초기화에 실패했습니다. 푸시 알림 기능이 작동하지 않을 수 있습니다.")

        # FCM 토큰 정리 작업 실행 (한 번만)
        asyncio.run(cleanup_all_invalid_tokens())
        print(f"{datetime.now()} FCM 토큰 정리 작업이 완료되었습니다.")

    # 예약 작업 설정
    setup_scheduled_tasks()
    

    # App initialization
    with app.app_context():
        app.init = init_background_tasks()
    
    app.run(host="0.0.0.0", port=8080, debug=False)