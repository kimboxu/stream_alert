from os import environ, path
from flask import Flask, request, jsonify, render_template, g
from typing import List, Tuple, Optional, Dict, Any
from base import make_list_to_dict
from flask_cors import CORS
import asyncio
import threading
from json import loads, dumps
from supabase import create_client
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, messaging
from datetime import datetime
import pandas as pd
from base import saveNotificationsData
from uuid import uuid4

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
CORS(app)  # 크로스 오리진 요청 허용


def initialize_firebase():
    """Firebase 초기화 함수"""
    try:
        # 이미 초기화되었는지 확인
        firebase_admin.get_app()
        print("Firebase 앱이 이미 초기화되어 있습니다.")
        return True
    except ValueError:
        # 초기화되지 않은 경우에만 초기화 진행
        try:
            # 환경 변수에서 Firebase 인증 정보 가져오기
            cred_dict = {
                "type": environ.get("FIREBASE_TYPE"),
                "project_id": environ.get("FIREBASE_PROJECT_ID"),
                "private_key_id": environ.get("FIREBASE_PRIVATE_KEY_ID"),
                "private_key": environ.get("FIREBASE_PRIVATE_KEY").replace("\\n", "\n"),
                "client_email": environ.get("FIREBASE_CLIENT_EMAIL"),
                "client_id": environ.get("FIREBASE_CLIENT_ID"),
                "auth_uri": environ.get("FIREBASE_AUTH_URI"),
                "token_uri": environ.get("FIREBASE_TOKEN_URI"),
                "auth_provider_x509_cert_url": environ.get(
                    "FIREBASE_AUTH_PROVIDER_X509_CERT_URL"
                ),
                "client_x509_cert_url": environ.get("FIREBASE_CLIENT_X509_CERT_URL"),
                "universe_domain": environ.get("FIREBASE_UNIVERSE_DOMAIN"),
            }

            # 인증 정보 생성
            cred = credentials.Certificate(cred_dict)

            # 프로젝트 ID 가져오기
            project_id = cred.project_id or environ.get("FIREBASE_PROJECT_ID")

            if not project_id:
                print("Firebase 프로젝트 ID를 찾을 수 없습니다.")
                return False

            # Firebase 앱 초기화 (한 번만 호출)
            firebase_admin.initialize_app(
                cred,
                {
                    "projectId": project_id,
                },
            )

            print(
                f"Firebase 앱이 프로젝트 ID '{project_id}'로 성공적으로 초기화되었습니다."
            )
            return True
        except Exception as e:
            print(f"Firebase 초기화 중 오류 발생: {e}")
            import traceback

            traceback.print_exc()  # 자세한 오류 출력
            return False


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
    supabase.table("date_update").upsert({"idx": 0, "user_date": True}).execute()

    return jsonify({"status": "success", "message": "설정이 저장되었습니다"})


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

        # FCM 토큰 업데이트
        user_data = result.data[0]

        # 기존 토큰 목록 가져오기
        existing_tokens = user_data.get("fcm_tokens", "")
        if existing_tokens:
            tokens_list = existing_tokens.split(",")
            # 중복 방지
            if fcm_token not in tokens_list:
                tokens_list.append(fcm_token)
            tokens_str = ",".join(tokens_list)
        else:
            tokens_str = fcm_token

        # 토큰 목록 업데이트
        update_data = {
            "fcm_tokens": tokens_str,
            "last_token_update": datetime.now().isoformat(),
        }

        supabase.table("userStateData").update(update_data).eq(
            "discordURL", discord_webhook_url
        ).execute()

        return jsonify({"status": "success", "message": "FCM 토큰이 등록되었습니다"})

    except Exception as e:
        print(f"FCM 토큰 등록 중 오류: {e}")
        return (
            jsonify(
                {"status": "error", "message": f"토큰 등록 중 오류 발생: {str(e)}"}
            ),
            500,
        )


# 알림 가져오기 엔드포인트
# 알림 가져오기 엔드포인트 개선 (페이지네이션 적용)
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
    fcm_token = data.get("fcm_token")

    if not username or not discord_webhook_url:
        return (
            jsonify({"status": "error", "message": "필수 정보가 누락되었습니다"}),
            400,
        )

    try:
        # Supabase에서 FCM 토큰 제거
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

        # FCM 토큰 제거
        user_data = result.data[0]

        # 기존 토큰 목록 가져오기
        existing_tokens = user_data.get("fcm_tokens", "")
        if existing_tokens:
            tokens_list = existing_tokens.split(",")
            # 해당 토큰 제거
            if fcm_token in tokens_list:
                tokens_list.remove(fcm_token)
            tokens_str = ",".join(tokens_list)
        else:
            tokens_str = ""

        # 토큰 목록 업데이트
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


