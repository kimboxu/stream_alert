from os import environ
# import base
from base import userDataVar, fCount, fSleep, initVar
import asyncio
from time import time
from datetime import datetime
from shared_state import StateManager
from Twitch_live_message import twitch_live_message
# from Chzzk_live_message import chzzk_live_message
# from Afreeca_live_message import afreeca_live_message
from Chzzk_chat_message import chzzk_chat_message
from Afreeca_chat_message import afreeca_chat_message
from Chzzk_video import chzzk_video
from getCafePostTitle import getCafePostTitle
from getYoutubeJsonData import getYoutubeJsonData
from discord_webhook_sender import DiscordWebhookSender

from live_message import chzzk_live_message, afreeca_live_message

async def main_loop(init: initVar):

    while True:
        try:
            if init.count % 2 == 0: await userDataVar(init)

            cafe_tasks = [asyncio.create_task(getCafePostTitle(init, channel_id).start()) for channel_id in init.cafeData["channelID"]]
            chzzk_video_tasks = [asyncio.create_task(chzzk_video(init, channel_id).start()) for channel_id in init.chzzkIDList["channelID"]]
            chzzk_live_tasks = [asyncio.create_task(chzzk_live_message(init, channel_id).start()) for channel_id in init.chzzkIDList["channelID"]]
            afreeca_live_tasks = [asyncio.create_task(afreeca_live_message(init, channel_id).start()) for channel_id in init.afreecaIDList["channelID"]]
            
            tasks = [
                *chzzk_live_tasks,
                *afreeca_live_tasks,
                *chzzk_video_tasks,
                *cafe_tasks
            ]

            await asyncio.gather(*tasks)
            await fSleep(init)
            fCount(init)

        except Exception as e:
            asyncio.create_task(DiscordWebhookSender._log_error(f"Error in main loop: {str(e)}"))
            await asyncio.sleep(1)

async def youtube_task(init: initVar):
    await asyncio.sleep(2)

    developer_keys = environ['developerKeyList'].split(",")
    key_index = 0
    while True:
        try:
            for youtubeChannelID in init.youtubeData["YoutubeChannelID"]:
                if not init.youtube_TF:
                    await asyncio.sleep(3)
                    continue
                    
                start_time = time()
                
                # 작업 실행
                developerKey = developer_keys[key_index]
                await asyncio.create_task(getYoutubeJsonData(init, developerKey, youtubeChannelID).start())
                
                # 다음 키로 순환
                key_index = (key_index + 1) % len(developer_keys)
                
                # 정확히 3초 간격 유지
                elapsed_time = time() - start_time
                await asyncio.sleep(max(3 - elapsed_time, 0))
            
        except Exception as e:
            print(f"{datetime.now()} YouTube 작업 오류: {e}")
            await asyncio.sleep(3)

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
    state = StateManager.get_instance()
    init = await state.initialize()
    from my_app import initialize_firebase
    initialize_firebase(False)

    test = [
        asyncio.create_task(main_loop(init)),
        asyncio.create_task(generic_chat(init, 'afreeca', afreeca_chat_message)),
        asyncio.create_task(generic_chat(init, 'chzzk', chzzk_chat_message)),
        asyncio.create_task(youtube_task(init)),
    ]
    
    await asyncio.gather(*test)
        
if __name__ == "__main__":
    asyncio.run(main())