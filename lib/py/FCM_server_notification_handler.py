import asyncio
import json
import pandas as pd
from firebase_admin import messaging
from os import environ
from datetime import datetime
from typing import List, Dict, Any, Optional
from supabase import create_client
from FCM_server import *

class FCMHandler:
    def __init__(self):
        self.supabase_url = environ.get('supabase_url')
        self.supabase_key = environ.get('supabase_key')
        self.error_webhook_url = environ.get('errorPostBotURL')
        
    async def _handle_invalid_token(self, token: str):
        """등록 해제된 FCM 토큰을 처리합니다."""
        try:
            # Supabase에서 토큰으로 사용자 찾기
            supabase = create_client(self.supabase_url, self.supabase_key)
            result = supabase.table('userStateData').select('*').filter('fcm_tokens', 'cs', f"%{token}%").execute()
            
            if result.data:
                for user in result.data:
                    # 토큰 목록에서 해당 토큰 제거
                    tokens = user.get('fcm_tokens', '').split(',')
                    if token in tokens:
                        tokens.remove(token)
                        
                    # 업데이트된 토큰 목록 저장
                    supabase.table('userStateData').update({
                        'fcm_tokens': ','.join(tokens)
                    }).eq('id', user['id']).execute()
                    
                    print(f"사용자 {user['username']}의 FCM 토큰이 제거되었습니다: {token}")
            
        except Exception as e:
            print(f"유효하지 않은 토큰 처리 중 오류: {e}")

    async def send_streaming_start_notifications(self, streamer_name: str, platform: str, title: str, 
                                                thumbnail_url: str, channel_id: str) -> None:
        """스트리밍 시작 알림을 전송합니다."""
        try:
            # 1. Supabase에서 해당 스트리머에 대한 알림 설정이 있는 사용자 가져오기
            supabase = create_client(self.supabase_url, self.supabase_key)
            users = supabase.table('userStateData').select('*').execute()
            
            # 사용자 데이터를 DataFrame으로 변환
            df = pd.DataFrame(users.data)
            if df.empty:
                return
            
            # 2. 뱅온 알림 설정이 있는 사용자 필터링
            notifications_to_send = []
            
            for _, user in df.iterrows():
                fcm_tokens = user.get('fcm_tokens', '')
                if not fcm_tokens:
                    continue
                
                # 푸시 알림 설정 확인
                try:
                    push_settings = json.loads(user.get('push_notification_settings', '{}'))
                    if not push_settings.get('뱅온 알림', True):  # 기본값은 활성화
                        continue
                except:
                    # 설정이 없으면 기본적으로 알림 활성화
                    pass
                
                # 해당 스트리머에 대한 알림 설정 확인
                bang_on_streamers = user.get('뱅온 알림', '').split(', ')
                if streamer_name in bang_on_streamers:
                    for token in fcm_tokens.split(','):
                        if token.strip():
                            notifications_to_send.append({
                                'token': token.strip(),
                                'title': f'{streamer_name} 방송 시작',
                                'body': title,
                                'data': {
                                    'type': 'stream_start',
                                    'streamer_name': streamer_name,
                                    'platform': platform,
                                    'title': title,
                                    'thumbnail_url': thumbnail_url,
                                    'channel_id': channel_id,
                                    'timestamp': str(datetime.now().timestamp())
                                }
                            })
            
            # 3. 알림 전송
            if notifications_to_send:
                sender = FCMNotificationSender()
                await sender.send_notifications(notifications_to_send)
                print(f"{streamer_name} 방송 시작 알림이 {len(notifications_to_send)}명의 사용자에게 전송되었습니다.")
        
        except Exception as e:
            print(f"스트리밍 시작 알림 전송 중 오류: {e}")

    async def send_streaming_end_notifications(self, streamer_name: str, platform: str, channel_id: str) -> None:
        """스트리밍 종료 알림을 전송합니다."""
        try:
            # 1. Supabase에서 해당 스트리머에 대한 알림 설정이 있는 사용자 가져오기
            supabase = create_client(self.supabase_url, self.supabase_key)
            users = supabase.table('userStateData').select('*').execute()
            
            # 사용자 데이터를 DataFrame으로 변환
            df = pd.DataFrame(users.data)
            if df.empty:
                return
            
            # 2. 방종 알림 설정이 있는 사용자 필터링
            notifications_to_send = []
            
            for _, user in df.iterrows():
                fcm_tokens = user.get('fcm_tokens', '')
                if not fcm_tokens:
                    continue
                
                # 푸시 알림 설정 확인
                try:
                    push_settings = json.loads(user.get('push_notification_settings', '{}'))
                    if not push_settings.get('방종 알림', True):  # 기본값은 활성화
                        continue
                except:
                    # 설정이 없으면 기본적으로 알림 활성화
                    pass
                
                # 해당 스트리머에 대한 알림 설정 확인
                end_stream_streamers = user.get('방종 알림', '').split(', ')
                if streamer_name in end_stream_streamers:
                    for token in fcm_tokens.split(','):
                        if token.strip():
                            notifications_to_send.append({
                                'token': token.strip(),
                                'title': f'{streamer_name} 방송 종료',
                                'body': f'{streamer_name} 방송이 종료되었습니다',
                                'data': {
                                    'type': 'stream_end',
                                    'streamer_name': streamer_name,
                                    'platform': platform,
                                    'channel_id': channel_id,
                                    'timestamp': str(datetime.now().timestamp())
                                }
                            })
            
            # 3. 알림 전송
            if notifications_to_send:
                sender = FCMNotificationSender()
                await sender.send_notifications(notifications_to_send)
                print(f"{streamer_name} 방송 종료 알림이 {len(notifications_to_send)}명의 사용자에게 전송되었습니다.")
        
        except Exception as e:
            print(f"스트리밍 종료 알림 전송 중 오류: {e}")

    async def send_title_change_notifications(self, streamer_name: str, platform: str, 
                                            new_title: str, channel_id: str) -> None:
        """방송 제목 변경 알림을 전송합니다."""
        try:
            # 1. Supabase에서 해당 스트리머에 대한 알림 설정이 있는 사용자 가져오기
            supabase = create_client(self.supabase_url, self.supabase_key)
            users = supabase.table('userStateData').select('*').execute()
            
            # 사용자 데이터를 DataFrame으로 변환
            df = pd.DataFrame(users.data)
            if df.empty:
                return
            
            # 2. 방제 변경 알림 설정이 있는 사용자 필터링
            notifications_to_send = []
            
            for _, user in df.iterrows():
                fcm_tokens = user.get('fcm_tokens', '')
                if not fcm_tokens:
                    continue
                
                # 푸시 알림 설정 확인
                try:
                    push_settings = json.loads(user.get('push_notification_settings', '{}'))
                    if not push_settings.get('방제 변경 알림', True):  # 기본값은 활성화
                        continue
                except:
                    # 설정이 없으면 기본적으로 알림 활성화
                    pass
                
                # 해당 스트리머에 대한 알림 설정 확인
                title_change_streamers = user.get('방제 변경 알림', '').split(', ')
                if streamer_name in title_change_streamers:
                    for token in fcm_tokens.split(','):
                        if token.strip():
                            notifications_to_send.append({
                                'token': token.strip(),
                                'title': f'{streamer_name} 방제 변경',
                                'body': new_title,
                                'data': {
                                    'type': 'title_change',
                                    'streamer_name': streamer_name,
                                    'platform': platform,
                                    'title': new_title,
                                    'channel_id': channel_id,
                                    'timestamp': str(datetime.now().timestamp())
                                }
                            })
            
            # 3. 알림 전송
            if notifications_to_send:
                sender = FCMNotificationSender()
                await sender.send_notifications(notifications_to_send)
                print(f"{streamer_name} 방제 변경 알림이 {len(notifications_to_send)}명의 사용자에게 전송되었습니다.")
        
        except Exception as e:
            print(f"방제 변경 알림 전송 중 오류: {e}")

    async def send_youtube_upload_notifications(self, channel_name: str, video_title: str, 
                                              thumbnail_url: str, video_id: str) -> None:
        """유튜브 업로드 알림을 전송합니다."""
        try:
            # 1. Supabase에서 해당 채널에 대한 알림 설정이 있는 사용자 가져오기
            supabase = create_client(self.supabase_url, self.supabase_key)
            users = supabase.table('userStateData').select('*').execute()
            
            # 사용자 데이터를 DataFrame으로 변환
            df = pd.DataFrame(users.data)
            if df.empty:
                return
            
            # 2. 유튜브 알림 설정이 있는 사용자 필터링
            notifications_to_send = []
            
            for _, user in df.iterrows():
                fcm_tokens = user.get('fcm_tokens', '')
                if not fcm_tokens:
                    continue
                
                # 푸시 알림 설정 확인
                try:
                    push_settings = json.loads(user.get('push_notification_settings', '{}'))
                    if not push_settings.get('유튜브 알림', True):  # 기본값은 활성화
                        continue
                except:
                    # 설정이 없으면 기본적으로 알림 활성화
                    pass
                
                # 해당 채널에 대한 알림 설정 확인
                try:
                    youtube_settings = json.loads(user.get('유튜브 알림', '{}'))
                    send_notification = False
                    
                    for channel_id, channels in youtube_settings.items():
                        if channel_name in channels:
                            send_notification = True
                            break
                    
                    if not send_notification:
                        continue
                except:
                    continue
                
                for token in fcm_tokens.split(','):
                    if token.strip():
                        notifications_to_send.append({
                            'token': token.strip(),
                            'title': f'{channel_name} 유튜브 업로드',
                            'body': video_title,
                            'data': {
                                'type': 'youtube_upload',
                                'channel_name': channel_name,
                                'video_title': video_title,
                                'thumbnail_url': thumbnail_url,
                                'video_id': video_id,
                                'timestamp': str(datetime.now().timestamp())
                            }
                        })
            
            # 3. 알림 전송
            if notifications_to_send:
                sender = FCMNotificationSender()
                await sender.send_notifications(notifications_to_send)
                print(f"{channel_name} 유튜브 업로드 알림이 {len(notifications_to_send)}명의 사용자에게 전송되었습니다.")
        
        except Exception as e:
            print(f"유튜브 업로드 알림 전송 중 오류: {e}")

    async def send_vod_upload_notifications(self, streamer_name: str, vod_title: str, 
                                          thumbnail_url: str, vod_id: str) -> None:
        """VOD 업로드 알림을 전송합니다."""
        try:
            # 1. Supabase에서 해당 스트리머에 대한 알림 설정이 있는 사용자 가져오기
            supabase = create_client(self.supabase_url, self.supabase_key)
            users = supabase.table('userStateData').select('*').execute()
            
            # 사용자 데이터를 DataFrame으로 변환
            df = pd.DataFrame(users.data)
            if df.empty:
                return
            
            # 2. VOD 알림 설정이 있는 사용자 필터링
            notifications_to_send = []
            
            for _, user in df.iterrows():
                fcm_tokens = user.get('fcm_tokens', '')
                if not fcm_tokens:
                    continue
                
                # 푸시 알림 설정 확인
                try:
                    push_settings = json.loads(user.get('push_notification_settings', '{}'))
                    if not push_settings.get('치지직 VOD', True):  # 기본값은 활성화
                        continue
                except:
                    # 설정이 없으면 기본적으로 알림 활성화
                    pass
                
                # 해당 스트리머에 대한 알림 설정 확인
                try:
                    vod_settings = json.loads(user.get('치지직 VOD', '{}'))
                    send_notification = False
                    
                    for channel_id, streamers in vod_settings.items():
                        if streamer_name in streamers:
                            send_notification = True
                            break
                    
                    if not send_notification:
                        continue
                except:
                    continue
                
                for token in fcm_tokens.split(','):
                    if token.strip():
                        notifications_to_send.append({
                            'token': token.strip(),
                            'title': f'{streamer_name} VOD 업로드',
                            'body': vod_title,
                            'data': {
                                'type': 'vod_upload',
                                'streamer_name': streamer_name,
                                'vod_title': vod_title,
                                'thumbnail_url': thumbnail_url,
                                'vod_id': vod_id,
                                'timestamp': str(datetime.now().timestamp())
                            }
                        })
            
            # 3. 알림 전송
            if notifications_to_send:
                sender = FCMNotificationSender()
                await sender.send_notifications(notifications_to_send)
                print(f"{streamer_name} VOD 업로드 알림이 {len(notifications_to_send)}명의 사용자에게 전송되었습니다.")
        
        except Exception as e:
            print(f"VOD 업로드 알림 전송 중 오류: {e}")

    async def send_cafe_post_notifications(self, cafe_id: str, user_id: str, post_title: str, post_url: str) -> None:
        """카페 게시글 알림을 전송합니다."""
        try:
            # 1. Supabase에서 해당 카페 사용자에 대한 알림 설정이 있는 사용자 가져오기
            supabase = create_client(self.supabase_url, self.supabase_key)
            users = supabase.table('userStateData').select('*').execute()
            
            # 사용자 데이터를 DataFrame으로 변환
            df = pd.DataFrame(users.data)
            if df.empty:
                return
            
            # 카페 정보 가져오기 - 카페 이름을 알기 위해
            cafe_info = supabase.table('cafeData').select('*').eq('channelID', cafe_id).execute()
            cafe_name = "카페"
            if cafe_info.data:
                cafe_name = cafe_info.data[0].get('channelName', '카페')
            
            # 2. 카페 알림 설정이 있는 사용자 필터링
            notifications_to_send = []
            
            for _, user in df.iterrows():
                fcm_tokens = user.get('fcm_tokens', '')
                if not fcm_tokens:
                    continue
                
                # 푸시 알림 설정 확인
                try:
                    push_settings = json.loads(user.get('push_notification_settings', '{}'))
                    if not push_settings.get('카페 알림', True):  # 기본값은 활성화
                        continue
                except:
                    # 설정이 없으면 기본적으로 알림 활성화
                    pass
                
                # 해당 카페와 사용자에 대한 알림 설정 확인
                try:
                    cafe_settings = json.loads(user.get('cafe_user_json', '{}'))
                    send_notification = False
                    
                    if cafe_id in cafe_settings and user_id in cafe_settings.get(cafe_id, []):
                        send_notification = True
                    
                    if not send_notification:
                        continue
                except:
                    continue
                
                for token in fcm_tokens.split(','):
                    if token.strip():
                        notifications_to_send.append({
                            'token': token.strip(),
                            'title': f'{cafe_name} 새 글',
                            'body': f'{user_id}: {post_title}',
                            'data': {
                                'type': 'cafe_post',
                                'cafe_id': cafe_id,
                                'cafe_name': cafe_name,
                                'user_id': user_id,
                                'post_title': post_title,
                                'post_url': post_url,
                                'timestamp': str(datetime.now().timestamp())
                            }
                        })
            
            # 3. 알림 전송
            if notifications_to_send:
                sender = FCMNotificationSender()
                await sender.send_notifications(notifications_to_send)
                print(f"{cafe_name} 게시글 알림이 {len(notifications_to_send)}명의 사용자에게 전송되었습니다.")
        
        except Exception as e:
            print(f"카페 게시글 알림 전송 중 오류: {e}")
