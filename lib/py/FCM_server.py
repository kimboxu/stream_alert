import asyncio
import firebase_admin
from firebase_admin import credentials, messaging
from os import environ, path
from typing import List, Dict, Any
from flask import request, jsonify
from datetime import datetime
from supabase import create_client

def initialize_firebase():
    try:
        # 이미 초기화되었는지 확인
        firebase_admin.get_app()
        print("Firebase 앱이 이미 초기화되어 있습니다.")
    except ValueError:
        # 초기화되지 않은 경우에만 초기화 진행
        try:
            # 현재 파일의 디렉토리 경로를 가져와서 사용
            current_dir = path.dirname(path.abspath(__file__))
            json_path = path.join(current_dir, "streamalert-a07d2-firebase-adminsdk-fbsvc-ac409b5179.json")
            
            # JSON 파일이 존재하는지 확인
            if not path.exists(json_path):
                print(f"Firebase 인증 파일을 찾을 수 없습니다: {json_path}")
                return False
                
            cred = credentials.Certificate(json_path)
            firebase_admin.initialize_app(cred)
            print("Firebase 앱이 성공적으로 초기화되었습니다.")
            return True
        except Exception as e:
            print(f"Firebase 초기화 중 오류 발생: {e}")
            return False
    return True

# FCM 토큰 등록 엔드포인트
@app.route('/register_fcm_token', methods=['POST'])
def register_fcm_token():
    username = request.form.get('username')
    discord_webhook_url = request.form.get('discordWebhooksURL')
    fcm_token = request.form.get('fcm_token')
    
    if not username or not discord_webhook_url or not fcm_token:
        return jsonify({"status": "error", "message": "필수 정보가 누락되었습니다"}), 400
    
    try:
        # Supabase에 FCM 토큰 저장
        supabase = create_client(environ['supabase_url'], environ['supabase_key'])
        
        # 기존 사용자 확인
        result = supabase.table('userStateData').select('*').eq('discordURL', discord_webhook_url).execute()
        
        if not result.data:
            return jsonify({"status": "error", "message": "사용자를 찾을 수 없습니다"}), 404
        
        # FCM 토큰 업데이트
        update_data = {
            "fcm_tokens": fcm_token,
            "last_token_update": datetime.now().isoformat()
        }
        
        supabase.table('userStateData').update(update_data).eq('discordURL', discord_webhook_url).execute()
        
        return jsonify({"status": "success", "message": "FCM 토큰이 등록되었습니다"})
    
    except Exception as e:
        print(f"FCM 토큰 등록 중 오류: {e}")
        return jsonify({"status": "error", "message": f"토큰 등록 중 오류 발생: {str(e)}"}), 500

# 푸시 알림 설정 저장 엔드포인트
@app.route('/save_push_settings', methods=['POST'])
def save_push_settings():
    username = request.form.get('username')
    discord_webhook_url = request.form.get('discordWebhooksURL')
    notification_settings = request.form.get('notification_settings')
    
    if not username or not discord_webhook_url or not notification_settings:
        return jsonify({"status": "error", "message": "필수 정보가 누락되었습니다"}), 400
    
    try:
        # Supabase에 알림 설정 저장
        supabase = create_client(environ['supabase_url'], environ['supabase_key'])
        
        # 기존 사용자 확인
        result = supabase.table('userStateData').select('*').eq('discordURL', discord_webhook_url).execute()
        
        if not result.data:
            return jsonify({"status": "error", "message": "사용자를 찾을 수 없습니다"}), 404
        
        # 알림 설정 업데이트
        update_data = {
            "push_notification_settings": notification_settings
        }
        
        supabase.table('userStateData').update(update_data).eq('discordURL', discord_webhook_url).execute()
        
        return jsonify({"status": "success", "message": "알림 설정이 저장되었습니다"})
    
    except Exception as e:
        print(f"알림 설정 저장 중 오류: {e}")
        return jsonify({"status": "error", "message": f"설정 저장 중 오류 발생: {str(e)}"}), 500

class FCMNotificationSender:
    def __init__(self):
        self.supabase_url = environ.get('supabase_url')
        self.supabase_key = environ.get('supabase_key')
        self.MAX_RETRIES = 3
        self.BASE_DELAY = 0.2
    
    async def send_notifications(self, notifications: List[Dict[str, Any]]) -> List[str]:
        """
        여러 FCM 알림을 병렬로 전송합니다.
        
        Args:
            notifications: [{'token': 'fcm_token', 'data': {...}}] 형태의 알림 목록
            
        Returns:
            전송 성공한 알림의 응답 목록
        """
        semaphore = asyncio.Semaphore(5)  # 최대 동시 요청 수 제한
        
        tasks = [
            asyncio.create_task(self._send_notification_with_retry(notification, semaphore))
            for notification in notifications
        ]
        
        # 응답 수집
        responses = []
        for task in asyncio.as_completed(tasks):
            result = await task
            if result is not None:
                responses.append(result)
        
        return responses
    
    async def _send_notification_with_retry(self, notification: Dict[str, Any], semaphore: asyncio.Semaphore) -> str:
        """단일 FCM 알림을 전송하고 필요시 재시도합니다."""
        async with semaphore:
            for attempt in range(self.MAX_RETRIES):
                try:
                    # Firebase Admin SDK를 사용하여 메시지 전송
                    message = messaging.Message(
                        token=notification['token'],
                        data=notification['data'],
                        notification=messaging.Notification(
                            title=notification.get('title', '알림'),
                            body=notification.get('body', ''),
                        ),
                        android=messaging.AndroidConfig(
                            priority='high',
                        ),
                        apns=messaging.APNSConfig(
                            headers={'apns-priority': '10'},
                        )
                    )
                    
                    # 동기식 전송 (Firebase Admin SDK는 비동기 지원이 제한적임)
                    response = messaging.send(message)
                    return response
                
                except messaging.UnregisteredError:
                    # 등록되지 않은 토큰 처리 (사용자가 앱을 제거했거나 토큰이 만료됨)
                    await self._handle_invalid_token(notification['token'])
                    break
                
                except Exception as e:
                    print(f"알림 전송 중 오류 (시도 {attempt+1}/{self.MAX_RETRIES}): {e}")
                    
                    if attempt == self.MAX_RETRIES - 1:
                        break
                    
                    # 지수 백오프로 재시도
                    await asyncio.sleep(self.BASE_DELAY * (2 ** attempt))
            
            return None