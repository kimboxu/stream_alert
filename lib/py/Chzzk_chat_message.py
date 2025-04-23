import asyncio
import chzzk_api
import websockets
from os import environ
from datetime import datetime
from urllib.parse import unquote
from json import loads, dumps, JSONDecodeError
from dataclasses import dataclass, field
from cmd_type import CHZZK_CHAT_CMD, CHZZK_DONATION_CMD
from base import  getChzzkCookie, if_last_chat, initVar, get_message, change_chat_join_state, save_airing_data, if_after_time, discordBotDataVars, userDataVar
from discord_webhook_sender import DiscordWebhookSender, get_list_of_urls, get_chat_json_data
from my_app import send_push_notification

@dataclass
class ChzzkChatData:
    sock: websockets.connect = None
    chzzk_chat_msg_List: list = field(default_factory=list)
    last_chat_time: datetime = field(default_factory=datetime.now)
    sid: str = ""
    cid: str = ""
    accessToken: str = ""
    extraToken: str = ""
    channel_id: str = ""
    channel_name: str = ""

class chzzk_chat_message:
    def __init__(self, init_var: initVar, channel_id):
        self.init = init_var
        channel_name = init_var.chzzkIDList.loc[channel_id, 'channelName']
        self.state_update_time = init_var.chzzk_titleData.loc[channel_id, 'state_update_time']
        self.data = ChzzkChatData(channel_id=channel_id, channel_name = channel_name)
        self.post_chat_semaphore = asyncio.Semaphore(5)
        self.profile_image_cache = {}  # Store as uid -> (timestamp, image_url)
        self.profile_cache_ttl = 1800
        self.tasks = []

    async def start(self):
        while True:
            if self.init.chat_json[self.data.channel_id]: 
                await change_chat_join_state(self.init.chat_json, self.data.channel_id, False)
            
            if self.check_live_state_close():
                await asyncio.sleep(5)
                continue
            
            try:
                await self._connect_and_run()
            except Exception as e:
                await DiscordWebhookSender._log_error(f"error in chat manager: {e}")
                await change_chat_join_state(self.init.chat_json, self.data.channel_id)
            finally:
                await self._cleanup_tasks()

    async def _connect_and_run(self):
        async with websockets.connect('wss://kr-ss3.chat.naver.com/chat', 
                                    subprotocols=['chat'], 
                                    ping_interval=None) as sock:
            self.data.sock = sock
            self.data.cid = self.init.chzzk_titleData.loc[self.data.channel_id, 'chatChannelId']


            await self.get_check_channel_id()
            if not if_after_time(self.state_update_time["openDate"], sec = 60) and not await self.change_chatChannelId():
                return
            
            await self.change_chatChannelId()
            await self.connect()
            message_queue = asyncio.Queue()

            self.tasks = [
                asyncio.create_task(self._ping()),
                asyncio.create_task(self._message_receiver(message_queue)),
                asyncio.create_task(self._message_processor(message_queue)),
                # asyncio.create_task(self._post_chat()),
            ]
            
            await asyncio.gather(self.tasks[0], self.tasks[1])

    async def _cleanup_tasks(self):
        for task in self.tasks:
            if task and not task.done() and not task.cancelled():
                try:
                    task.cancel()
                    await asyncio.wait([task], timeout=2)
                except Exception as cancel_error:
                    error_logger = DiscordWebhookSender()
                    await error_logger._log_error(f"Error cancelling task for {self.data.channel_id}: {cancel_error}")

    async def _message_receiver(self, message_queue: asyncio.Queue):
        async def should_close_connection():
            return ((self.check_live_state_close() and if_last_chat(self.data.last_chat_time)) 
                    or self.init.chat_json[self.data.channel_id])
        json_loads = loads
        message_buffer = []
        buffer_size = 5 
        buffer_timeout = 0.05
        last_buffer_flush = datetime.now()

        while True:

            # 논블로킹 방식으로 메시지 수신 시도
            try:
                if await should_close_connection():
                    try: await self.data.sock.close()
                    except Exception: pass

                if self.data.sock.closed:
                    asyncio.create_task(DiscordWebhookSender._log_error(f"{self.data.channel_id} 연결 종료 {self.data.cid}", webhook_url=environ['chat_post_url']))
                    break

                raw_message = await asyncio.wait_for(self.data.sock.recv(), timeout=0.5)
                
                self.data.last_chat_time = datetime.now()
                parsed_message = json_loads(raw_message)
                # await message_queue.put(parsed_message)

                message_buffer.append(parsed_message)
                
                if len(message_buffer) >= buffer_size or if_last_chat(last_buffer_flush, sec=buffer_timeout):
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
                
            except (JSONDecodeError, ConnectionError, RuntimeError, websockets.exceptions.ConnectionClosed) as e:
                if not self.check_live_state_close():
                    asyncio.create_task(DiscordWebhookSender._log_error(f"{datetime.now()} last_chat_time{self.data.channel_id} 2.{self.data.last_chat_time}.{e}"))
                    try: await self.data.sock.close()
                    except Exception: pass
                asyncio.create_task(DiscordWebhookSender._log_error(f"Test2 {self.data.channel_id}.{e}{datetime.now()}"))
                continue
                    
            except Exception as e:
                print(f"{datetime.now()} Error details: {type(e)}, {e}")
                asyncio.create_task(DiscordWebhookSender._log_error(f"Detailed error in message_receiver: {type(e)}, {e}"))

    async def _message_processor(self, message_queue: asyncio.Queue):
        processing_pool = []
        max_concurrent_processing = 10
        
        while True:
            try:
                # 큐에서 메시지 가져오기
                raw_message = await message_queue.get()
                
                try:
                    task = asyncio.create_task(self._process_single_message(raw_message))
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
                        f"Error processing message: {e}, {str(raw_message)}"
                    ))
                finally:
                     # 큐 작업 완료 신호
                    message_queue.task_done()
                    
            except Exception as e:
                print(f"{datetime.now()} Error in message_processor: {e}")
                asyncio.create_task(DiscordWebhookSender._log_error(f"Error in message_processor: {e}"))
                await asyncio.sleep(0.1)    ## 예외 발생 시 잠시 대기

    async def _process_single_message(self, raw_message):
        try:
            # 채팅 타입 결정
            chat_cmd = raw_message['cmd']
            chat_type = self.get_chat_type(chat_cmd)

            if not await self.check_chat_message(raw_message, chat_type):
                return
            
            if not (bdy := await self.check_TEMPORARY_RESTRICT(raw_message)):
                return
            
            chzzk_chat_list = self.get_chzzk_chat_list(bdy)

            if chzzk_chat_list:
                await self.process_chat_list(chzzk_chat_list, chat_type)
        
        except Exception as e:
            asyncio.create_task(DiscordWebhookSender._log_error(f"Error in _process_single_message: {e}, {str(raw_message)}"))

    def get_chat_type(self, chat_cmd) -> str:
        # 채팅 타입 결정
        return {
            CHZZK_CHAT_CMD['chat']: '채팅',
            CHZZK_CHAT_CMD['request_chat']: '채팅',
            CHZZK_CHAT_CMD['donation']: '후원',
            CHZZK_CHAT_CMD['ping']: '핑'
        }.get(chat_cmd, '모름')
    
    def get_msgTypeCode(self, chat_data) -> str:
        # 후원 타입 결정
        msgTypeCode = chat_data.get('msgTypeCode') or chat_data.get('messageTypeCode')
        return {
            CHZZK_DONATION_CMD['chat']: '채팅',
            CHZZK_DONATION_CMD['subscribe']: '구독',
            CHZZK_DONATION_CMD['donation']: '일반후원',
            CHZZK_DONATION_CMD['CHAT_RESTRICTION_MSG']: '채팅제한',
            CHZZK_DONATION_CMD['subscription_gift']: '구독선물',
        }.get(msgTypeCode, '모름')

    async def check_chat_message(self, raw_message, chat_type):
        if chat_type == "핑": 
            await self.data.sock.send(dumps(self._CHZZK_CHAT_DICT("pong")))
            print(f"{datetime.now()} [{chat_type} - ping]")
            return False
        
        # 에러 체크
        if chat_type != "후원" and raw_message['tid'] is None:
            bdy = raw_message.get('bdy', {})
            if message := bdy.get('message'):
                asyncio.create_task(DiscordWebhookSender._log_error(f"message_processor200len.{str(message)[:200]}"))
            return False

        return True
    
    async def check_TEMPORARY_RESTRICT(self, raw_message):
        # 임시 제한 처리
        bdy = raw_message.get('bdy', {})
        if isinstance(bdy, dict) and bdy.get('type') == 'TEMPORARY_RESTRICT':
            duration = bdy.get('duration', 30)
            asyncio.create_task(DiscordWebhookSender._log_error(f"{datetime.now()} 임시 제한 상태입니다. {duration}초 동안 대기합니다."))
            await asyncio.sleep(duration)
            return {}
        return bdy

    def get_chzzk_chat_list(self, bdy):
        if isinstance(bdy, dict) and 'messageList' in bdy:
            chat_data = bdy['messageList']
            chzzk_chat_list = [msg for msg in chat_data]
        else:
            chat_data = bdy if isinstance(bdy, list) else [bdy]
            chzzk_chat_list = [msg for msg in chat_data]
        return chzzk_chat_list

    async def process_chat_list(self, chzzk_chat_list, chat_type):
        processing_tasks = []
        
        for chat_data in chzzk_chat_list:
            try:
                if self.get_msgTypeCode(chat_data) == "채팅제한":
                    continue

                nickname = self.get_nickname(chat_data)
                if nickname is None:
                    continue
                
                userRoleCode = self.get_userRoleCode(chat_data, nickname)
                
                message = self.print_msg(chat_data, chat_type)
                if not self.init.DO_TEST and (chat_type == "후원" or userRoleCode in ["streamer", "streaming_chat_manager"]):
                    asyncio.create_task(DiscordWebhookSender._log_error(
                        message, webhook_url=environ['donation_post_url']
                    ))
                else:
                    print(f"{datetime.now()} {message}")

                #chzzk_chatFilter에 없는 사람 채팅은 제거
                # if nickname not in [*self.init.chzzk_chatFilter["channelName"]]:
                #     continue

                # self.data.chzzk_chat_msg_List.append([chat_data, chat_type])
                task = asyncio.create_task(self._post_chat(chat_data, chat_type))
                processing_tasks.append(task)

            except Exception as e:
                asyncio.create_task(DiscordWebhookSender._log_error(f"error process_message {e}"))
        
        if processing_tasks:
            await asyncio.gather(*processing_tasks, return_exceptions=True)

    async def _post_chat(self, chat_data, chat_type):
        try:
            async with self.post_chat_semaphore:  # Limit concurrent executions
                nickname = self.get_nickname(chat_data)
                chat = self.get_chat(chat_data)
                uid = self.get_uid(chat_data)
                
                # profile_image_task = self._get_profile_image_cached(uid)
                profile_image = await self._get_profile_image_cached(uid)
                
                json_data = get_chat_json_data(nickname, chat, self.data.channel_name, profile_image)
                
                list_of_urls = get_list_of_urls(self.init.DO_TEST, self.init.userStateData, 
                                            nickname, self.data.channel_id, "chat_user_json")
                
                asyncio.create_task(send_push_notification(list_of_urls, json_data))
                message_sender = DiscordWebhookSender()
                webhook_task = asyncio.create_task(message_sender.send_messages(list_of_urls, json_data, DO_TEST = self.init.DO_TEST))
                webhook_task.add_done_callback(lambda t: self._handle_webhook_result(t))
                
                print(f"{datetime.now()} post chat {self.print_msg(chat_data, chat_type)}")
        except Exception as e:
            asyncio.create_task(DiscordWebhookSender._log_error(f"error postChat: {str(e)}"))

    def _handle_webhook_result(self, task):
        try:
            task.result()  # 예외가 있으면 여기서 발생
        except Exception as e:
            asyncio.create_task(DiscordWebhookSender._log_error(f"Webhook task error: {str(e)}"))

    async def _get_profile_image_cached(self, uid):
        
        # 프로필 url profile_cache_ttl 시간 동안 캐시에 재사용 가능 
        if uid in self.profile_image_cache:
            timestamp, image_url = self.profile_image_cache[uid]
            if not if_after_time(timestamp, sec = self.profile_cache_ttl):
                return image_url
        
        # If not cached or expired, fetch a new one
        image_url = await self._get_profile_image(uid)
        
        # Update cache
        self.profile_image_cache[uid] = (datetime.now().isoformat(), image_url)
        return image_url

    async def _ping(self):
        ping_interval = 10
        
        try:
            while not self.data.sock.closed:
                # Send ping message
                await self.data.sock.send(dumps(self._CHZZK_CHAT_DICT("pong")))
                
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

    async def connect(self):
        self.data.accessToken, self.data.extraToken = chzzk_api.fetch_accessToken(self.data.cid, getChzzkCookie())
        
        await self.data.sock.send(dumps(self._CHZZK_CHAT_DICT("connect")))
        sock_response = loads(await self.data.sock.recv())
        self.data.sid = sock_response['bdy']['sid']
        await self.data.sock.send(dumps(self._CHZZK_CHAT_DICT("recentMessageCount", num = 50)))
        sock_response = loads(await self.data.sock.recv())


        bdy = await self.check_TEMPORARY_RESTRICT(sock_response)
        chzzk_chat_list = self.get_chzzk_chat_list(bdy)
        try:
            messageTime = chzzk_chat_list[-1].get('messageTime') or chzzk_chat_list[-1].get('msgTime')
        except Exception as e: print(f"test messageTime {e}")

        self.data.last_chat_time = datetime.fromtimestamp(messageTime/1000)

        asyncio.create_task(DiscordWebhookSender._log_error(f"{self.data.channel_id} 연결 완료 {self.data.cid}", webhook_url=environ['chat_post_url']))

    def _send(self, message):
        default_dict = {
            "ver": 2,
            "svcid": "game",
            "cid": self.data.cid,
        }

        extras = {
            "chatType": "STREAMING",
            "emojis": "",
            "osType": "PC",
            "extraToken": self.data.extraToken,
            "streamingChannelId": self.data.cid
        }

        send_dict = {
            "tid": 3,
            "cmd": CHZZK_CHAT_CMD['send_chat'],
            "retry": False,
            "sid": self.data.sid,
            "bdy": {
                "msg": message,
                "msgTypeCode": 1,
                "extras": dumps(extras),
                "msgTime": int(datetime.now().timestamp())
            }
        }

        self.data.sock.send(dumps(dict(send_dict, **default_dict)))

    def _CHZZK_CHAT_DICT(self, option = "connect", num = 50):
        default_dict = {
            "ver": "2",
            "svcid": "game",
            "cid": self.data.cid,
        }
        if option == "connect":
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
            send_dict = {
                "cmd": CHZZK_CHAT_CMD['request_recent_chat'],
                "tid": 2,
                "sid": self.data.sid,
                "bdy": {
                    "recentMessageCount": num
                }
            }
        elif option == "pong":
            return {
                "ver" : "2",
                "cmd" : CHZZK_CHAT_CMD['pong']
                }
        
        return dict(send_dict, **default_dict)

    async def _get_profile_image(self, uid):
        def chzzk_getLink(uid):
            return f'https://api.chzzk.naver.com/service/v1/channels/{uid}'
        
        data = await get_message("chzzk", chzzk_getLink(uid))
        profile_image = data["content"]["channelImageUrl"]

        if profile_image and profile_image.startswith(("https://nng-phinf.pstatic.net", "https://ssl.pstatic.net")):
            return profile_image

        profile_image = environ['default_thumbnail']

        return profile_image
    
    async def get_check_channel_id(self) -> int:
        try:

            self.data.cid = chzzk_api.fetch_chatChannelId(self.init.chzzkIDList.loc[self.data.channel_id, "channel_code"])
            return True
            
        except Exception as e: 
            asyncio.create_task(DiscordWebhookSender._log_error(f"error get_check_channel_id {self.data.channel_id}.{e}"))
        return False

    async def change_chatChannelId(self):
        if self.data.cid != self.init.chzzk_titleData.loc[self.data.channel_id, 'chatChannelId']:
            self.init.chzzk_titleData.loc[self.data.channel_id, 'oldChatChannelId'] = self.init.chzzk_titleData.loc[self.data.channel_id, 'chatChannelId']
            self.init.chzzk_titleData.loc[self.data.channel_id, 'chatChannelId'] = self.data.cid
            await save_airing_data(self.init.chzzk_titleData, 'chzzk', self.data.channel_id)
            return True
        return False

    def get_profile_data(self, chat_data, nickname):
        profile_data = chat_data.get('profile', {})
        #AOS환경의 채팅인 경우 profile_data가 str형의 null인 경우가 있음
        if profile_data is None or profile_data == "null":
            profile_data = {}

        elif isinstance(profile_data, str):
            profile_data = unquote(profile_data)
            profile_data = loads(profile_data)
        if not profile_data and nickname not in  ["익명의 후원자", "알 수 없음"]: 
            asyncio.create_task(DiscordWebhookSender._log_error(f"test get_profile_data"))
            print(f"test get_profile_data.{self.data.channel_name}.{chat_data}")
        return profile_data

    def get_userRoleCode(self, chat_data, nickname):
        #streamer, streaming_chat_manager, common_user
        profile_data = self.get_profile_data(chat_data, nickname)
        return profile_data.get('userRoleCode', None)

    def get_nickname(self, chat_data):
        nick_name = "(알 수 없음)"
        if not chat_data.get('extras', {}) or loads(chat_data['extras']).get('styleType', {}) in [1, 2, 3]:
            return nick_name
            
        # Handle anonymous users
        user_id = chat_data.get('uid', chat_data.get('userId'))
        if user_id == 'anonymous':
            return '익명의 후원자'
        
        # Parse and validate profile data
        profile_data = self.get_profile_data(chat_data, nick_name)
        return profile_data.get('nickname', nick_name)

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

    def get_uid(self, chat_data) -> str:
        return chat_data.get('uid') or chat_data.get('userId')

    def get_payAmount(self, chat_data, chat_type) -> str:
        if chat_type == "후원": payAmount = loads(chat_data['extras'])['payAmount']
        else: payAmount = None
        return payAmount

    def print_msg(self, chat_data, chat_type) -> str:

        if chat_type == "채팅":
            msg = chat_data.get('msg') or chat_data.get('content')
            time = chat_data.get('msgTime') or chat_data.get('messageTime')
            return self.format_message('채팅', chat_type, self.get_nickname(chat_data), msg, time)
        
        if chat_type == "후원":
        
            extras = loads(chat_data['extras'])
            msg_type_code = self.get_msgTypeCode(chat_data)
            
            handlers = {
                "일반후원": self._handle_donation,
                "구독": self._handle_subscription,
                "구독선물": self._handle_gift_subscription,
                "채팅": self._handle_chat
            }
            
            handler = handlers.get(msg_type_code, self._handle_unknown)
            
            return handler(chat_data, chat_type, extras)
        
        return "print_msg 채팅도 후원도 아닌 무언가 현재는 확인X"

    def format_message(self, msg_type, chat_type, nickname, message, time, **kwargs):
        base = f"[{chat_type} - {self.data.channel_name}] {nickname}"
        formatted_time  = datetime.fromtimestamp(time/1000)

        message_formats = {
            "후원채팅": lambda: f"{base} ({kwargs.get('amount')}치즈): {message}, {formatted_time}",

            "영상후원": lambda: f"{base} ({kwargs.get('amount')}치즈) 영상후원: {message}, {formatted_time}",
            
            "후원미션걸기": lambda: f"{base} ({kwargs.get('missionText')} 모금함 미션 생성{kwargs.get('amount')}치즈 ): {message}, {formatted_time}",
            
            "후원미션추가": lambda: f"{base} ({kwargs.get('missionText')} 모금함에 미션에 {kwargs.get('amount')}치즈 추가): {message}, {formatted_time}",
            
            "구독": lambda: f"{base} ({kwargs.get('month')}개월 동안 구독): {message}, {formatted_time}",
            
            "구독선물": lambda: f"{base} ({kwargs.get('giftTierName')}구독권{kwargs.get('quantity')}개를 선물): {message}, {formatted_time}",

            "단일구독선물": lambda: f"{base} ({kwargs.get('receiverNickname')}님에게 {kwargs.get('giftTierName')}구독권선물): {message}, {formatted_time}",

            "default": lambda: f"{base}: {message}, {formatted_time}"

            }

        formatter = message_formats.get(msg_type, message_formats["default"])
        return formatter()

    def _handle_donation(self, chat_data, chat_type, extras):
        donation_type = extras.get('donationType')
        
        donation_handlers = {
            "CHAT": lambda: self.format_message(
                "후원채팅", 
                chat_type,
                self.get_nickname(chat_data),
                chat_data['msg'],
                chat_data['msgTime'],
                amount=extras['payAmount']
            ),
            "VIDEO": lambda: self.format_message(
                "영상후원",
                chat_type,
                self.get_nickname(chat_data),
                chat_data['msg'],
                chat_data['msgTime'],
                amount=extras['payAmount']
            ),
            "MISSION": lambda: self.format_message(
                "후원미션걸기",
                chat_type,
                self.get_nickname(chat_data),
                chat_data['msg'],
                chat_data['msgTime'],
                amount=extras['payAmount'],
                missionText=extras['missionText']
            ),
            "MISSION_PARTICIPATION": lambda: self.format_message(
                "후원미션추가",
                chat_type,
                self.get_nickname(chat_data),
                chat_data['msg'],
                chat_data['msgTime'],
                amount=extras['payAmount'],
                missionText=extras['missionText']
            ),
        }
        
        handler = donation_handlers.get(donation_type)
        if handler:
            return handler()
        
        # Log unknown donation type
        asyncio.create_task(DiscordWebhookSender._log_error(f"Unknown donation type: {donation_type}"))
        print(chat_data)
        return self.format_message(
            "후원채팅",
            chat_type,
            self.get_nickname(chat_data),
            chat_data['msg'],
            chat_data['msgTime'],
            amount=extras['payAmount']
        )

    def _handle_subscription(self, chat_data, chat_type, extras):
        tierName = extras["tierName"] #구독 티어 이름
        tierNo = extras["tierNo"]   #구독 티어 
        return self.format_message(
            "구독",
            chat_type,
            self.get_nickname(chat_data),
            chat_data['msg'],
            chat_data['msgTime'],
            month=extras['month']
        )

    def _handle_gift_subscription(self, chat_data, chat_type, extras):
        if extras.get('giftType') == 'SUBSCRIPTION_GIFT':
            return self.format_message(
                "구독선물",
                chat_type,
                self.get_nickname(chat_data),
                chat_data['msg'],
                chat_data['msgTime'],
                giftTierName=extras['giftTierName'],
                quantity=extras["quantity"],
            )
        elif extras.get('giftType') == 'SUBSCRIPTION_GIFT_RECEIVER':
            return self.format_message(
                "단일구독선물",
                chat_type,
                self.get_nickname(chat_data),
                chat_data['msg'],
                chat_data['msgTime'],
                giftTierName=extras['giftTierName'],
                receiverNickname=extras['receiverNickname'],
            )
        
        asyncio.create_task(DiscordWebhookSender._log_error(f"Unknown gift subscription type: "))
        print(f"Unknown gift subscription type: {chat_data}")
        return f"print_msg 어떤 메시지인지 현재는 확인X.{self.data.channel_name}.{self.get_nickname(chat_data)}.{extras}"

    def _handle_chat(self, chat_data, chat_type, extras):
        return self.format_message(
            '채팅', 
            chat_type, 
            self.get_nickname(chat_data), 
            chat_data['msg'], 
            chat_data['msgTime']
        )

    def _handle_unknown(self, chat_data, chat_type, extras):
        asyncio.create_task(DiscordWebhookSender._log_error(f"Unknown _handle_unknowne: {self.get_msgTypeCode(chat_data)}.{chat_type}"))
        print(f"Unknown _handle_unknowne: {chat_data}")
        return f"print_msg 어떤 메시지인지 현재는 확인X.{self.data.channel_name}.{self.get_nickname(chat_data)}.{extras}"

    async def sendHi(self, himent):
        if await self.get_check_channel_id():
            await self.change_chatChannelId()
            asyncio.create_task(DiscordWebhookSender._log_error(f"send hi {self.init.chzzkIDList.loc[self.data.channel_id, 'channelName']} {self.data.cid}"))
            self._send(himent)

    def onAirChat(self, message):
        himent = None
        if message != "뱅온!":return
        if self.data.channel_id == "charmel"   	: himent = "챠하"
        if self.data.channel_id == "mawang0216"	: himent = "마하"
        if self.data.channel_id == "bighead033"	: himent = "빅하"
        if himent: self._send(himent)

    def offAirChat(self):
        byement = None
        if self.data.channel_id =="charmel"   : byement = "챠바"
        if self.data.channel_id =="mawang0216": byement = "마바"
        if self.data.channel_id =="bighead033": byement = "빅바"
        if byement: self._send(byement)

    def check_live_state_close(self):
        try:
            return self.init.chzzk_titleData.loc[self.data.channel_id, 'live_state'] == "CLOSE"
        except Exception as e:
            asyncio.create_task(DiscordWebhookSender._log_error(f"Error in check_live_state_close: {e}"))
            return True



