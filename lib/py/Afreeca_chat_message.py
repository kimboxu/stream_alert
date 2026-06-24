import ssl
from base import (
    initVar,
    change_field_state,
    if_after_time,
    afreeca_getLink,
    afreeca_getChannelOffStateData,
    log_error,
    getDefaultHeaders,
    getAfreecaCookie,
    save_airing_data,
    change_nickname,
)
import certifi  # SSL 인증서 검증용 라이브러리
import asyncio
import websockets
from time import time
from json import loads
from os import environ
from datetime import datetime
from dataclasses import dataclass, field
from improved_get_message import get_message
from discord_webhook_sender import (
    DiscordWebhookSender,
    get_list_of_urls,
    get_chat_json_data,
)
from notification_service import send_push_notification
from chat_analyzer import ChatMessageWithAnalyzer
from make_log_api_performance import PerformanceManager

from aiohttp import ClientSession, ClientError, TCPConnector


# 아프리카 채팅 데이터 클래스 정의
@dataclass
class AfreecaChatData:
    sock = None  # 웹소켓 연결 객체
    message_queue: asyncio.Queue = field(
        default_factory=asyncio.Queue
    )  # 채팅 메시지 큐
    processed_messages: list = field(
        default_factory=list
    )  # 처리된 메시지 리스트 (중복 방지용)
    last_chat_time: str = ""  # 마지막 채팅 시간
    channel_id: str = ""  # 채널 ID
    channel_name: str = ""  # 채널 이름
    BNO: str = ""  # 방송 번호
    BID: str = ""  # 방송인 ID


