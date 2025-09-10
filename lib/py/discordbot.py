from os import environ
# import base
from base import userDataVar, fCount, fSleep, initVar, log_error
import asyncio
from time import time
from datetime import datetime
from shared_state import StateManager
# from Twitch_live_message import twitch_live_message
# from Chzzk_live_message import chzzk_live_message
# from Afreeca_live_message import afreeca_live_message
from Chzzk_chat_message import chzzk_chat_message
from Afreeca_chat_message import afreeca_chat_message
from Chzzk_video import chzzk_video
from getCafePostTitle import getCafePostTitle
from getYoutubeJsonData import getYoutubeJsonData
from make_log_api_performance import PerformanceManager
from live_message import chzzk_live_message, afreeca_live_message

GLOBAL_INSTANCES = {
    'cafe': {},
    'chzzk_video': {},
    'chzzk_live': {},
    'afreeca_live': {}
}

def get_or_create_instance(instance_type, init, performance_manager, channel_id):
    """인스턴스를 가져오거나 생성하는 헬퍼 함수"""
    instances = GLOBAL_INSTANCES[instance_type]
    
    if channel_id not in instances:
        if instance_type == 'cafe':
            instances[channel_id] = getCafePostTitle(init, performance_manager, channel_id)
        elif instance_type == 'chzzk_video':
            instances[channel_id] = chzzk_video(init, performance_manager, channel_id)
        elif instance_type == 'chzzk_live':
            instances[channel_id] = chzzk_live_message(init, performance_manager, channel_id)
        elif instance_type == 'afreeca_live':
            instances[channel_id] = afreeca_live_message(init, performance_manager, channel_id)
    
    return instances[channel_id]

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
                for channel_id in init.chzzkIDList["channelID"]
            ]
            
            chzzk_live_tasks = [
                asyncio.create_task(
                    get_or_create_instance('chzzk_live', init, performance_manager, channel_id).start()
                ) 
                for channel_id in init.chzzkIDList["channelID"]
            ]
            
            afreeca_live_tasks = [
                asyncio.create_task(
                    get_or_create_instance('afreeca_live', init, performance_manager, channel_id).start()
                ) 
                for channel_id in init.afreecaIDList["channelID"]
            ]
            
            tasks = []

            if init.count % 2 == 0: 
                tasks.extend(chzzk_live_tasks)
            if init.count % 2 == 1: 
                tasks.extend(afreeca_live_tasks) 
            if init.count % 3 == 2: 
                tasks.extend(chzzk_video_tasks) 
            if init.count % 3 == 1: 
                tasks.extend(cafe_tasks) 

            await asyncio.gather(*tasks)
            await fSleep(init)
            fCount(init)

        except Exception as e:
            asyncio.create_task(log_error(f"Error in main loop: {str(e)}"))
            await asyncio.sleep(1)

async def youtube_task(init: initVar, performance_manager: PerformanceManager):
    await asyncio.sleep(2)

    developer_keys = environ['developerKeyList'].split(",")
    key_index = 0
    if init.DO_TEST:
        return
    while True:
        try:
            for youtubeChannelID in init.youtubeData["YoutubeChannelID"]:
                if not init.youtube_TF:
                    await asyncio.sleep(3)
                    continue
                    
                start_time = time()
                
                # 작업 실행
                developerKey = developer_keys[key_index]
                await asyncio.create_task(getYoutubeJsonData(init, performance_manager, developerKey, youtubeChannelID).start())
                
                # 다음 키로 순환
                key_index = (key_index + 1) % len(developer_keys)
                
                # 정확히 3초 간격 유지
                elapsed_time = time() - start_time
                await asyncio.sleep(max(3 - elapsed_time, 0))
            
        except Exception as e:
            print(f"{datetime.now()} YouTube 작업 오류: {e}")
            await asyncio.sleep(3)

async def generic_chat(init: initVar, performance_manager: PerformanceManager, platform_name: str, message_class):
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
                    chat_instance = message_class(init, performance_manager, channel_id)
                    tasks[channel_id] = asyncio.create_task(chat_instance.start())
            
            await asyncio.sleep(1)  # 1초마다 체크 (필요하면 조절 가능)
        
        except Exception as e:
            print(f"{datetime.now()} error {platform_name}_chatf {e}")
            await asyncio.create_task(log_error(f"Error in {platform_name}_chatf: {str(e)}"))
            await asyncio.sleep(1)

async def main():
    state = StateManager.get_instance()
    init = state.get_init()
    performance_manager = state.get_performance_manager()
    if init is None: init = await state.initialize()
    from my_app import initialize_firebase
    initialize_firebase(False)

    test = [
        asyncio.create_task(main_loop(init, performance_manager)),
        asyncio.create_task(generic_chat(init, performance_manager, 'afreeca', afreeca_chat_message)),
        asyncio.create_task(generic_chat(init, performance_manager, 'chzzk', chzzk_chat_message)),
        asyncio.create_task(youtube_task(init, performance_manager)),
    ]
    
    await asyncio.gather(*test)
        
if __name__ == "__main__":
    asyncio.run(main())