async def generic_chat(init: initVar, platform_name: str, message_class):
    await asyncio.sleep(3)
    
    tasks = {}  # 채널 ID별 실행 중인 task를 관리할 딕셔너리
    
    while True:
        try:
            # ID 리스트 결정
            if platform_name == 'chzzk':
                id_list = init.chzzkIDList
            elif platform_name == 'afreeca':
                id_list = init.afreecaIDList
            
            # 기존 실행 중인 태스크를 유지하면서, 새로운 채널이 추가되면 실행
            for channel_id in id_list["channelID"]:
                if channel_id not in tasks or tasks[channel_id].done():
                    chat_instance = message_class(init, channel_id)
                    tasks[channel_id] = asyncio.create_task(chat_instance.start())
            
            await asyncio.sleep(1)  # 1초마다 체크 (필요하면 조절 가능)
        
        except Exception as e:
            print(f"{datetime.now()} error {platform_name}_chatf {e}")
            await asyncio.create_task(DiscordWebhookSender._log_error(f"Error in {platform_name}_chatf: {str(e)}"))
            await asyncio.sleep(1)

async def main():
    init = initVar()
    await discordBotDataVars(init)
    await userDataVar(init)
    await asyncio.sleep(1)
    

    await asyncio.create_task(generic_chat(init, 'chzzk', chzzk_chat_message))
        
if __name__ == "__main__":
    asyncio.run(main())