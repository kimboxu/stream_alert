import asyncio
import chzzk_api
import websockets
from os import environ
from typing import Dict
from datetime import datetime
from urllib.parse import unquote
from dataclasses import dataclass, field
from improved_get_message import get_message
from json import loads, dumps, JSONDecodeError
from cmd_type import CHZZK_CHAT_CMD, CHZZK_DONATION_CMD
from make_log_api_performance import PerformanceManager
from base import  (
    initVar,
    getChzzkCookie, 
    change_field_state,
    save_airing_data, 
    if_after_time, 
    log_error,
    save_chat_command_data,
    change_nickname,
    )

from discord_webhook_sender import DiscordWebhookSender, get_list_of_urls, get_chat_json_data
from notification_service import send_push_notification
from chat_analyzer import ChatMessageWithAnalyzer

@dataclass
class ChzzkChatData:
    sock: websockets.connect = None  # 웹소켓 연결 객체
    chzzk_chat_msg_List: list = field(default_factory=list)  # 채팅 메시지 리스트
    last_chat_time: str = ""  # 마지막 채팅 시간
    sid: str = ""  # 세션 ID
    cid: str = ""  # 채널 ID
    accessToken: str = ""   # 액세스 토큰
    extraToken: str = ""    # 추가 토큰
    channel_id: str = ""    # 채널 ID
    channel_name: str = ""  # 채널 이름