def get_supabase_client():
    """애플리케이션 컨텍스트에서 Supabase 클라이언트를 가져오거나 생성합니다."""
    if not hasattr(g, "supabase_client"):
        g.supabase_client = create_client(
            environ["supabase_url"], environ["supabase_key"]
        )
    return g.supabase_client

async def send_push_notification(messages: List[str], json_data):
    # Firebase가 초기화되었는지 확인 (한 번만 호출됨)
    if not initialize_firebase():
        print("Firebase 초기화 실패")
        return

    try:
        # 알림 고유 ID 및 시간 미리 생성 (모든 작업에서 공유)
        notification_id = str(uuid4())
        notification_time = datetime.now().isoformat()

        # 메시지 데이터 준비
        notification_data = {
            "title": json_data.get("username", "알림"),
            "body": json_data.get("content", ""),
        }

        # 기본 데이터 필드
        data_fields = {
            "notification_id": notification_id,  # 고유 ID를 명시적으로 포함
            "username": json_data.get("username", "알림"),
            "content": json_data.get("content", ""),
            "avatar_url": json_data.get("avatar_url", ""),
            "timestamp": notification_time,
        }

        # embeds 데이터가 있으면 추가 (Discord와 동일한 형식)
        if "embeds" in json_data and json_data["embeds"]:
            # FCM은 모든 데이터 필드가 문자열이어야 함
            data_fields["embeds"] = dumps(json_data["embeds"])

        # 배치 처리를 위한 작업 목록
        tasks = []

        # Supabase 클라이언트 한 번만 생성
        with app.app_context():
            supabase = get_supabase_client()

            # 병렬 처리를 위한 작업들 준비
            for discord_webhook_url in messages:
                # 기존 사용자 확인
                result = (
                    supabase.table("userStateData")
                    .select("*")
                    .eq("discordURL", discord_webhook_url)
                    .execute()
                )
                if not result.data:
                    continue  # 사용자 없음

                # 사용자 데이터
                user_data = result.data[0]

                # 알림 데이터 저장 작업 생성 (비동기 작업으로 추가)
                tasks.append(
                    asyncio.create_task(
                        saveNotificationsData(
                            supabase,
                            discord_webhook_url,
                            user_data,
                            notification_id,  # 동일한 ID 전달
                            data_fields,
                        )
                    )
                )

                # Flutter 앱으로 메시지 전송 (Firebase 메시징)
                asyncio.create_task(
                    post_msg_to_flutter(user_data, notification_data, data_fields)
                )

            # 모든 작업이 완료될 때까지 대기 (선택적)
            # await asyncio.gather(*tasks)

        return True

    except Exception as e:
        print(f"알림 전송 중 오류 발생: {e}")
        import traceback

        traceback.print_exc()
        return False

async def post_msg_to_flutter(user_data, notification_data, data_fields):
    # 토큰 목록 가져오기
    existing_tokens = user_data.get("fcm_tokens", "")
    if not existing_tokens:
        return

    tokens_list = [
        token.strip() for token in existing_tokens.split(",") if token.strip()
    ]
    if not tokens_list:
        return

    # 2. 개별 토큰에 메시지 전송
    for token in tokens_list:
        try:
            message_data = {k: str(v) for k, v in data_fields.items()}
            
            # 메시지 객체 생성
            message = messaging.Message(
                notification=messaging.Notification(**notification_data),
                data=message_data,  # 수정된 데이터 필드
                token=token,
                android=messaging.AndroidConfig(
                    priority="high",
                    notification=messaging.AndroidNotification(
                        channel_id="high_importance_channel",
                        priority="high",
                    ),
                ),
            )

            # 메시지 전송
            messaging.send(message, dry_run=False)

        except Exception as e:
            print(f"토큰 {token} 메시지 전송 실패: {e}")

if __name__ == "__main__":

    # Only initialize once for the main process, not the reloader
    if environ.get("WERKZEUG_RUN_MAIN") != "true":
        # Initialize Firebase here
        firebase_initialized = initialize_firebase()
        if not firebase_initialized:
            print(
                "경고: Firebase 초기화에 실패했습니다. 푸시 알림 기능이 작동하지 않을 수 있습니다."
            )

    # App initialization
    with app.app_context():
        app.init_var = init_background_tasks()

    app.run(host="0.0.0.0", port=5000, debug=False)
