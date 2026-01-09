import asyncio
import threading
import nest_asyncio
from os import environ
from datetime import datetime
from dotenv import load_dotenv
from base import initVar, userDataVar, fCount, fSleep, log_error
from shared_state import StateManager
from Chzzk_chat_message import chzzk_chat_message
from Afreeca_chat_message import afreeca_chat_message
from getCafePostTitle import getCafePostTitle
from getYoutubeJsonData import getYoutubeJsonData
from live_message import chzzk_live_message, afreeca_live_message
from unified_vod import chzzk_vod, afreeca_vod
from unified_hot_clip import ChzzkHotClipDetector, AfreecaHotClipDetector
from notification_service import initialize_firebase, cleanup_all_invalid_tokens, setup_scheduled_tasks
from make_log_api_performance import PerformanceManager


# 비동기 이벤트 루프를 중첩해서 사용할 수 있도록 설정
nest_asyncio.apply()

# 환경 변수 로드
load_dotenv()

# 전역 상태 관리자
state_manager = StateManager.get_instance()

# Flask 앱 설정 함수
def setup_flask_app():
    from my_app import app, init_background_tasks
    
    # 상태 관리자에서 init 가져오기
    with app.app_context():
        app.init = state_manager.get_init()
        if app.init is None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            app.init = loop.run_until_complete(state_manager.initialize())
    
    return app

def get_or_create_instance(instance_type, init, performance_manager, channel_id):
    """인스턴스를 가져오거나 생성하는 헬퍼 함수"""
    # StateManager에서 인스턴스 확인
    existing_instance = state_manager.get_instance_by_type(instance_type, channel_id)
    
    if existing_instance is not None:
        return existing_instance
    
    # 인스턴스가 없으면 새로 생성
    new_instance = None
    
    if instance_type == 'cafe':
        new_instance = getCafePostTitle(init, performance_manager, channel_id)
    elif instance_type == 'chzzk_video':
        new_instance = chzzk_vod(init, performance_manager, channel_id)
    elif instance_type == 'afreeca_video':
        new_instance = afreeca_vod(init, performance_manager, channel_id)
    elif instance_type == 'chzzk_live':
        new_instance = chzzk_live_message(init, performance_manager, channel_id)
    elif instance_type == 'afreeca_live':
        new_instance = afreeca_live_message(init, performance_manager, channel_id)
    elif instance_type == 'chzzk_chat':
        new_instance = chzzk_chat_message(init, performance_manager, channel_id)
    elif instance_type == 'afreeca_chat':
        new_instance = afreeca_chat_message(init, performance_manager, channel_id)
    elif instance_type == 'chzzk_hot_clips':
        new_instance = ChzzkHotClipDetector(init, performance_manager, channel_id)
    elif instance_type == 'afreeca_hot_clips':
        new_instance = AfreecaHotClipDetector(init, performance_manager, channel_id)
    
    # 생성된 인스턴스를 StateManager에 저장
    if new_instance is not None:
        state_manager.set_instance(instance_type, channel_id, new_instance)
    
    return new_instance

# 디스코드 봇 메인 루프
async def main_loop(init: initVar, performance_manager: PerformanceManager):
    while True:
        try:
            if init.count % 2 == 0: 
                await userDataVar(init)

            # 기존 인스턴스를 재사용하여 태스크 생성
            cafe_tasks = [
                asyncio.create_task(
                    get_or_create_instance('cafe', init, performance_manager, channel_id).start()
                ) 
                for channel_id in init.cafeData["channelID"]
            ]
            
            chzzk_video_tasks = [
                asyncio.create_task(
                    get_or_create_instance('chzzk_video', init, performance_manager, channel_id).start()
                ) 
                for channel_id in list(init.IDList["chzzk"].index)
            ]

            afreeca_video_tasks = [
                asyncio.create_task(
                    get_or_create_instance('afreeca_video', init, performance_manager, channel_id).start()
                ) 
                for channel_id in list(init.IDList["afreeca"].index)
            ]
            
            chzzk_live_tasks = [
                asyncio.create_task(
                    get_or_create_instance('chzzk_live', init, performance_manager, channel_id).start()
                ) 
                for channel_id in list(init.IDList["chzzk"].index)
            ]
            
            afreeca_live_tasks = [
                asyncio.create_task(
                    get_or_create_instance('afreeca_live', init, performance_manager, channel_id).start()
                ) 
                for channel_id in list(init.IDList["afreeca"].index)
            ]

            tasks = []
            
            if init.count % 2 == 0: 
                tasks.extend(chzzk_live_tasks)
            if init.count % 2 == 1: 
                tasks.extend(afreeca_live_tasks) 
            if init.count % 3 == 2: 
                tasks.extend(chzzk_video_tasks)
            if init.count % 3 == 0:
                tasks.extend(afreeca_video_tasks)
            if init.count % 3 == 1: 
                tasks.extend(cafe_tasks)

            await asyncio.gather(*tasks)
            await fSleep(init)
            fCount(init)

        except Exception as e:
            asyncio.create_task(log_error(f"Error in main loop: {str(e)}"))
            await asyncio.sleep(1)