# Chzzk 채팅 메시지 처리 클래스
class chzzk_chat_message(ChatMessageWithAnalyzer):
    def __init__(self, init_var: initVar, performance_manager: PerformanceManager, channel_id):
        self.init = init_var
        self.performance_manager = performance_manager
        channel_name = init_var.IDList["chzzk"].loc[channel_id, 'channelName']
        self.title_data = init_var.titleData["chzzk"]
        self.state_update_time = self.title_data.loc[channel_id, 'state_update_time']
        self.data = ChzzkChatData(channel_id=channel_id, channel_name = channel_name)
        self.DiscordWebhookSender_class = DiscordWebhookSender()
        self.post_chat_semaphore = asyncio.Semaphore(5)  # 동시 실행 제한 세마포어
        self.command_semaphore = asyncio.Semaphore(1)
        self.profile_image_cache = {}  # 프로필 이미지 캐시 (uid -> (timestamp, image_url))
        self.profile_cache_ttl = 1800  # 프로필 캐시 유효 시간 (초)
        self.tasks = []  # 비동기 태스크
        self.command_task = None
        self.command_delay = {}
        

        self.is_connect = False
        self.start_program = True

        self.setup_analyzer(channel_id, channel_name, 'chzzk')

    # 메인 실행 함수
    async def start(self):
        while True:
            if self.init.chat_json[self.data.channel_id]: 
                asyncio.create_task(change_field_state(self.init.supabase, "chat_json", self.init.chat_json, self.data.channel_id, False))
            
            # 방송이 종료되었다면 대기(5초 마다 확인)
            # if self.check_live_state_close() and not self.start_program:
            #     await asyncio.sleep(5)
            #     continue
            
            try:
                await self._connect_and_run()   # 연결 및 실행
            except Exception as e:
                await log_error(f"error in chat manager: {self.data.channel_name}.{str(e)}")
                asyncio.create_task(change_field_state(self.init.supabase, "chat_json", self.init.chat_json, self.data.channel_id))
            finally:
                await self._cleanup_tasks()  # 태스크 정리
                await asyncio.sleep(5)

    # 웹소켓 연결 및 메시지 처리 실행
    async def _connect_and_run(self):
        connect_start_msg = f"{self.data.channel_id} 방송 켜짐"
        if len(self.data.cid):
            connect_start_msg += f", 기존 cid:{self.data.cid}, 지금 {self.title_data.loc[self.data.channel_id, 'chatChannelId']}"
        # print(f"{datetime.now()} {connect_start_msg}")

        async with websockets.connect('wss://kr-ss3.chat.naver.com/chat', 
                                    subprotocols=['chat'], 
                                    ping_interval=None) as sock:
            self.data.sock = sock
            self.run_analyzer = True
            # self.data.cid = self.title_data.loc[self.data.channel_id, 'chatChannelId']

            # 채널 ID 확인 및 갱신
            await self.get_check_channel_id()
            
            if  not self.check_live_state_close() and self.title_data.loc[self.data.channel_id, 'state_update_time']['is_firstConnect'] and not await self.is_different_chatChannelId():
                await asyncio.sleep(0.1)
                return 
            
            # if not if_after_time(self.state_update_time["openDate"], sec = 60) and if_after_time(self.state_update_time["changeChatChannelIdDate"], sec = 60) and not await self.is_different_chatChannelId():
            #     return
                
            await self.change_chatChannelId()
            if not (await self.connect()):  # 연결 수립
                return 
            
            if self.title_data.loc[self.data.channel_id, 'state_update_time']['is_firstConnect']:
                self.title_data.loc[self.data.channel_id, 'state_update_time']['is_firstConnect'] = False
                asyncio.create_task(save_airing_data(self.init.supabase, self.title_data, 'chzzk', self.data.channel_id))

            message_queue = asyncio.Queue()  # 메시지 큐 생성
            if self.check_live_state_close():
                self.run_analyzer = False
            else:
                await self.start_analyzer()     # 분석기 시작

            # 필요한 비동기 태스크 생성 및 시작
            self.tasks = [
                asyncio.create_task(self._ping()),  # 핑 유지
                asyncio.create_task(self._message_receiver(message_queue)),  # 메시지 수신
                asyncio.create_task(self._message_processor(message_queue)),  # 메시지 처리
                # asyncio.create_task(self._post_chat()),  # 주석 처리된 채팅 전송
            ]
            
            await asyncio.gather(self.tasks[0], self.tasks[1])  # 태스크 실행

    # 태스크 정리 함수
    async def _cleanup_tasks(self):
        """태스크 정리 함수"""
        
        # 분석기 정리
        # try:
        #     await self.stop_analyzer()
        # except Exception as e:
        #     await log_error(f"stop_analyzer 에러 ({self.data.channel_id}): {str(e)}")
        
        # 웹소켓 연결 강제 종료 및 정리
        try:
            if self.data.sock and self.data.sock.state != websockets.protocol.State.CLOSED:
                try:
                    await self.data.sock.close()
                    await self.data.sock.wait_closed()
                except Exception as e:
                    await log_error(f"소켓 종료 중 에러: {str(e)}")
                finally:
                    print(f"{datetime.now()} CLOSED소캣 정리 완료")
                    self.data.sock = None
            elif self.data.sock and self.data.sock.state == websockets.protocol.State.CLOSING:
                await self.data.sock.wait_closed()
                print(f"{datetime.now()} CLOSING소캣 정리 완료")
                self.data.sock = None
        except Exception as e:
            await log_error(f"웹소켓 정리 에러 ({self.data.channel_id}): {str(e)}")
        
        # 모든 태스크 취소 및 완료 대기
        for task in self.tasks:
            if task and not task.done() and not task.cancelled():
                try:
                    task.cancel()
                    await asyncio.wait([task], timeout=2)
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    await log_error(f"태스크 정리 중 오류 ({self.data.channel_id}): {str(e)}")

        if self.command_task and not self.command_task.done():
            self.command_task.cancel()
        
        # 4. 태스크 리스트 초기화
        self.tasks = []
        
        # 5. 시스템 정리 완료 대기
        await asyncio.sleep(0.5)
        
        print(f"{datetime.now()} {self.data.channel_id} 연결 정리 완료")

    # 메시지 수신 태스크
    async def _message_receiver(self, message_queue: asyncio.Queue):
        async def should_close_connection():
            is_change_chatChannel = await self.check_change_chatChannel(join_time)
            is_close = self.check_live_state_close()
            is_new_chatChannel = self.title_data.loc[self.data.channel_id, 'state_update_time']['is_firstConnect'] and not is_close
            check_chat = self.init.chat_json[self.data.channel_id]
            
            is_old_chatChannel = (not if_after_time(self.state_update_time["openDate"], sec = 600) 
                                  and (if_after_time(self.data.last_chat_time, sec = 60) and not self.is_connect)
                                  and if_after_time(join_time, sec = 30))

            if (self.run_analyzer and (is_close or is_change_chatChannel or is_new_chatChannel or check_chat)):
                self.run_analyzer = False
                asyncio.create_task(self.should_offLine())
            
            if  is_change_chatChannel or is_new_chatChannel or check_chat or is_old_chatChannel:
                print(f"{datetime.now()} should_close_connection {self.data.channel_name} is_change_chatChannel:{is_change_chatChannel},is_new_chatChannel:{is_new_chatChannel}, check_chat:{check_chat},is_old_chatChannel:{is_old_chatChannel}")

            return not self.run_analyzer and (is_change_chatChannel or is_new_chatChannel or check_chat) or is_old_chatChannel

        json_loads = loads
        message_buffer = []
        buffer_size = 5  # 버퍼 크기
        buffer_timeout = 0.05  # 버퍼 타임아웃(초)
        last_buffer_flush= datetime.now().isoformat()
        join_time= datetime.now().isoformat()

        while True:
            # 논블로킹 방식으로 메시지 수신 시도
            try:
                # 연결 종료 조건 확인
                if await should_close_connection():
                    try: 
                        await self.data.sock.close()
                        await self.data.sock.wait_closed()
                        await self.stop_analyzer()
                    except Exception: pass

                if self.data.sock.state.name == 'CLOSED':
                    if self.start_program:
                        print(f"{datetime.now()} {self.data.channel_id} 연결 종료 {self.data.cid}")
                    else:
                        asyncio.create_task(log_error(f"{self.data.channel_id} 연결 종료 {self.data.cid}", webhook_url=environ['chat_post_url']))
                    break

                # 메시지 수신(1.0초 타임아웃)
                raw_message = await asyncio.wait_for(self.data.sock.recv(), timeout=1.0)
                
                self.data.last_chat_time= datetime.now().isoformat()
                parsed_message = json_loads(raw_message)
                # await message_queue.put(parsed_message)

                # 버퍼에 메시지 추가
                message_buffer.append(parsed_message)
                
                # 버퍼가 가득 찼거나 타임아웃이 발생하면 큐에 메시지 추가
                if len(message_buffer) >= buffer_size or if_after_time(last_buffer_flush, sec=buffer_timeout):
                    for msg in message_buffer:
                        await message_queue.put(msg)
                    message_buffer.clear()
                    last_buffer_flush = self.data.last_chat_time
                
            except asyncio.TimeoutError:
                # 타임아웃 발생 시 남은 버퍼 처리
                if message_buffer:
                    for msg in message_buffer:
                        await message_queue.put(msg)
                    message_buffer.clear()
                    last_buffer_flush = self.data.last_chat_time
                continue
                
            except (JSONDecodeError, ConnectionError, RuntimeError, websockets.exceptions.ConnectionClosed) as e:
                # 연결 오류 처리
                if not self.check_live_state_close():
                    asyncio.create_task(log_error(f"{datetime.now()} last_chat_time{self.data.channel_id} 2.{self.data.last_chat_time}.{str(e)}"))
                    try: 
                        await self.data.sock.close()
                        await self.data.sock.wait_closed()
                    except Exception: pass
                self.start_program = True
                try:
                    if if_after_time(self.init.platform_chat_server_last_close_time["chzzk"], sec = 600):
                        self.init.platform_chat_server_last_close_time["chzzk"] = datetime.now().isoformat()
                        asyncio.create_task(log_error(f"chhzk server error {self.data.channel_id}.{str(e)}"))
                except Exception as e:
                    asyncio.create_task(log_error(f"test chhzk server error {self.data.channel_id}.{str(e)}"))

                continue
                    
            except Exception as e:
                print(f"{datetime.now()} Error details: {type(e)}, {str(e)}")
                asyncio.create_task(log_error(f"Detailed error in message_receiver: {type(e)}, {str(e)}"))

    # 메시지 처리 태스크
    async def _message_processor(self, message_queue: asyncio.Queue):
        processing_pool = []  # 처리 중인 태스크 풀
        max_concurrent_processing = 10  # 최대 동시 처리 수
        
        while True:
            try:
                # 큐에서 메시지 가져오기
                raw_message = await message_queue.get()
                
                try:
                    # 각 메시지를 개별 태스크로 처리
                    task = asyncio.create_task(self._process_single_message(raw_message))
                    processing_pool.append(task)
                    
                    # 완료된 태스크 제거
                    processing_pool = [t for t in processing_pool if not t.done()]
                    
                    # 최대 동시 처리 수 초과 시 하나라도 완료될 때까지 대기
                    if len(processing_pool) >= max_concurrent_processing:
                        _, pending = await asyncio.wait(
                            processing_pool, 
                            return_when=asyncio.FIRST_COMPLETED
                        )
                        processing_pool = list(pending)
                    
                except Exception as e:
                    asyncio.create_task(log_error(
                        f"Error processing message: {str(e)}, {str(raw_message)}"
                    ))
                finally:
                     # 큐 작업 완료 신호
                    message_queue.task_done()
                    
            except Exception as e:
                print(f"{datetime.now()} Error in message_processor: {str(e)}")
                asyncio.create_task(log_error(f"Error in message_processor: {str(e)}"))
                await asyncio.sleep(0.1)    ## 예외 발생 시 잠시 대기

    # 단일 메시지 처리 함수
    async def _process_single_message(self, raw_message):
        try:
            # 채팅 타입 결정
            chat_cmd = raw_message['cmd']
            chat_type = self.get_chat_type(chat_cmd)

            # 메시지 유효성 검사
            if not await self.check_chat_message(raw_message, chat_type):
                return
            
            # 임시 제한 상태 확인
            if not (bdy := await self.check_TEMPORARY_RESTRICT(raw_message)):
                return
            
            # 채팅 목록 가져오기
            chzzk_chat_list = self.get_chzzk_chat_list(bdy)

            # 채팅 목록 처리
            if chzzk_chat_list:
                await self.process_chat_list(chzzk_chat_list, chat_type)
        
        except Exception as e:
            asyncio.create_task(log_error(f"Error in _process_single_message: {str(e)}, {str(raw_message)}"))

    # 채팅 타입 결정 함수
    def get_chat_type(self, chat_cmd) -> str:
        # 채팅 타입 결정
        return {
            CHZZK_CHAT_CMD['chat']: '채팅',
            CHZZK_CHAT_CMD['request_chat']: '채팅',
            CHZZK_CHAT_CMD['donation']: '후원',
            CHZZK_CHAT_CMD['ping']: '핑'
        }.get(chat_cmd, '모름')
    
    # 메시지 타입 코드 결정 함수
    def get_msgTypeCode(self, chat_data) -> str:
        # 후원 타입 결정
        msgTypeCode = chat_data.get('msgTypeCode') or chat_data.get('messageTypeCode')
        return {
            CHZZK_DONATION_CMD['chat']: '채팅',
            CHZZK_DONATION_CMD['subscribe']: '구독',
            CHZZK_DONATION_CMD['donation']: '일반후원',
            CHZZK_DONATION_CMD['product_purchase']: '상품구매',
            CHZZK_DONATION_CMD['CHAT_RESTRICTION_MSG']: '채팅제한',
            CHZZK_DONATION_CMD['subscription_gift']: '구독선물',
        }.get(msgTypeCode, '모름')

    # 채팅 메시지 확인 함수
    async def check_chat_message(self, raw_message, chat_type):
        # 핑 메시지 처리
        if chat_type == "핑": 
            await self.data.sock.send(dumps(self._CHZZK_CHAT_DICT("pong")))
            print(f"{datetime.now()} [{chat_type} - ping]")
            return False
        
        # 에러 체크
        if chat_type != "후원" and raw_message['tid'] is None:
            bdy = raw_message.get('bdy', {})
            if message := bdy.get('message'):
                asyncio.create_task(log_error(f"message_processor200len.{str(message)[:200]}"))
            return False

        return True
    
    # 임시 제한 상태 확인 함수
    async def check_TEMPORARY_RESTRICT(self, raw_message):
        # 임시 제한 처리
        bdy = raw_message.get('bdy', {})
        if isinstance(bdy, dict) and bdy.get('type') == 'TEMPORARY_RESTRICT':
            duration = bdy.get('duration', 30)
            asyncio.create_task(log_error(f"{datetime.now()} 임시 제한 상태입니다. {duration}초 동안 대기합니다."))
            await asyncio.sleep(duration)
            return {}
        return bdy

    # 채팅 목록 추출 함수
    def get_chzzk_chat_list(self, bdy):
        if isinstance(bdy, dict) and 'messageList' in bdy:
            chat_data = bdy['messageList']
            chzzk_chat_list = [msg for msg in chat_data]
        else:
            chat_data = bdy if isinstance(bdy, list) else [bdy]
            chzzk_chat_list = [msg for msg in chat_data]
        return chzzk_chat_list

    # 채팅 목록 처리 함수
    async def process_chat_list(self, chzzk_chat_list, chat_type):
        processing_tasks = []
        
        for chat_data in chzzk_chat_list:
            try:
                # 채팅 제한 메시지는 건너뜀
                if self.get_msgTypeCode(chat_data) == "채팅제한":
                    continue

                # 닉네임 가져오기
                nickname = self.get_nickname(chat_data)
                if nickname is None:
                    continue
                
                userRoleCode = self.get_userRoleCode(chat_data)

                # 채팅 메시지인 경우 분석기로 전달
                if chat_type == "채팅":
                    chat = self.get_chat(chat_data)
                    time = self.get_msgTime(chat_data)
                    if not self.init.DO_TEST and await self.chat_command(userRoleCode, nickname, chat, time):
                        continue 
                    
                    if nickname and chat:
                        # 분석기로 메시지 전달
                        await self.chat_analyzer.add_chat_message(nickname, chat, datetime.fromisoformat(time))

                # 메시지 출력
                message = self.print_msg(chat_data, chat_type)
                
                if not self.init.DO_TEST and ( userRoleCode in ["streamer", "streaming_chat_manager"]): # ((chat_type == "후원" and self.get_msgTypeCode(chat_data) != "채팅")) or userRoleCode in ["streamer", "streaming_chat_manager"]
                    asyncio.create_task(log_error(message[0], webhook_url=environ['donation_post_url']))
                # else:
                #     print(f"{datetime.now()} {message[0]}")

                # chzzk_chatFilter에 없는 사람 채팅은 제거
                chzzk_filter = self.init.chatFilter["chzzk"]
                if not self.init.DO_TEST and nickname not in chzzk_filter["channelName"].values:
                    continue

                if nickname not in chzzk_filter["channelName"].values:
                    continue

                user_id = self.get_uid(chat_data)

                if user_id not in self.init.chatFilter["chzzk"].index:
                    continue

                await change_nickname(self.init, user_id, nickname, "chzzk")

                # self.data.chzzk_chat_msg_List.append([chat_data, chat_type])
                # 채팅 전송 태스크 생성
                task = asyncio.create_task(self._post_chat(chat_data, message))
                processing_tasks.append(task)

            except Exception as e:
                asyncio.create_task(log_error(f"error process_message {chat_data}. {str(e)}"))
        
        # 모든 처리 태스크 실행
        if processing_tasks:
            await asyncio.gather(*processing_tasks, return_exceptions=True)


    # 채팅 전송 함수
    async def _post_chat(self, chat_data, message):
        try:
            async with self.post_chat_semaphore:  # 동시 실행 제한
                nickname = self.get_nickname(chat_data)
                chat = message[1]
                uid = self.get_uid(chat_data)
                
                # 프로필 이미지 가져오기
                # profile_image_task = self._get_profile_image_cached(uid)
                profile_image = await self._get_profile_image_cached(uid)
                
                # JSON 데이터 생성
                json_data = get_chat_json_data(nickname, chat, self.data.channel_name, profile_image)
                
                # URL 목록 가져오기
                list_of_urls = get_list_of_urls(self.init.DO_TEST, self.init.userStateData, 
                                            nickname, self.data.channel_id, "chat_user_json")
                
                # 푸시 알림 전송
                asyncio.create_task(send_push_notification(list_of_urls, json_data))
                # 디스코드 웹훅 전송
                webhook_task = asyncio.create_task(self.DiscordWebhookSender_class.send_messages(list_of_urls, json_data))
                webhook_task.add_done_callback(lambda t: self._handle_webhook_result(t))
                
                # print(f"{datetime.now()} post chat {message[0]}")
        except Exception as e:
            asyncio.create_task(log_error(f"error postChat: {str(e)}"))

    # 웹훅 결과 처리 함수
    def _handle_webhook_result(self, task):
        try:
            task.result()  # 예외가 있으면 여기서 발생
        except Exception as e:
            asyncio.create_task(log_error(f"Webhook task error: {str(e)}"))

    # 캐시된 프로필 이미지 가져오기
    async def _get_profile_image_cached(self, uid):
        
        # 프로필 url profile_cache_ttl 시간 동안 캐시에 재사용 가능 
        if uid in self.profile_image_cache:
            timestamp, image_url = self.profile_image_cache[uid]
            if not if_after_time(timestamp, sec = self.profile_cache_ttl):
                return image_url
        
        # 캐시에 없거나 만료된 경우 새로 가져오기
        image_url = await self._get_profile_image(uid)
        
        # 캐시 업데이트
        self.profile_image_cache[uid] = (datetime.now().isoformat(), image_url)
        return image_url

    # 핑 유지 함수
    async def _ping(self):
        ping_interval = 10  # 핑 간격(초)
        
        try:
            while self.data.sock and not self.data.sock.state.name == 'CLOSED':
                try:
                    # 핑 메시지 전송
                    await asyncio.sleep(0.0001)
                    await self.data.sock.send(dumps(self._CHZZK_CHAT_DICT("pong")))
                except websockets.exceptions.ConnectionClosedOK as e: 
                    break
                
                try:
                    await asyncio.wait_for(asyncio.shield(self.data.sock.wait_closed()), timeout=ping_interval)
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    await log_error(f"Error during ping wait: {str(e)}")
                    break
                    
        except Exception as e:
            await log_error(f"Error in ping function: {str(e)}")
        
        # print(f"{datetime.now()} {self.data.channel_id} chat pong 종료")

    # 연결 수립 함수
    async def connect(self):
        """연결 수립 함수"""
        sock_response = None
        try:
            # 액세스 토큰과 추가 토큰 가져오기
            self.data.accessToken, self.data.extraToken = chzzk_api.fetch_accessToken(self.data.cid, getChzzkCookie())
            
            # 연결 요청 전송
            await self.data.sock.send(dumps(self._CHZZK_CHAT_DICT("connect")))
            sock_response = loads(await self.data.sock.recv())
            self.data.sid = sock_response['bdy']['sid']
            
            # 최근 메시지 요청
            await self.data.sock.send(dumps(self._CHZZK_CHAT_DICT("recentMessageCount", num = 50)))
            sock_response = loads(await self.data.sock.recv())

            # 임시 제한 상태 확인
            bdy = await self.check_TEMPORARY_RESTRICT(sock_response)
            chzzk_chat_list = self.get_chzzk_chat_list(bdy)

            if chzzk_chat_list and self.get_nickname(chzzk_chat_list[0]) == "(알 수 없음)" and chzzk_chat_list[0].get('msg', chzzk_chat_list[0].get('content', '')) == "채팅방이 생성되었습니다.":
                self.is_connect = True
            else:
                self.is_connect = False
            try:
                if chzzk_chat_list:
                    messageTime = chzzk_chat_list[-1].get('messageTime') or chzzk_chat_list[-1].get('msgTime')
                    self.data.last_chat_time = datetime.fromtimestamp(messageTime/1000).isoformat()
                    
                    if not self.start_program:
                        # 최근 채팅 3개 샘플 출력
                        print(f"{datetime.now()} {self.data.channel_id} 최근 채팅 {len(chzzk_chat_list)}개 확인:")
                        for i, chat in enumerate(chzzk_chat_list[-3:]):  # 최근 3개
                            nickname = self.get_nickname(chat)
                            content = chat.get('msg', chat.get('content', ''))
                            chat_time = chat.get('messageTime', chat.get('msgTime', 0))
                            time_str = datetime.fromtimestamp(chat_time/1000).strftime('%H:%M:%S')
                            print(f"  [{time_str}] {nickname}: {content}")
                else:
                    self.data.last_chat_time = datetime.now().isoformat()
                    print(f"{datetime.now()} {self.data.channel_id} 새로 시작된 방송이거나 채팅 활동이 없는 상태")
                    
            except Exception as e: 
                print(f"messageTime 처리 오류 {str(e)}")
                self.data.last_chat_time = datetime.now().isoformat()
                
            if self.start_program:
                print(f"{datetime.now()} {self.data.channel_id} 연결 완료 {self.data.cid}")
                self.start_program = False
            else:
                asyncio.create_task(log_error(f"{self.data.channel_id} 연결 완료 {self.data.cid}", is_Do_test = self.init.DO_TEST, webhook_url=environ['chat_post_url']))
                
            return True

        except Exception as e:
            print(f"{datetime.now()} {self.data.channel_id} 연결 실패: {str(e)}, sock_response:{sock_response}")
            return False

    # 메시지 전송 함수
    async def _send(self, message, command = None, time = datetime.now().timestamp()):
        # 기본 딕셔너리
        default_dict = {
            "ver": 2,
            "svcid": "game",
            "cid": self.data.cid,
        }

        # 추가 정보
        extras = {
            "chatType": "STREAMING",
            "emojis": "",
            "osType": "PC",
            "extraToken": self.data.extraToken,
            "streamingChannelId": self.data.cid
        }

        # 전송 딕셔너리
        send_dict = {
            "tid": 3,
            "cmd": CHZZK_CHAT_CMD['send_chat'],
            "retry": False,
            "sid": self.data.sid,
            "bdy": {
                "msg": "[" + message + "]",
                "msgTypeCode": 1,
                "extras": dumps(extras),
                "msgTime": int(datetime.now().timestamp())
            }
        }
        if command:
            self.command_delay[command] = time
            
        await self.data.sock.send(dumps(dict(send_dict, **default_dict)))

    # Chzzk 채팅 딕셔너리 생성 함수
    def _CHZZK_CHAT_DICT(self, option = "connect", num = 50):
        default_dict = {
            "ver": "2",
            "svcid": "game",
            "cid": self.data.cid,
        }
        if option == "connect":
            # 연결 요청 딕셔너리
            send_dict = {
                "cmd": CHZZK_CHAT_CMD['connect'],
                "tid": 1,
                "bdy": {
                    "uid": chzzk_api.fetch_userIdHash(getChzzkCookie()),
                    "devType": 2001,
                    "accTkn": self.data.accessToken,
                    "auth": "SEND"
                }
            } 
        elif option == "recentMessageCount":
            # 최근 메시지 요청 딕셔너리
            send_dict = {
                "cmd": CHZZK_CHAT_CMD['request_recent_chat'],
                "tid": 2,
                "sid": self.data.sid,
                "bdy": {
                    "recentMessageCount": num
                }
            }
        elif option == "pong":
            # 핑 응답 딕셔너리
            return {
                "ver" : "2",
                "cmd" : CHZZK_CHAT_CMD['pong']
                }
        
        return dict(send_dict, **default_dict)

    # 프로필 이미지 가져오기 함수
    async def _get_profile_image(self, uid):
        def chzzk_getLink(uid):
            return f'https://api.chzzk.naver.com/service/v1/channels/{uid}'
        
        data = await get_message(self.performance_manager, "chzzk", chzzk_getLink(uid))
        profile_image = data["content"]["channelImageUrl"]

        # 유효한 프로필 이미지 확인
        if profile_image and profile_image.startswith(("https://nng-phinf.pstatic.net", "https://ssl.pstatic.net")):
            return profile_image

        # 기본 프로필 이미지 사용
        profile_image = environ['default_thumbnail']

        return profile_image
    
    # 채널 ID 확인 함수
    async def get_check_channel_id(self) -> int:
        try:
            # 채널 코드로부터 채팅 채널 ID 가져오기
            self.data.cid = chzzk_api.fetch_chatChannelId(self.init.IDList["chzzk"].loc[self.data.channel_id, "uid"], getChzzkCookie())
            return True
            
        except Exception as e: 
            asyncio.create_task(log_error(f"error get_check_channel_id {self.data.channel_id}.{str(e)}"))
        return False

    # 채팅 채널 ID 가 다른지
    async def is_different_chatChannelId(self, cid = None):
        if cid is None:
            cid = self.data.cid

        if cid != self.title_data.loc[self.data.channel_id, 'chatChannelId']:
            return True
        return False
    
    # 채팅 채널 ID 변경 함수
    async def change_chatChannelId(self, cid = None):
        if cid is None:
            cid = self.data.cid

        if cid != self.title_data.loc[self.data.channel_id, 'chatChannelId']:
            self.title_data.loc[self.data.channel_id, 'oldChatChannelId'] = self.title_data.loc[self.data.channel_id, 'chatChannelId']
            self.title_data.loc[self.data.channel_id, 'chatChannelId'] = cid
            self.state_update_time["changeChatChannelIdDate"] = datetime.now().isoformat()
            asyncio.create_task(save_airing_data(self.init.supabase, self.title_data, 'chzzk', self.data.channel_id))
            return True
        return False

    # 프로필 데이터 가져오기 함수
    def get_profile_data(self, chat_data):
        profile_data = chat_data.get('profile', {})
        #AOS환경의 채팅인 경우 profile_data가 str형의 null인 경우가 있음
        if profile_data is None or profile_data == "null":
            profile_data = {}

        elif isinstance(profile_data, str):
            profile_data = unquote(profile_data)
            profile_data = loads(profile_data)

        return profile_data

    # 사용자 역할 코드 가져오기 함수
    def get_userRoleCode(self, chat_data):
        #streamer, streaming_chat_manager, common_user
        profile_data = self.get_profile_data(chat_data)
        return profile_data.get('userRoleCode', None)

    # 닉네임 가져오기 함수
    def get_nickname(self, chat_data):
        nick_name = "(알 수 없음)"
        if not chat_data.get('extras', {}) or loads(chat_data['extras']).get('styleType', {}) in [1, 2, 3]:
            return nick_name
            
        # 익명 사용자 처리
        user_id = chat_data.get('uid', chat_data.get('userId'))
        if user_id == 'anonymous':
            return '익명의 후원자'
        
        # 프로필 데이터 파싱 및 검증
        profile_data = self.get_profile_data(chat_data)
        return profile_data.get('nickname', nick_name)

    # 채팅 내용 가져오기 함수
    def get_chat(self, chat_data) -> str:
        if 'msg' in chat_data:
            msg = chat_data['msg']
        elif 'content' in chat_data:
            msg = chat_data['content']
        else:
            return None

        if msg and msg[0] in [">"]:
            msg = "/" + msg
        return msg

    # 사용자 ID 가져오기 함수
    def get_uid(self, chat_data) -> str:
        return chat_data.get('uid') or chat_data.get('userId')
    
    def get_msgTime(self, chat_data) -> int:
        seconds = chat_data.get('msgTime') or chat_data.get('messageTime')
        time = datetime.fromtimestamp(seconds/1000).isoformat()
        return time

    # 결제 금액 가져오기 함수
    def get_payAmount(self, chat_data, chat_type) -> str:
        if chat_type == "후원": payAmount = loads(chat_data['extras'])['payAmount']
        else: payAmount = None
        return payAmount

   # 메시지 출력 형식 함수 - 채팅 메시지의 타입에 따라 적절한 형식으로 변환
    def print_msg(self, chat_data, chat_type) -> str:

        # 일반 채팅 메시지 처리
        if chat_type == "채팅":
            msg = chat_data.get('msg') or chat_data.get('content')  # 메시지 내용 가져오기
            time = self.get_msgTime(chat_data)  # 메시지 시간 가져오기
            return self.format_message('채팅', chat_type, self.get_nickname(chat_data), message=msg, time=time)
        
        # 후원 메시지 처리
        if chat_type == "후원":
            extras = loads(chat_data['extras'])  # 추가 정보 파싱
            msg_type_code = self.get_msgTypeCode(chat_data)  # 메시지 타입 코드 가져오기
            
            # 메시지 타입에 따른 핸들러 매핑
            handlers = {
                "일반후원": self._handle_donation,       # 일반 후원 처리
                "구독": self._handle_subscription,       # 구독 처리
                "구독선물": self._handle_gift_subscription,  # 구독 선물 처리
                "상품구매": self._handle_product_purchase,  # 상품 구매 처리
                "채팅": self._handle_chat                # 채팅 처리
            }
            
            # 적절한 핸들러 선택 (없으면 _handle_unknown 사용)
            handler = handlers.get(msg_type_code, self._handle_unknown)
            
            # 핸들러 실행하여 결과 반환
            return handler(chat_data, chat_type, extras)
        
        # 알 수 없는 메시지 타입인 경우
        return "print_msg 채팅도 후원도 아닌 무언가 현재는 확인X"

    # 메시지 포맷팅 함수 - 다양한 메시지 타입에 맞는 형식으로 문자열 생성
    def format_message(self, msg_type, chat_type, nickname, **kwargs):
        base = f"[{chat_type} - {self.data.channel_name}] {nickname}"

        message = kwargs.get("message", "(메시지 없음)") 
        time = kwargs.get("time")
        amount = kwargs.get("amount")
        missionText = kwargs.get("missionText")
        partyName = kwargs.get("partyName")
        month = kwargs.get("month")
        giftTierName = kwargs.get("giftTierName")
        quantity = kwargs.get("quantity")
        receiverNickname = kwargs.get("receiverNickname")
        productName = kwargs.get("productName")
        orderAmount = kwargs.get("orderAmount")

        templates = {
            "후원채팅": f"({amount}치즈)",
            "영상후원": f"({amount}치즈) 영상후원",
            "후원미션걸기": f"({missionText} 모금함 미션 생성 {amount}치즈)",
            "후원미션추가": f"({missionText} 모금함 미션에 {amount}치즈 추가)",
            "파티후원": f"({partyName} 파티에 {amount}치즈 후원)",
            "구독": f"({month}개월 동안 구독)",
            "구독선물": f"({giftTierName}구독권 {quantity}개 선물)",
            "단일구독선물": f"({receiverNickname}님에게 {giftTierName}구독권 선물)",
            "상품구매": f"{productName} {orderAmount}원 구매!",
        }

        extra = templates.get(msg_type, "")
        
        full = f"{base} {extra}: {message}, {time}"
        short = f"{extra}: {message}" if extra else message

        return [full, short]

    # 일반 후원 처리 함수 - 후원 타입에 따라 적절한 메시지 형식 반환
    def _handle_donation(self, chat_data, chat_type, extras: Dict):
        donation_type = extras.get('donationType')  # 후원 타입 가져오기
        
        # 후원 타입별 핸들러 정의
        donation_handlers = {
            # 일반 후원 채팅
            "CHAT": lambda: self.format_message(
                "후원채팅", 
                chat_type,
                self.get_nickname(chat_data),
                message=chat_data['msg'],
                time=chat_data['msgTime'],
                amount=extras['payAmount']
            ),
            # 영상 후원
            "VIDEO": lambda: self.format_message(
                "영상후원",
                chat_type,
                self.get_nickname(chat_data),
                message=chat_data['msg'],
                time=chat_data['msgTime'],
                amount=extras['payAmount']
            ),
            # 모금함 미션 생성
            "MISSION": lambda: self.format_message(
                "후원미션걸기",
                chat_type,
                self.get_nickname(chat_data),
                message=chat_data['msg'],
                time=chat_data['msgTime'],
                amount=extras['payAmount'],
                missionText=extras['missionText']
            ),
            # 모금함 미션 참여
            "MISSION_PARTICIPATION": lambda: self.format_message(
                "후원미션추가",
                chat_type,
                self.get_nickname(chat_data),
                message=chat_data['msg'],
                time=chat_data['msgTime'],
                amount=extras['payAmount'],
                missionText=extras['missionText']
            ),
            # 파티후원
            "PARTY": lambda: self.format_message(
                "파티후원",
                chat_type,
                self.get_nickname(chat_data),
                message=chat_data['msg'],
                time=chat_data['msgTime'],
                amount=extras['payAmount'],
                partyName=extras['partyName']
            ),
        }
        
        # 적절한 핸들러 선택 및 실행
        handler = donation_handlers.get(donation_type)
        if handler:
            return handler()
        
        # 알 수 없는 후원 타입 처리
        asyncio.create_task(log_error(f"Unknown donation type: {donation_type}"))
        print(chat_data)
        return self.format_message(
            "후원채팅",
            chat_type,
            self.get_nickname(chat_data),
            message=chat_data['msg'],
            time=chat_data['msgTime'],
            amount=extras['payAmount']
        )

    # 구독 처리 함수 - 구독 메시지 형식으로 반환
    def _handle_subscription(self, chat_data, chat_type, extras: Dict):
        tierName = extras["tierName"]  # 구독 티어 이름
        tierNo = extras["tierNo"]      # 구독 티어 번호
        return self.format_message(
            "구독",
            chat_type,
            self.get_nickname(chat_data),
            message=chat_data['msg'],
            time=chat_data['msgTime'],
            month=extras['month']  # 구독 개월 수
        )

    # 구독 선물 처리 함수 - 구독 선물 타입에 따라 적절한 메시지 형식 반환
    def _handle_gift_subscription(self, chat_data, chat_type, extras: Dict):
        # 구독 선물 타입 확인
        if extras.get('giftType') == 'SUBSCRIPTION_GIFT':
            # 다수 대상 구독 선물
            return self.format_message(
                "구독선물",
                chat_type,
                self.get_nickname(chat_data),
                message=chat_data['msg'],
                time=chat_data['msgTime'],
                giftTierName=extras['giftTierName'],  # 선물한 구독권 티어 이름
                quantity=extras["quantity"],          # 선물한 구독권 수량
            )
        elif extras.get('giftType') == 'SUBSCRIPTION_GIFT_RECEIVER':
            # 단일 대상 구독 선물
            return self.format_message(
                "단일구독선물",
                chat_type,
                self.get_nickname(chat_data),
                message=chat_data['msg'],
                time=chat_data['msgTime'],
                giftTierName=extras['giftTierName'],        # 선물받은 구독권 티어 이름
                receiverNickname=extras['receiverNickname'], # 수신자 닉네임
            )
        
        # 알 수 없는 구독 선물 타입 처리
        asyncio.create_task(log_error(f"Unknown gift subscription type: "))
        print(f"{datetime.now()} Unknown gift subscription type: {chat_data}")
        return f"print_msg 어떤 메시지인지 현재는 확인X.{self.data.channel_name}.{self.get_nickname(chat_data)}.{extras}"

    def _handle_product_purchase(self, chat_data, chat_type, extras: Dict):
        return self.format_message(
            '상품구매', 
            chat_type, 
            self.get_nickname(chat_data), 
            message=chat_data['msg'], 
            time=chat_data['msgTime'],
            productName=extras.get('productName'),
            orderAmount=extras.get('orderAmount'),
        )
    # 일반 채팅 처리 함수 - 기본 채팅 메시지 형식으로 반환
    def _handle_chat(self, chat_data, chat_type, extras):
        return self.format_message(
            '채팅', 
            chat_type, 
            self.get_nickname(chat_data), 
            message=chat_data['msg'], 
            time=chat_data['msgTime']
        )

    # 알 수 없는 메시지 타입 처리 함수 - 오류 로깅 후 기본 메시지 형식 반환
    def _handle_unknown(self, chat_data, chat_type, extras):
        asyncio.create_task(log_error(f"Unknown _handle_unknowne: {self.get_msgTypeCode(chat_data)}.{chat_type}"))
        print(f"{datetime.now()} Unknown _handle_unknowne: {chat_data}")
        return f"print_msg 어떤 메시지인지 현재는 확인X.{self.data.channel_name}.{self.get_nickname(chat_data)}.{extras}"

    # 챗팅 명령어
    async def chat_command(self, userRoleCode: str, nickname: str, chat: str, time: int) -> bool:
        # 빅헤드가 아니면 동작 안함
        if (nickname == "ai코딩" and chat[0] == "[" and chat[-1] == "]"):
            return True
        
        if self.data.channel_id not in ["bighead033", "kimboxu"]:
            return
        
        special_command_list = ["!업타임", "!방제", "!명령어", "!카테고리", "!게임", "!삭제", "!추가", "!수정"]

        # 명령어 수정 기능
        sp_chat = chat.split(" ")
        command = sp_chat[0]
        if command == "!멤버수정" or (len(sp_chat) >= 2 and sp_chat[1] == "수정") and (command == "!멤버" or self.is_authority(userRoleCode, nickname)):
            if (len(sp_chat) == 2 and command == "!멤버") or (len(sp_chat) == 1 and command == "!멤버수정"):
                save_text = " "
            elif command == "!멤버수정":
                command = "!멤버"
                save_text = " ".join(sp_chat[1:])
            else:
                save_text = " ".join(sp_chat[2:])

            if not self.is_sendMSG_time(command, time):
                return
            
            await self._send(f"{save_text}(으)로 변경")
            self.init.chat_commands["chzzk"].loc[self.data.channel_id, "chat_command"][command] = save_text
            await save_chat_command_data(self.init.supabase, self.init.chat_commands, self.data.channel_id, "chzzk")
            return
        
        if len(sp_chat) >= 2 and command in ["!수정"] and sp_chat[1] == "!멤버":
            await self.fix_command(chat_command, sp_chat)
            return
        
        chat_command = self.init.chat_commands["chzzk"].loc[self.data.channel_id, "chat_command"]
        # 메시지 보네기
        if len(sp_chat) == 1 and command in list(chat_command.keys()) + special_command_list:
            if not self.is_sendMSG_time(command, time):
                return
            
            if command in special_command_list:
                if command == "!업타임":
                    await self.uptime_command(command, time)
                    return

                if command == "!방제":
                    await self.title_command(command, time)
                    return
                
                if command == "!명령어":
                    if self.command_task and not self.command_task.done():
                        return
                    self.command_task = asyncio.create_task(self.command_list(chat_command, special_command_list, command, time))
                    return

                if command in ["!카테고리", "!게임"]:
                    await self.category_command(command, time)
                    return
                
            send_command = chat_command[command]
            await self._send(send_command, command, time)

        elif self.is_authority(userRoleCode, nickname) and len(sp_chat) == 2 and command in ["!삭제"]:
            if not self.is_sendMSG_time(command, time):
                return
            
            await self.del_command(chat_command)
            return

        elif self.is_authority(userRoleCode, nickname) and len(sp_chat) >= 2 and command in ["!추가", "!수정"]:
            if not self.is_sendMSG_time(command, time):
                return
            
            if command == "!추가":
                await self.add_command(sp_chat)
                return
            if command == "!수정":
                await self.fix_command(chat_command, sp_chat)
                return
        return

    def is_authority(self, userRoleCode, nickname):
        return (userRoleCode in ["streamer", "streaming_chat_manager"] or nickname == "ai코딩")

    async def uptime_command(self, command, time):
        if self.check_live_state_close():
            await self._send("채널이 오프라인 상태입니다.")
            return
        start_time_str = self.title_data.loc[self.data.channel_id, 'state_update_time']['openDate']
        current_time = datetime.now()
        start_time = datetime.fromisoformat(start_time_str)
        uptime = current_time - start_time

        def format_time(seconds: int) -> str:
            # 시간, 분, 초로 변환
            hours = seconds // 3600
            remaining_seconds = seconds % 3600
            minutes = remaining_seconds // 60
            secs = remaining_seconds % 60
            
            # 0이 아닌 항목만 포함하여 출력
            parts = ["업타임 : "]
            
            if hours > 0:
                parts.append(f"{hours}시간")
            if minutes > 0:
                parts.append(f"{minutes}분")
            if secs > 0 or not parts:  # 0초만 남은 경우도 표시
                parts.append(f"{secs}초")

            return " ".join(parts)
            
        await self._send(format_time(int(uptime.total_seconds())), command, time)
    
    async def title_command(self, command, time):
        title = self.title_data.loc[self.data.channel_id, 'title1']
        
        await self._send("방제 : " + title, command, time)

    async def command_list(self, chat_command, special_command_list, command, time):
        commands = list(chat_command.keys()) + special_command_list

        async with self.command_semaphore:
            for msg in self.split_message(commands):
                await self._send(msg, command, time)
                await asyncio.sleep(0.5)

    def split_message(self, items, sep=",", max_len=100):
        result = []
        buffer = ""

        for item in items:
            next_part = item if not buffer else sep + item

            # [] 포함 길이 고려 (-2)
            if len(buffer) + len(next_part) > max_len - 2:
                result.append(buffer)
                buffer = item
            else:
                buffer += next_part

        if buffer:
            result.append(buffer)

        return result

    async def category_command(self, command, time):
        category = self.title_data.loc[self.data.channel_id, 'category']
        await self._send("카테고리 : " + category, command, time)

    async def add_command(self, sp_chat):
        if sp_chat[1] not in self.init.chat_commands["chzzk"].loc[self.data.channel_id, "chat_command"]:
            if len(sp_chat) == 2:
                save_text = " "
            else:
                save_text = " ".join(sp_chat[2:])

            self.init.chat_commands["chzzk"].loc[self.data.channel_id, "chat_command"][sp_chat[1]] = save_text
            await save_chat_command_data(self.init.supabase, self.init.chat_commands, self.data.channel_id, "chzzk")
            await self._send(f"명령어 {sp_chat[1]}(이)가 추가 되었습니다.")
        else:
            await self._send(f"{sp_chat[1]} 명령어는 이미 있습니다.")

    async def fix_command(self, sp_chat):
        if sp_chat[1] in self.init.chat_commands["chzzk"].loc[self.data.channel_id, "chat_command"]:
            if len(sp_chat) == 2:
                save_text = " "
            else:
                save_text = " ".join(sp_chat[2:])
        
            self.init.chat_commands["chzzk"].loc[self.data.channel_id, "chat_command"][sp_chat[1]] = save_text
            await self._send(f"{save_text}(으)로 변경")
            await save_chat_command_data(self.init.supabase, self.init.chat_commands, self.data.channel_id, "chzzk")
        else:
            await self._send(f"{sp_chat[1]} 명령어는 없습니다.")

    async def del_command(self, chat_command):
        if chat_command in self.init.chat_commands["chzzk"].loc[self.data.channel_id, "chat_command"]:
            del self.init.chat_commands["chzzk"].loc[self.data.channel_id, "chat_command"][chat_command]
            await self._send(f"{chat_command}(이)가 삭제되었습니다.")
            await save_chat_command_data(self.init.supabase, self.init.chat_commands, self.data.channel_id, "chzzk")
        else:
            await self._send(f"{chat_command} 명령어는 없습니다.")

    def is_sendMSG_time(self, command, time):
        if command not in self.command_delay:
            self.command_delay[command] = time
            return True
        
        return if_after_time(self.command_delay[command], sec = 1)
        

    # 채팅방 입장 시 인사 메시지 전송 함수
    async def sendHi(self, himent):
        if await self.get_check_channel_id():  # 채널 ID 확인
            await self.change_chatChannelId()  # 채널 ID 갱신
            asyncio.create_task(log_error(f"send hi {self.init.IDList['chzzk'].loc[self.data.channel_id, 'channelName']} {self.data.cid}"))
            await self._send(himent)  # 인사 메시지 전송

    # 방송 시작 시 자동 인사 메시지 함수
    async def onAirChat(self, message):
        if message != "뱅온!":
            return
        
        greeting_map = {
            "charmel": "챠하",
            "mawang0216": "마하",
            "bighead033": "빅하"
        }
        
        himent = greeting_map.get(self.data.channel_id)
        if himent:
            await self._send(himent)

    # 방송 종료 시 자동 작별 인사 메시지 함수
    async def offAirChat(self):
        farewell_map = {
            "charmel": "챠바",
            "mawang0216": "마바",
            "bighead033": "빅바"
        }
        
        byement = farewell_map.get(self.data.channel_id)
        if byement:
            await self._send(byement)

    # 방송 상태가 종료인지 확인하는 함수
    def check_live_state_close(self):
        try:
            # 채널의 라이브 상태가 "CLOSE"인지 확인
            return self.title_data.loc[self.data.channel_id, 'live_state'] == "CLOSE"
        except Exception as e:
            # 예외 발생 시 로그 기록 후 기본값으로 True(종료) 반환
            asyncio.create_task(log_error(f"Error in check_live_state_close: {str(e)}"))
            return True
        
    async def check_change_chatChannel(self, connect_time):
        if not if_after_time(self.state_update_time["openDate"], sec = 60) and if_after_time(connect_time, sec = 60):
            cid = chzzk_api.fetch_chatChannelId(self.init.IDList["chzzk"].loc[self.data.channel_id, "uid"], getChzzkCookie())
            if await self.is_different_chatChannelId(cid):
                print(f"{datetime.now()} check {self.data.channel_id},{self.data.cid},cid check_live_state_close")
                # asyncio.create_task(change_field_state("chat_json", self.init.chat_json, self.data.channel_id))
                return True
        return False