# 아프리카 채팅 메시지 처리 클래스
class afreeca_chat_message(ChatMessageWithAnalyzer):
    def __init__(
        self, init_var: initVar, performance_manager: PerformanceManager, channel_id
    ):
        self.init = init_var
        self.performance_manager = performance_manager
        self.DiscordWebhookSender_class = DiscordWebhookSender()

        # SSL 컨텍스트 생성
        self.ssl_context = self.create_ssl_context()

        # 웹소켓 통신에 사용되는 특수 문자 정의
        self.F = "\x0c"  # 구분자
        self.ESC = "\x1b\t"  # 이스케이프 시퀀스
        self.PING_PACKET = f"{self.ESC}000000000100{self.F}"  # 핑 패킷 형식

        # 채널 이름 가져오기
        channel_name = self.init.IDList["afreeca"].loc[channel_id, "channelName"]

        # 채팅 데이터 객체 초기화
        self.title_data = init_var.titleData["afreeca"]
        self.state_update_time = self.title_data.loc[channel_id, "state_update_time"]
        self.data = AfreecaChatData(channel_id=channel_id, channel_name=channel_name)

        # 동시 채팅 요청 제한을 위한 세마포어
        self.post_chat_semaphore = asyncio.Semaphore(5)

        # 비동기 태스크 관리 리스트
        self.tasks = []
        self.start_program = False if self.check_live_state_close() else True

        # 방송 타입 상태
        self.adult_channel_state = -6
        self.subscription_Plus = -14
        self.black_list = -3

        self.setup_analyzer(channel_id, channel_name, "afreeca")

    # SSL 컨텍스트 생성
    @staticmethod
    def create_ssl_context():
        ssl_context = (
            ssl.create_default_context()
        )  # 기본 보안 설정이 적용된 SSL 컨텍스트 객체를 생성
        ssl_context.load_verify_locations(
            certifi.where()
        )  # 신뢰할 수 있는 인증서 파일의 경로를 반환
        ssl_context.check_hostname = False  #  인증서 확인 비활성화
        ssl_context.verify_mode = ssl.CERT_NONE  # 서버 인증서 유효성 검증 비활성화
        return ssl_context

    # 채팅 모니터링 시작
    async def start(self):
        while True:
            # 채팅 참여 상태가 활성화되어 있으면 비활성화
            if self.init.chat_json[self.data.channel_id]:
                asyncio.create_task(
                    change_field_state(
                        self.init.supabase,
                        "chat_json",
                        self.init.chat_json,
                        self.data.channel_id,
                        False,
                    )
                )

            # 방송이 종료되었거나 비밀번호가 설정된 경우 대기
            if self.check_live_state_close() or await self.check_is_passwordDict():
                await asyncio.sleep(5)
                continue

            # 방송 정보 가져오기
            self.data.BNO = int(self.title_data.loc[self.data.channel_id, "chatChannelId"])
            self.data.BID = self.init.IDList["afreeca"]["uid"][self.data.channel_id]

            # 방송 정보가 없으면 대기
            if not await self.afreeca_getChannelStateData():
                await asyncio.sleep(5)
                continue

            try:
                await self._connect_and_run()  # 웹소켓 연결 및 메시지 처리 실행
            except Exception as e:
                # 오류 발생 시 로그 기록
                await log_error(
                    f"error in chat manager afreeca {self.data.channel_id}.{str(e)}"
                )
                if not self.init.DO_TEST:
                    asyncio.create_task(
                        change_field_state(
                            self.init.supabase,
                            "chat_json",
                            self.init.chat_json,
                            self.data.channel_id,
                        )
                    )
            finally:
                # 실행 중인 태스크 정리
                await self._cleanup_tasks()

    # 웹소켓 연결 및 메시지 처리
    async def _connect_and_run(self):
        self.data.BID = self.init.IDList["afreeca"]["uid"][self.data.channel_id]
        # print(f"{datetime.now()} {self.data.channel_id} 방송 켜짐")
        # 웹소켓 연결
        async with websockets.connect(
            f"wss://{self.CHDOMAIN}:{self.CHPT}/Websocket/{self.data.BID}",
            subprotocols=["chat"],
            ssl=self.ssl_context,
            ping_interval=None,
        ) as sock:
            self.data.sock = sock
            self.run_analyzer = True

            # if not self.start_program and self.title_data.loc[self.data.channel_id, 'state_update_time']['is_firstConnect'] and not await self.is_different_chatChannelId():
            #     await asyncio.sleep(0.1)
            #     return

            # 채팅 채널에 연결
            # await self.change_chatChannelId()
            await self.connect()

            if self.title_data.loc[self.data.channel_id, "state_update_time"][
                "is_firstConnect"
            ]:
                self.title_data.loc[self.data.channel_id, "state_update_time"][
                    "is_firstConnect"
                ] = False
                asyncio.create_task(
                    save_airing_data(
                        self.init.supabase,
                        self.title_data,
                        "afreeca",
                        self.data.channel_id,
                        updated_keys={"chatChannelId", "oldChatChannelId", "state_update_time"},
                    )
                )

            await self.start_analyzer()  # 분석기 시작

            # 핑, 메시지 수신, 메시지 디코딩 태스크 생성 및 실행
            self.tasks = [
                asyncio.create_task(self._ping()),
                asyncio.create_task(self._receive_messages()),
                asyncio.create_task(self._decode_message()),
            ]
            await asyncio.gather(self.tasks[0], self.tasks[1])

    # 실행 중인 태스크 정리
    async def _cleanup_tasks(self):
        self.start_program = False

        for task in self.tasks:
            if task and not task.done() and not task.cancelled():
                try:
                    task.cancel()
                    await asyncio.wait([task], timeout=2)
                except Exception as cancel_error:
                    await log_error(
                        f"Error cancelling task for {self.data.channel_id}.{cancel_error}"
                    )
        await self.stop_analyzer()

        print(f"{datetime.now()} {self.data.channel_id} 연결 정리 완료")

    # 채팅 서버 연결
    async def connect(self):
        self.data.last_chat_time = datetime.now().isoformat()
        # 연결 및 채널 참여 패킷 정의
        CONNECT_PACKET = f"{self.ESC}000100000600{self.F*3}16{self.F}"
        JOIN_PACKET = f"{self.ESC}0002{self.calculate_byte_size(self.CHATNO):06}00{self.F}{self.CHATNO}{self.F*5}"

        # 연결 패킷 전송
        await self.data.sock.send(CONNECT_PACKET)

        chatChannelId = int(self.title_data.loc[self.data.channel_id, "chatChannelId"])

        # 연결 완료 로그 기록
        if self.start_program:
            print(f"{datetime.now()} {self.data.channel_id} 연결 완료 {chatChannelId}")
        else:
            asyncio.create_task(
                log_error(
                    f"{self.data.channel_id} 연결 완료 {chatChannelId}",
                    is_Do_test=self.init.DO_TEST,
                    webhook_url=environ["chat_post_url"],
                )
            )

        # 채널 참여 패킷 전송
        await asyncio.sleep(2)
        await self.data.sock.send(JOIN_PACKET)

    # 바이트 크기 계산
    @staticmethod
    def calculate_byte_size(string):
        return len(string.encode("utf-8")) + 6

    # 채팅창 연결이 해제되지 않게 주기적인 핑 전송
    async def _ping(self):
        ping_interval = 10

        try:
            while self.data.sock and not self.data.sock.state.name == "CLOSED":
                try:
                    # 핑 메시지 전송
                    await asyncio.sleep(0.0001)
                    await self.data.sock.send(self.PING_PACKET)
                except websockets.exceptions.ConnectionClosedOK as e:
                    break

                try:
                    await asyncio.wait_for(
                        asyncio.shield(self.data.sock.wait_closed()),
                        timeout=ping_interval,
                    )
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    await log_error(f"Error during ping wait: {str(e)}")
                    break

        except Exception as e:
            await log_error(f"Error in ping function: {str(e)}")

        # print(f"{datetime.now()} {self.data.channel_id} chat pong 종료")

    # 메시지 수신
    async def _receive_messages(self):
        # 연결 종료 여부 확인 함수
        async def should_close_connection():
            is_change_chatChannel = await self.check_change_chatChannel(join_time)
            check_chat = self.init.chat_json[self.data.channel_id]
            is_close = self.check_live_state_close()
            is_new_chatChannel = (
                self.title_data.loc[self.data.channel_id, "state_update_time"][
                    "is_firstConnect"
                ]
                and not is_close
            )
            is_old_chatChannel = (
                not if_after_time(self.state_update_time["openDate"], sec=300)
                and (if_after_time(self.data.last_chat_time, sec=60))
                and if_after_time(join_time, sec=30)
            )

            if self.run_analyzer and is_close or is_change_chatChannel or check_chat:
                asyncio.create_task(self.should_offLine())
                self.run_analyzer = False

            if (
                is_change_chatChannel
                or is_new_chatChannel
                or check_chat
                or is_old_chatChannel
            ):
                print(
                    f"{datetime.now()} should_close_connection {self.data.channel_name} is_change_chatChannel:{is_change_chatChannel},is_new_chatChannel:{is_new_chatChannel}, check_chat:{check_chat},is_old_chatChannel:{is_old_chatChannel}"
                )

            return (
                not self.run_analyzer
                and (is_change_chatChannel or is_new_chatChannel or check_chat)
                or is_old_chatChannel
            )

        # 메시지 버퍼링을 위한 변수들
        message_buffer = []
        buffer_size = 5
        buffer_timeout = 0.05
        last_buffer_flush = datetime.now().isoformat()
        join_time = datetime.now().isoformat()

        while True:
            try:
                # 연결 종료 조건 확인
                if await should_close_connection():
                    try:
                        await self.data.sock.close()
                        await self.data.sock.wait_closed()
                    except Exception:
                        pass

                # 소켓이 닫혔는지 확인
                if self.data.sock.state.name == "CLOSED":
                    asyncio.create_task(self.should_offLine())
                    asyncio.create_task(
                        log_error(
                            f"{self.data.channel_id}: 연결 종료",
                            webhook_url=environ["chat_post_url"],
                        )
                    )
                    break

                # 메시지 수신
                raw_message = await asyncio.wait_for(self.data.sock.recv(), timeout=1)
                # await self.data.message_queue.put(raw_message)

                # 메시지 버퍼에 추가
                message_buffer.append(raw_message)

                # 버퍼가 가득 차거나 일정 시간이 지나면 메시지 큐에 추가
                if len(message_buffer) >= buffer_size or if_after_time(
                    last_buffer_flush, sec=buffer_timeout
                ):
                    for msg in message_buffer:
                        await self.data.message_queue.put(msg)
                    message_buffer.clear()
                    last_buffer_flush = self.data.last_chat_time

            except asyncio.TimeoutError:
                # 타임아웃 시 버퍼 비우기
                if message_buffer:
                    for msg in message_buffer:
                        await self.data.message_queue.put(msg)
                    message_buffer.clear()
                    last_buffer_flush = self.data.last_chat_time
                continue

            except websockets.exceptions.ConnectionClosed:
                # 연결 종료 시 로그 기록
                asyncio.create_task(
                    log_error(
                        f"{self.data.channel_id}: 연결 비정상 종료",
                        webhook_url=environ["chat_post_url"],
                    )
                )
                try:
                    await self.data.sock.close()
                    await self.data.sock.wait_closed()
                except Exception:
                    pass

            except Exception as e:
                # 기타 예외 처리
                asyncio.create_task(
                    log_error(
                        f"{self.data.channel_id} afreeca chat test except {str(e)}"
                    )
                )
                try:
                    await self.data.sock.close()
                    await self.data.sock.wait_closed()
                except Exception:
                    pass

    # 채팅 채널 ID 가 다른지
    async def is_different_chatChannelId(self, BNO=None):
        if BNO is None:
            BNO = self.data.BNO

        if BNO != int(self.title_data.loc[self.data.channel_id, "chatChannelId"]):
            return True
        return False

    # 채팅 채널 ID 변경 함수
    async def change_chatChannelId(self, BNO=None):
        if BNO is None:
            BNO = self.data.BNO

        if BNO != int(self.title_data.loc[self.data.channel_id, "chatChannelId"]):
            self.title_data.loc[self.data.channel_id, "oldChatChannelId"] = (
                self.title_data.loc[self.data.channel_id, "chatChannelId"]
            )
            self.title_data.loc[self.data.channel_id, "chatChannelId"] = BNO
            self.state_update_time["changeChatChannelIdDate"] = (
                datetime.now().isoformat()
            )
            asyncio.create_task(
                save_airing_data(
                    self.init.supabase, self.title_data, "afreeca", self.data.channel_id, updated_keys={"chatChannelId", "oldChatChannelId", "state_update_time"},
                )
            )
            return True
        return False

    async def check_change_chatChannel(self, connect_time):
        if not if_after_time(
            self.state_update_time["openDate"], sec=60
        ) and if_after_time(connect_time, sec=60):
            BNO = int(self.title_data.loc[self.data.channel_id, "chatChannelId"])
            if BNO != self.data.BNO:
                print(
                    f"{datetime.now()} check {self.data.channel_id},{self.data.BNO},BNO check_live_state_close"
                )
                # asyncio.create_task(change_field_state("chat_json", self.init.chat_json, self.data.channel_id))
                return True
        return False

    # 메시지 디코딩 및 처리
    async def _decode_message(self):
        processing_pool = []
        max_concurrent_processing = 10

        while True:
            # 큐에서 메시지 가져오기
            bytes_data = await self.data.message_queue.get()
            # 메시지 분할 및 디코딩
            parts = bytes_data.split(b"\x0c")
            messages = [part.decode("utf-8", errors="ignore") for part in parts]

            try:
                # 메시지 처리 태스크 생성
                task = asyncio.create_task(self._process_single_message(messages))
                processing_pool.append(task)

                # 완료된 태스크 제거
                processing_pool = [t for t in processing_pool if not t.done()]

                # 동시 처리 태스크 수 제한
                if len(processing_pool) >= max_concurrent_processing:
                    _, pending = await asyncio.wait(
                        processing_pool, return_when=asyncio.FIRST_COMPLETED
                    )
                    processing_pool = list(pending)

            except Exception as e:
                # 메시지 처리 오류 로그
                asyncio.create_task(
                    log_error(f"Error processing message: {str(e)}, {str(messages)}")
                )
            finally:
                # 큐 작업 완료 신호
                self.data.message_queue.task_done()

    # 유저 채팅 데이터 얻기
    def get_user_chat(self, messages):
        user_id, chat, nickname, chat_type = None, None, None, "채팅"
        if len(messages) in [14, 16]:
            user_id, chat, nickname, chat_type = (
                messages[2],
                messages[1],
                messages[6],
                "채팅",
            )
        elif len(messages) == 11:
            user_id, chat, nickname, chat_type = (
                messages[2],
                messages[6],
                messages[3],
                "VOD 후원 알림",
            )
        elif len(messages) == 17:
            user_id, chat, nickname, chat_type = (
                messages[2],
                messages[16],
                messages[3],
                "구독선물",
            )  # 12,15,16 중 하나가 chat 5(설물 받은 사람), 6(방송 채널 id), 7(방송 채널 이름)
        elif len(messages) == 18:
            user_id, chat, nickname, chat_type = (
                messages[3],
                messages[7],
                messages[4],
                "애드벌룬 후원",
            )
        elif len(messages) == 19:
            user_id, chat, nickname, chat_type = (
                messages[6],
                messages[2],
                messages[7],
                "채팅",
            )
        elif len(messages) == 20:
            user_id, chat, nickname, chat_type = (
                messages[6],
                messages[2],
                messages[7],
                "이미지 챗",
            )
        else:
            asyncio.create_task(
                log_error(
                    f"messages,{messages}", webhook_url=environ["afreeca_chat_log_url"]
                )
            )

        return user_id, chat, nickname, chat_type

    # 단일 메시지 처리
    async def _process_single_message(self, messages):
        # 채팅방 입장, 퇴장 시 last_chat_time update
        if self._is_chat_connection(messages):
            self.data.last_chat_time = datetime.now().isoformat()
            return
        # 유효하지 않은 메시지 필터링
        if self._is_invalid_message(messages):
            if self.if_afreeca_chat(messages):
                asyncio.create_task(
                    log_error(
                        f"아프리카 chat recv messages {messages}",
                        webhook_url=environ["afreeca_chat_log_url"],
                    )
                )
            return

        # 메시지 정보 추출
        user_id, chat, nickname, chat_type = self.get_user_chat(messages)

        try:
            user_id = user_id.split("(")[0]
        except:
            asyncio.create_task(
                log_error(
                    f"messages2,{messages}", webhook_url=environ["afreeca_chat_log_url"]
                )
            )
            return

        # print(f"{datetime.now()} [{chat_type} - {self.data.channel_name}] {nickname}: {chat}")

        self.data.last_chat_time = datetime.now().isoformat()
        # 채팅 메시지인 경우 분석기로 전달
        if chat_type in ["채팅", "이미지 챗"]:

            if nickname and chat:
                # 분석기로 메시지 전달
                await self.chat_analyzer.add_chat_message(nickname, chat)

        # 테스트 모드가 아니고 필터링된 채널이 아니면 무시
        if user_id not in self.init.chatFilter["afreeca"].index:
            return

        # 사용자 정보 가져오기
        user_nick, profile_image = await self._get_user_info(user_id)
        if nickname != user_nick:
            return

        await change_nickname(self.init, user_id, nickname, "afreeca")

        # 메시지 중복 체크 및 처리
        self._process_new_message(user_id, chat)

        # 채팅 메시지 포스팅
        asyncio.create_task(self._post_chat(nickname, chat, profile_image, chat_type))

    # 채팅 메시지 전송
    async def _post_chat(self, nickname, chat, profile_image, chat_type):
        async with self.post_chat_semaphore:
            try:
                # 채팅 데이터 생성
                json_data = get_chat_json_data(
                    nickname, chat, self.data.channel_name, profile_image
                )

                # 전송할 URL 목록 가져오기
                list_of_urls = get_list_of_urls(
                    self.init.DO_TEST,
                    self.init.userStateData,
                    nickname,
                    self.data.channel_id,
                    "chat_user_json",
                )

                # 푸시 알림 및 디스코드 웹훅 전송
                asyncio.create_task(send_push_notification(list_of_urls, json_data))
                asyncio.create_task(
                    self.DiscordWebhookSender_class.send_messages(
                        list_of_urls, json_data, DO_TEST=self.init.DO_TEST
                    )
                )

                # print(f"{datetime.now()} post chat [{chat_type} - {self.data.channel_name}] {nickname}: {chat}")

            except Exception as e:
                asyncio.create_task(log_error(f"error postChat: {str(e)}"))

    # 유저 정보 가져오기
    async def _get_user_info(self, user_id):
        try:
            for _ in range(3):
                stateData = await get_message(
                    self.performance_manager, "afreeca", afreeca_getLink(user_id)
                )
                if not stateData:
                    continue
                break

            if not stateData:
                return None, None

            user_nick = stateData["station"]["user_nick"]
            _, _, profile_image = afreeca_getChannelOffStateData(
                stateData, stateData["station"]["user_id"]
            )
        except Exception as e:
            asyncio.create_task(
                log_error(
                    f"Error in _get_user_info: {str(e)}",
                    webhook_url=environ["afreeca_chat_log_url"],
                )
            )
            asyncio.create_task(
                log_error(
                    f"stateData,{stateData}",
                    webhook_url=environ["afreeca_chat_log_url"],
                )
            )
        return user_nick, profile_image

    # 새 메시지 처리  (중복 방지)
    def _process_new_message(self, user_id, chat):
        message_id = f"{user_id}_{chat}_{time()}"

        # 이미 처리된 메시지인지 확인
        if message_id in self.data.processed_messages:
            asyncio.create_task(log_error(f"중복 메시지 무시: {chat}"))
            return

        # 새 메시지 처리
        self.data.processed_messages.append(message_id)

        # 메시지 리스트 크기 제한 (최근 20개만 유지)
        if len(self.data.processed_messages) > 20:
            self.data.processed_messages.pop(0)

    def _is_chat_connection(self, messages):
        # arr = ['\x1b\t000400003800', '1', 'kimboxu', '코딩노예_', '65536|163840', ''] # 방송 접속
        return len(messages) == 6 and messages[1] in ["-1", "", "1"]

    # 메시지 유효성 검사
    def _is_invalid_message(self, messages):
        # 메시지가 유효하지 않은지 확인
        return (
            len(messages) < 10
            or len(messages) == 10  # 매니저가 해당 유저 차단?
            or messages[1] in ["-1", "", "1"]
            or len(messages[2]) == 0
            or messages[2] in ["1"]
            or messages[1] == self.data.BID
            or (messages[2] == self.data.BID and len(messages) == 11)
            or ("fw" in messages[2])
            or len(messages) == 13
            or len(messages) == 21 # 이미지 후원? 혹은 이모티콘?
        )

    # 아프리카 채팅 메시지 체크
    def if_afreeca_chat(self, messages):
        # 기본 제외 조건들을 리스트로 정의
        excluded_values = {"-1", "1", "", "0", "2", "4"}

        # 빈 리스트 확인
        if not messages or len(messages) == 1:
            return 0

        # 인덱스 범위 확인
        if len(messages) <= 2:
            return 0

        # 첫 번째 검사: messages[1] 확인 (인덱스 검사는 이미 위에서 했음)
        if (
            messages[1] in excluded_values
            or isinstance(messages[1], str)
            and "|" in messages[1]
            or "CHALLENGE_GIFT" in messages[1]
        ):
            return 0

        # messages[2] 인덱스 및 타입 확인
        if (
            not isinstance(messages[2], str)
            or "fw" in messages[2]
            or messages[2] in {"-1", "1", "", "0"}
            or "|" in messages[2]
        ):
            return 0

        # 특정 문자열 체크
        message_str = str(messages)
        if (
            "png" in message_str
            or "https://smartstore.naver.com" in message_str
            or "씨발" in message_str
        ):
            return 0

        # messages[7] 체크 (인덱스 확인 필요)
        if len(messages) >= 8 and isinstance(messages[7], str) and "|" in messages[7]:
            return 0

        # messages[1] 이 BID 인 경우 or messages[2] 가  BID 면서 길이가 11인 경우
        user_id = messages[1].split("(")[0]
        if user_id == self.data.BID or (
            messages[2] == self.data.BID and len(messages) == 11
        ):
            return 0

        # len(messages) < 11인지
        if len(messages) < 11:
            return 0

        if len(messages) == 13:
            return 0
        
        if len(messages) == 21: # 이미지 후원? 혹은 이모티콘?
            return 0

        return 1

    # 비밀번호 설정 여부 확인
    async def check_is_passwordDict(self):
        stateData = await get_message(
            self.performance_manager,
            "afreeca",
            afreeca_getLink(self.init.IDList["afreeca"]["uid"][self.data.channel_id]),
        )
        return (
            isinstance(stateData, dict)
            and isinstance(stateData.get("broad"), dict)
            and stateData["broad"].get("is_password", False)
        )

    # 방송 종료 여부 확인
    def check_live_state_close(self):
        try:
            return self.title_data.loc[self.data.channel_id, "live_state"] == "CLOSE"
        except Exception as e:
            asyncio.create_task(log_error(f"Error in check_live_state_close: {str(e)}"))
            return True

    # 채널 상태 데이터 가져오기
    async def afreeca_getChannelStateData(self):
        url = "https://live.sooplive.co.kr/afreeca/player_live_api.php"
        data = {
            "bid": self.data.BID,
            "bno": self.data.BNO,
            "type": "live",
            "pwd": "",
            "player_type": "html5",
            "stream_type": "common",
            "quality": "HD",
            "mode": "landing",
            "from_api": "0",
            "is_revive": "false",
        }

        try:
            # API 요청으로 채널 상태 데이터 가져오기
            async with ClientSession(connector=TCPConnector(ssl=False)) as session:
                async with session.post(
                    f"{url}?bjid={self.data.BID}",
                    data=data,
                    headers=getDefaultHeaders(),
                    cookies=getAfreecaCookie(),
                ) as response:
                    res = loads(await response.text())

        except Exception as e:
            asyncio.create_task(log_error(f"error get player live {str(e)}"))
            return False

        # 방송 상태 및 제목 정보 추출
        self.stream_type_state = res["CHANNEL"]["RESULT"]
        self.TITLE = res["CHANNEL"].get("TITLE", None)

        # 성인, 구독 플러스 채널 처리
        if self.stream_type_state in [
            self.adult_channel_state,
            self.subscription_Plus,
            self.black_list,
        ]:  # 연령제한 채널로 썸네일링크 못 읽을 경우
            thumbnail_url = f"https://liveimg.afreecatv.com/m/{self.data.BNO}"
            BNO = self.data.BNO
            return False

        # 방송 중인 경우 필요한 정보 추출
        if self.stream_type_state:
            try:
                BNO = int(res["CHANNEL"]["BNO"])
            except:
                asyncio.create_task(log_error(f"error res['CHANNEL']['BNO'] None"))

            thumbnail_url = f"https://liveimg.afreecatv.com/m/{res['CHANNEL']['BNO']}"

            self.data.BNO = BNO
            self.CHDOMAIN = res["CHANNEL"]["CHDOMAIN"].lower()
            self.CHATNO = res["CHANNEL"]["CHATNO"]

            try:
                FTK = res["CHANNEL"]["FTK"]
            except Exception as e:
                FTK = None
                # asyncio.create_task(log_error(f"{datetime.now()} error afreeca FTK {res}"))

            try:
                BJID = res["CHANNEL"]["BJID"]
            except Exception as e:
                BJID = None
                asyncio.create_task(
                    log_error(f"{datetime.now()} error afreeca BJID {res}")
                )

            self.CHPT = str(int(res["CHANNEL"]["CHPT"]) + 1)
            return True

        return False
