import ssl 
import base
import certifi
import asyncio
import websockets
from time import time
from os import environ
from json import loads
from requests import post
from datetime import datetime
from supabase import create_client
from dataclasses import dataclass, field
from discord_webhook_sender import DiscordWebhookSender, get_list_of_urls, get_chat_json_data
from my_app import send_push_notification

@dataclass
class afreecaChatData:
    sock: websockets.connect = None
    afreeca_chat_msg_List: list = field(default_factory=list)  
    processed_messages: list = field(default_factory=list)
    last_chat_time: str = ""
    channel_id: str = ""
    channel_name: str = ""
    BNO: str = ""
    BID: str = ""
    
class afreeca_chat_message:
    def __init__(self, init_var: base.initVar, channel_id):
        self.init = init_var

        self.ssl_context = self.create_ssl_context()
        self.F = "\x0c"
        self.ESC = "\x1b\t"
        self.PING_PACKET = f'{self.ESC}000000000100{self.F}'
        channel_name = self.init.afreecaIDList.loc[channel_id, 'channelName']
        self.data = afreecaChatData(channel_id = channel_id, channel_name = channel_name)
        self.post_chat_semaphore = asyncio.Semaphore(5)
        self.tasks = []
        # self.stream_end_time = {}  # 각 스트리머의 방송 종료 시간을 저장할 딕셔너리

    @staticmethod
    def create_ssl_context():
        ssl_context = ssl.create_default_context()
        ssl_context.load_verify_locations(certifi.where())
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        return ssl_context
    
    async def start(self):
        while True:
            if self.init.chat_json[self.data.channel_id]: 
                await base.change_chat_join_state(self.init.chat_json, self.data.channel_id, False)

            if self.check_live_state_close() or await self.check_is_passwordDict():
                await asyncio.sleep(5)
                continue

            self.data.BNO = self.init.afreeca_titleData.loc[self.data.channel_id, 'chatChannelId']
            self.data.BID = self.init.afreecaIDList["afreecaID"][self.data.channel_id]

            channel_data = self.afreeca_getChannelStateData()
            if_adult_channel, TITLE, thumbnail_url, self.CHDOMAIN, self.CHATNO, FTK, BJID, self.CHPT = channel_data
            if TITLE is None: 
                await asyncio.sleep(1)
                continue
            
            adult_channel_state = -6
            if if_adult_channel == adult_channel_state:
                await asyncio.sleep(5)
                continue
            
            try:
                await self._connect_and_run()
            except Exception as e:
                await DiscordWebhookSender._log_error(f"error in chat manager afreeca: {e}")
                await base.change_chat_join_state(self.init.chat_json, self.data.channel_id)
            finally:
                await self._cleanup_tasks()

    async def _connect_and_run(self):   
        self.data.BID = self.init.afreecaIDList["afreecaID"][self.data.channel_id]
        async with websockets.connect(f"wss://{self.CHDOMAIN}:{self.CHPT}/Websocket/{self.data.BID}",
                                subprotocols=['chat'],
                                ssl=self.ssl_context,
                                ping_interval=None) as sock:
            self.data.sock = sock

            await self.connect()
            message_queue = asyncio.Queue()

            self.tasks = [
                asyncio.create_task(self._ping()),
                asyncio.create_task(self._receive_messages(message_queue)),
                asyncio.create_task(self._decode_message(message_queue)),
            ]
            await asyncio.gather(self.tasks[0], self.tasks[1])

    async def _cleanup_tasks(self):
        for task in self.tasks:
            if task and not task.done() and not task.cancelled():
                try:
                    task.cancel()
                    # Optionally wait for task to actually cancel
                    await asyncio.wait([task], timeout=2)
                except Exception as cancel_error:
                    await DiscordWebhookSender._log_error(f"Error cancelling task for {self.data.channel_id}: {cancel_error}")

    async def connect(self):
            self.data.last_chat_time= datetime.now().isoformat()
            CONNECT_PACKET = f'{self.ESC}000100000600{self.F*3}16{self.F}'
            JOIN_PACKET = f'{self.ESC}0002{self.calculate_byte_size(self.CHATNO):06}00{self.F}{self.CHATNO}{self.F*5}'
            
            await self.data.sock.send(CONNECT_PACKET)

            chatChannelId = self.init.afreeca_titleData.loc[self.data.channel_id, 'chatChannelId']
            asyncio.create_task(DiscordWebhookSender._log_error(f"{self.data.channel_id} 연결 완료 {chatChannelId}", webhook_url=environ['chat_post_url']))

            await asyncio.sleep(2)
            await self.data.sock.send(JOIN_PACKET)

    async def _ping(self):
        ping_interval = 10
        
        try:
            while not self.data.sock.closed:
                # Send ping message
                await self.data.sock.send(self.PING_PACKET)
                
                try:
                    await asyncio.wait_for(asyncio.shield(self.data.sock.wait_closed()), timeout=ping_interval)
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    await DiscordWebhookSender._log_error(f"Error during ping wait: {e}")
                    break
                    
        except Exception as e:
            await DiscordWebhookSender._log_error(f"Error in ping function: {e}")
        
        print(f"{self.data.channel_id} chat pong 종료")
    
    async def _receive_messages(self, message_queue: asyncio.Queue):
        async def should_close_connection():
            return (self.check_live_state_close() and base.if_after_time(self.data.last_chat_time) 
                    or self.init.chat_json[self.data.channel_id])
        
        message_buffer = []
        buffer_size = 5 
        buffer_timeout = 0.05
        last_buffer_flush= datetime.now().isoformat()

        while True:
            try:
                if await should_close_connection():
                    try: await self.data.sock.close()
                    except Exception: pass

                if self.data.sock.closed:
                    asyncio.create_task(DiscordWebhookSender._log_error(f"{self.data.channel_id}: 연결 종료", webhook_url=environ['chat_post_url']))
                    break

                raw_message = await asyncio.wait_for(self.data.sock.recv(), timeout=1)
                self.data.last_chat_time= datetime.now().isoformat()
                # await message_queue.put(raw_message)

                message_buffer.append(raw_message)
                
                if len(message_buffer) >= buffer_size or base.if_after_time(last_buffer_flush, sec=buffer_timeout):
                    for msg in message_buffer:
                        await message_queue.put(msg)
                    message_buffer.clear()
                    last_buffer_flush = self.data.last_chat_time
                    
            except asyncio.TimeoutError:
                if message_buffer:
                    for msg in message_buffer:
                        await message_queue.put(msg)
                    message_buffer.clear()
                    last_buffer_flush = self.data.last_chat_time
                continue

            except websockets.exceptions.ConnectionClosed:
                asyncio.create_task(DiscordWebhookSender._log_error(f"{self.data.channel_id}: 연결 비정상 종료"), webhook_url=environ['chat_post_url'])
                try: await self.data.sock.close()
                except Exception: pass

            except Exception as e: 
                asyncio.create_task(DiscordWebhookSender._log_error(f"{self.data.channel_id} afreeca chat test except {e}"))
                try: await self.data.sock.close()
                except Exception: pass

    async def _decode_message(self, message_queue: asyncio.Queue):
        processing_pool = []
        max_concurrent_processing = 10

        while True:
            bytes_data = await message_queue.get()
            parts = bytes_data.split(b'\x0c')
            messages = [part.decode('utf-8', errors='ignore') for part in parts]

            
            try:
                task = asyncio.create_task(self._process_single_message(messages))
                processing_pool.append(task)
                
                processing_pool = [t for t in processing_pool if not t.done()]
                
                if len(processing_pool) >= max_concurrent_processing:
                    _, pending = await asyncio.wait(
                        processing_pool, 
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    processing_pool = list(pending)
                
            except Exception as e:
                asyncio.create_task(DiscordWebhookSender._log_error(
                    f"Error processing message: {e}, {str(messages)}"
                ))
            finally:
                    # 큐 작업 완료 신호
                message_queue.task_done()
        
    async def _process_single_message(self, messages):
        if self._is_invalid_message(messages):
            if self.if_afreeca_chat(messages): 
                asyncio.create_task(DiscordWebhookSender._log_error(f"아프리카 chat recv messages {messages}", webhook_url=environ['chat_post_url']))
            return
        
        user_id, chat, nickname = messages[2], messages[1], messages[6]
        chat_type = "채팅"

        user_id = user_id.split("(")[0]

        # print(f"{datetime.now()} [{chat_type} - {self.data.channel_name}] {nickname}: {chat}")

        if user_id not in [*self.init.afreeca_chatFilter["channelID"]]: 
            return
        
        user_nick, profile_image = await self._get_user_info(user_id)
        if nickname != user_nick:
            return
        
        if nickname != self.init.afreeca_chatFilter.loc[user_id, "channelName"]: 
            asyncio.create_task(self.afreeca_name_save(user_id, nickname))

        # 메시지 중복 체크
        self._process_new_message(chat)
        
        asyncio.create_task(self._post_chat(nickname, chat, profile_image, chat_type))

    async def afreeca_name_save(self, user_id, user_name): #save profile data
        supabase = create_client(environ['supabase_url'], environ['supabase_key'])
        data = {
            "channelID": user_id,
            'channelName': user_name
        }
        for _ in range(3):
            try:
                supabase.table('afreeca_chatFilter').upsert(data).execute()
                break
            except Exception as e:
                asyncio.create_task(DiscordWebhookSender._log_error(f"error saving profile data {e}"))
                await asyncio.sleep(0.1)

    async def _post_chat(self, nickname, chat, profile_image, chat_type): #send to chatting message
        async with self.post_chat_semaphore:
            try:

                json_data = get_chat_json_data(nickname, chat, self.data.channel_name, profile_image)
                                
                list_of_urls = get_list_of_urls(self.init.DO_TEST, self.init.userStateData, nickname, self.data.channel_id, "chat_user_json")

                asyncio.create_task(send_push_notification(list_of_urls, json_data))
                asyncio.create_task(DiscordWebhookSender().send_messages(list_of_urls, json_data))
            
                print(f"{datetime.now()} post chat [{chat_type} - {self.data.channel_name}] {nickname}: {chat}")

            except Exception as e:
                asyncio.create_task(DiscordWebhookSender._log_error(f"error postChat: {str(e)}"))
 
    @staticmethod
    def calculate_byte_size(string):
        return len(string.encode('utf-8')) + 6

    async def _get_user_info(self, user_id):
        #유저 정보 가져오기
        stateData = await base.get_message("afreeca", base.afreeca_getLink(user_id))
        user_nick = stateData['station']['user_nick']
        _, _, profile_image = base.afreeca_getChannelOffStateData(stateData, stateData["station"]["user_id"])
        return user_nick, profile_image

    def _process_new_message(self, chat):
        message_id = f"{chat}_{time()}"
        
        # 이미 처리된 메시지인지 확인
        if message_id in self.data.processed_messages:
            asyncio.create_task(DiscordWebhookSender._log_error(f"{datetime.now()} 중복 메시지 무시: {chat}"))
            return
            
        # 새 메시지 처리
        self.data.processed_messages.append(message_id)
        
        # 메시지 리스트 크기 제한
        if len(self.data.processed_messages) > 20:
            self.data.processed_messages.pop(0)

    def _is_invalid_message(self, messages):
        #메시지가 유효하지 않은지 확인
        return (len(messages) < 7 or 
                messages[1] in ['-1', '', '1'] or 
                len(messages[2]) == 0 or 
                messages[2] in ["1"] or 
                ("fw" in messages[2]))

    def if_afreeca_chat(self, messages):
        # 기본 제외 조건들을 리스트로 정의
        excluded_values = {'-1', '1', '', '0', '2', '4'}
        
        # 빈 리스트 확인
        if not messages or len(messages) == 1:
            return 0
        
        # 인덱스 범위 확인
        if len(messages) <= 2:
            return 0
            
        # 첫 번째 검사: messages[1] 확인 (인덱스 검사는 이미 위에서 했음)
        if (messages[1] in excluded_values or 
            isinstance(messages[1], str) and '|' in messages[1] or
            'CHALLENGE_GIFT' in messages[1]):
            return 0
            
        # messages[2] 인덱스 및 타입 확인
        if (not isinstance(messages[2], str) or
            'fw' in messages[2] or
            messages[2] in {'-1', '1', '', '0'} or 
            '|' in messages[2]):
            return 0
            
        # 특정 문자열 체크
        message_str = str(messages)
        if ('png' in message_str or 
            'https://smartstore.naver.com' in message_str or 
            '씨발' in message_str):
            return 0
            
        # messages[7] 체크 (인덱스 확인 필요)
        if len(messages) >= 8 and isinstance(messages[7], str) and '|' in messages[7]:
            return 0
                
        return 1

    async def check_is_passwordDict(self):
        stateData = await base.get_message("afreeca", base.afreeca_getLink(self.init.afreecaIDList["afreecaID"][self.data.channel_id]))
        return stateData['broad'].get('is_password',{False})
    
    def check_live_state_close(self):
        try:
            return self.init.afreeca_titleData.loc[self.data.channel_id, 'live_state'] == "CLOSE"
        except Exception as e:
            asyncio.create_task(DiscordWebhookSender._log_error(f"Error in check_live_state_close: {e}"))
            return True
    
    def afreeca_getChannelStateData(self):
        url = 'https://live.sooplive.co.kr/afreeca/player_live_api.php'
        data = {
            'bid': self.data.BID,
            'bno': self.data.BNO,
            'type': 'live',
            'confirm_adult': 'false',
            'player_type': 'html5',
            'mode': 'landing',
            'from_api': '0',
            'pwd': '',
            'stream_type': 'common',
            'quality': 'HD'}
        try:
            response = post(f'{url}?bjid={self.data.BID}', data=data)
            res = response.json()
        except Exception as e:
            asyncio.create_task(DiscordWebhookSender._log_error(f"error get player live {str(e)}"))
            return None, None, None, None, None, None, None, None
        live = res["CHANNEL"]["RESULT"]
        title = res["CHANNEL"]["TITLE"]

        adult_channel_state = -6
        if live == adult_channel_state:  # 연령제한 체널로 썸네일링크 못 읽을 경우
            thumbnail_url = f"https://liveimg.afreecatv.com/m/{self.data.BNO}"
            return live, title, thumbnail_url, None, None, None, None, None
        if live:
            try: int(res['CHANNEL']['BNO'])
            except: 
                asyncio.create_task(DiscordWebhookSender._log_error(f"error res['CHANNEL']['BNO'] None"))

            thumbnail_url = f"https://liveimg.afreecatv.com/m/{res['CHANNEL']['BNO']}"

            CHDOMAIN = res["CHANNEL"]["CHDOMAIN"].lower()
            CHATNO = res["CHANNEL"]["CHATNO"]
            FTK = res["CHANNEL"]["FTK"]
            BJID = res["CHANNEL"]["BJID"]
            CHPT = str(int(res["CHANNEL"]["CHPT"]) + 1)
        else:
            title = None
            thumbnail_url = None
            CHDOMAIN = None
            CHATNO = None
            FTK = None
            BJID = None
            CHPT = None

        return live, title, thumbnail_url, CHDOMAIN, CHATNO, FTK, BJID, CHPT