# 유튜브 작업 함수
async def youtube_task(init: initVar, performance_manager: PerformanceManager):
    from random import shuffle
    await asyncio.sleep(2)

    developer_keys = environ['developerKeyList'].split(",")
    YoutubeChannelID_list = list(init.youtubeData["YoutubeChannelID"]).copy()
    if init.DO_TEST:
        return
    while True:
        try:
            shuffle(YoutubeChannelID_list)
            for youtubeChannelID in YoutubeChannelID_list:
                if not init.is_state_control["is_youtube"]:
                    await asyncio.sleep(3)
                    continue
                    
                start_time = asyncio.get_event_loop().time()
                
                # 작업 실행
                developerKey = developer_keys[init.youtube_key_index//len(init.youtubeData["YoutubeChannelID"])]
                await asyncio.create_task(getYoutubeJsonData(init, performance_manager, developerKey, youtubeChannelID).start())
                
                # 다음 키로 순환
                init.youtube_key_index = (init.youtube_key_index + 1) % (len(developer_keys) * len(init.youtubeData["YoutubeChannelID"]))
                
                # 정확히 3초 간격 유지
                elapsed_time = asyncio.get_event_loop().time() - start_time
                await asyncio.sleep(max(3 - elapsed_time, 0))
            
        except Exception as e:
            print(f"{datetime.now()} YouTube 작업 오류: {str(e)}")
            await asyncio.sleep(3)

# 채팅 작업 함수
async def generic_chat(init: initVar, performance_manager: PerformanceManager, platform: str):
    await asyncio.sleep(3)
    
    tasks = {}  # 채널 ID별 실행 중인 task를 관리할 딕셔너리
    
    while True:
        try:
            chat_class = f'{platform}_chat'
            # 기존 실행 중인 태스크를 유지하면서, 새로운 채널이 추가되면 실행
            for channel_id in list(init.IDList[platform].index):
                if channel_id not in tasks or tasks[channel_id].done():
                    # StateManager를 활용하여 인스턴스 생성/재사용
                    chat_instance = get_or_create_instance(chat_class, init, performance_manager, channel_id)
                    tasks[channel_id] = asyncio.create_task(chat_instance.start())
            
            await asyncio.sleep(1)  # 1초마다 체크
        
        except Exception as e:
            print(f"{datetime.now()} error {platform}_chatf {str(e)}")
            await asyncio.create_task(log_error(f"Error in {platform}_chatf: {str(e)}"))
            await asyncio.sleep(1)

# 핫클립 작업
async def generic_hot_clip(init: initVar, performance_manager: PerformanceManager, platform: str):
    await asyncio.sleep(3)
    
    tasks = {}
    
    while True:
        try:
            hot_clip_class = f'{platform}_hot_clips'
            
            # 각 채널별 모니터링 태스크 관리
            for channel_id in list(init.IDList[platform].index):
                if channel_id not in tasks or tasks[channel_id].done():
                    hot_clip_instance = get_or_create_instance(hot_clip_class, init, performance_manager, channel_id)
                    tasks[channel_id] = asyncio.create_task(hot_clip_instance.start_monitoring())
            
            await asyncio.sleep(60)
            
        except Exception as e:
            await log_error(f"{platform} 핫클립 모니터링 오류: {str(e)}")
            await asyncio.sleep(60)

# 디스코드 봇 작업 실행 함수
async def run_discord_bot():
    # 상태 관리자에서 init 가져오기
    init = state_manager.get_init()
    performance_manager = state_manager.get_performance_manager()
    init = await state_manager.initialize()

    #정기적인 작업 스케줄러 설정
    performance_manager.setup_scheduler()
    print("성능 통계 스케줄러가 시작되었습니다.")
    
    # Firebase 초기화
    initialize_firebase(False)

    # 모든 작업 동시 실행
    bot_tasks = [
        asyncio.create_task(main_loop(init, performance_manager)),
        asyncio.create_task(generic_chat(init, performance_manager, 'chzzk')),
        asyncio.create_task(generic_chat(init, performance_manager, 'afreeca')),
        asyncio.create_task(generic_hot_clip(init, performance_manager, 'chzzk')),
        asyncio.create_task(generic_hot_clip(init, performance_manager, 'afreeca')),
        asyncio.create_task(youtube_task(init, performance_manager)),
    ]
    
    await asyncio.gather(*bot_tasks)

# 디스코드 봇 실행 스레드 함수
def run_bot_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # FCM 토큰 정리 작업 실행
    loop.run_until_complete(cleanup_all_invalid_tokens())
    print("FCM 토큰 정리 작업이 완료되었습니다.")
    
    # 예약 작업 설정
    setup_scheduled_tasks()
    
    # 디스코드 봇 실행
    loop.run_until_complete(run_discord_bot())

# 메인 함수
def main():
    # Firebase 초기화 (한 번만)
    firebase_initialized = initialize_firebase(False)
    if not firebase_initialized:
        print("경고: Firebase 초기화에 실패했습니다. 푸시 알림 기능이 작동하지 않을 수 있습니다.")
    # 디스코드 봇 스레드 시작
    bot_thread = threading.Thread(target=run_bot_thread, daemon=True)
    bot_thread.start()
    
    # Flask 앱 설정 및 실행
    app = setup_flask_app()
    app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)

if __name__ == "__main__":
    main()