#일반 채팅 처리 함수(디버깅 용도)
async def generic_chat(init: initVar, performance_manager: PerformanceManager, platform: str):
    await asyncio.sleep(3)
    
    tasks = {}  # 채널 ID별 실행 중인 task를 관리할 딕셔너리
    
    while True:
        try:
            # 기존 실행 중인 태스크를 유지하면서, 새로운 채널이 추가되면 실행
            for channel_id in init.IDList[platform]["channelID"]:
                if channel_id not in tasks or tasks[channel_id].done():
                    # StateManager를 활용하여 인스턴스 생성/재사용
                    chat_instance = chzzk_chat_message(init, performance_manager, channel_id)
                    tasks[channel_id] = asyncio.create_task(chat_instance.start())
            
            await asyncio.sleep(1)  # 1초마다 체크
        
        except Exception as e:
            print(f"{datetime.now()} error {platform}_chatf {str(e)}")
            await asyncio.create_task(log_error(f"Error in {platform}_chatf: {str(e)}"))
            await asyncio.sleep(1)

# 메인 함수 - 프로그램 실행(디버깅 용도)
async def main():
    # 상태 관리자 인스턴스 가져오기
    from shared_state import StateManager
    state_manager = StateManager.get_instance()
    init = state_manager.get_init()
    init = await state_manager.initialize()
    performance_manager = state_manager.get_performance_manager()
    
    # 초기화 및 데이터 로드
    
    await asyncio.sleep(1)  # 초기화 완료 후 1초 대기(간혹 바로 프로그램 실행시 초기화 단계에서 오류 발생 하는 것 같아서)
    
    # 치지직 채팅 처리 태스크 시작
    await asyncio.create_task(generic_chat(init, performance_manager, 'chzzk'))
        
# 스크립트가 직접 실행된 경우 메인 함수 실행
if __name__ == "__main__":
    asyncio.run(main())