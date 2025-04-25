import asyncio
from os import environ
from time import gmtime
from datetime import datetime
from urllib.parse import quote
from dataclasses import dataclass
from discord_webhook_sender import DiscordWebhookSender, get_list_of_urls

from base import (
    initVar,
    subjectReplace, 
    afreeca_getChannelOffStateData, 
    chzzk_getChannelOffStateData, 
    get_message, 
    iconLinkData, 
    chzzk_getLink, 
    afreeca_getLink, 
    saveCafeData)

from my_app import send_push_notification

@dataclass
class CafePostData:
    cafe_link: str
    menu_id: str
    menu_name: str
    subject: str
    image: str
    write_timestamp: str
    writer_nickname: str
    
class getCafePostTitle:
    def __init__(self, init_var: initVar, channel_id):
        self.DO_TEST: bool = init_var.DO_TEST
        self.userStateData = init_var.userStateData
        self.cafeData = init_var.cafeData
        self.channel_id: str = channel_id

    async def start(self):
        try:
            self.message_list: list = []
            await self.getCafeDataDic()
            await self.postCafe()
                
        except Exception as e:
            asyncio.create_task(DiscordWebhookSender._log_error(f"error cafe {self.channel_id}.{e}"))

    async def getCafeDataDic(self):
        BASE_URL = f"https://apis.naver.com/cafe-web/cafe2/ArticleListV2dot1.json,{str(self.cafeData.loc[self.channel_id, 'cafeNum'])}"
        response = await get_message("cafe", BASE_URL)

        cafe_json = self.cafeData.loc[self.channel_id, 'cafe_json']
        cafe_json_ref_articles = cafe_json["refArticleId"]
        max_ref_article = max(cafe_json_ref_articles) if cafe_json_ref_articles else 0
        update_time = int(self.cafeData.loc[self.channel_id, 'update_time'])
        cafe_name_dict = self.cafeData.loc[self.channel_id, "cafeNameDict"]
     
        try:
            self._process_article_list(response, cafe_name_dict, max_ref_article, update_time, cafe_json_ref_articles)
        except Exception as e:
            asyncio.create_task(DiscordWebhookSender._log_error(f"게시글 처리 중 오류 발생: {e}"))

        return

    def _process_article_list(self, request, cafe_name_dict, max_ref_article, update_time, cafe_json_ref_articles):
        """
        Args:
            request: API 요청 결과
            cafe_name_dict: 필터링할 작성자 닉네임 딕셔너리
            max_ref_article: 가장 최근의 현재까지의 게시글 ID
            update_time: 마지막 업데이트 시간
            cafe_json_ref_articles: 게시글 ID 목록들
        """
        article_list = request.get('message', {}).get('result', {}).get('articleList', [])
        
        for article in reversed(article_list):
            # 필터링 조건 확인
            if article["writerNickname"] not in cafe_name_dict:
                continue
                
            if not (article["refArticleId"] > max_ref_article and article['writeDateTimestamp'] > update_time):
                continue
            
            # 게시글 제목 정리
            article["subject"] = subjectReplace(article["subject"])
            
            # 최신 업데이트 시간 갱신
            self.cafeData.loc[self.channel_id, 'update_time'] = max(
                self.cafeData.loc[self.channel_id, 'update_time'], 
                article["writeDateTimestamp"]
            )
            
            # 참조 게시글 ID 목록 업데이트 (최대 10개 유지)
            self._update_ref_article_ids(cafe_json_ref_articles, article["refArticleId"])
            
            # 카페 게시글 데이터 객체 생성 및 추가
            self._add_cafe_post(article)

    def _update_ref_article_ids(self, ref_article_ids, new_id):
        """
        Args:
            ref_article_ids: 참조 게시글 ID 목록
            new_id: 추가할 새 게시글 ID
        """
        if len(ref_article_ids) >= 10:
            ref_article_ids[:-1] = ref_article_ids[1:]
            ref_article_ids[-1] = new_id
        else:
            ref_article_ids.append(new_id)

    def _add_cafe_post(self, article):
        """
        Args:
            article: 게시글 데이터
        """
        cafeID = self.cafeData.loc[self.channel_id, 'cafeID']
        cafe_post = CafePostData(
            cafe_link=f"https://cafe.naver.com/{cafeID}/{article['refArticleId']}",
            menu_id=article["menuId"],
            menu_name=article["menuName"],
            subject=article["subject"],
            image=article.get("representImage", ""),
            write_timestamp=article["writeDateTimestamp"],
            writer_nickname=article["writerNickname"]
        )
        self.message_list.append(cafe_post)

    async def postCafe(self):
        try:
            if not self.message_list:
                return
            
            for post_data in self.message_list:
                json_data = await self.create_cafe_json(post_data)
                print(f"{datetime.now()} {post_data.writer_nickname} post cafe {post_data.subject}")

                list_of_urls = get_list_of_urls(self.DO_TEST, self.userStateData, post_data.writer_nickname, self.channel_id, "cafe_user_json")

                asyncio.create_task(send_push_notification(list_of_urls, json_data))
                asyncio.create_task(DiscordWebhookSender().send_messages(list_of_urls, json_data))

            await saveCafeData(self.cafeData, self.channel_id)
            
        except Exception as e:
            asyncio.create_task(DiscordWebhookSender._log_error(f"error postCafe {e}"))
            self.message_list.clear()

    async def create_cafe_json(self, post_data: CafePostData) -> dict:
        def getTime(timestamp):
            tm = gmtime(timestamp/1000)
            return f"{tm.tm_year}-{tm.tm_mon:02d}-{tm.tm_mday:02d}T{tm.tm_hour:02d}:{tm.tm_min:02d}:{tm.tm_sec:02d}Z"
    
        cafe_info = self.cafeData.loc[self.channel_id]
        menu_url = (f"https://cafe.naver.com/{cafe_info['cafeID']}"
                f"?iframe_url=/ArticleList.nhn%3F"
                f"search.clubid={int(cafe_info['cafeNum'])}"
                f"%26search.menuid={post_data.menu_id}")

        embed = {
            "author": {
                "name": post_data.menu_name,
                "url": menu_url,
            },
            "color": 248125,
            "title": post_data.subject,
            "url": post_data.cafe_link,
            "thumbnail": {
                "url": quote(post_data.image, safe='/%:@&=+$,!?*\'()')
            },
            "footer": {
                "text": "cafe",
                "inline": True,
                "icon_url": iconLinkData().cafe_icon
            },
            "timestamp": getTime(post_data.write_timestamp)
        }

        return {
            "username": f"[카페 알림] {cafe_info['cafeName']} - {post_data.writer_nickname}",
            "avatar_url": await self.get_cafe_thumbnail_url(post_data.writer_nickname),
            "embeds": [embed]
        }
        
    async def get_cafe_thumbnail_url(self, writerNickname: str) -> str:
        # 미리 정의된 플랫폼별 API 요청 구성
        platform_config = {
            "afreeca": {
                "get_link": afreeca_getLink,
                "process_data": afreeca_getChannelOffStateData,
            },
            "chzzk": {
                "get_link": chzzk_getLink,
                "process_data": chzzk_getChannelOffStateData,
                "content_path": lambda data: data["content"]
            }
        }
        
        try:
            # 작성자 정보 가져오기
            if writerNickname not in self.cafeData.loc[self.channel_id, "cafeNameDict"]:
                return environ['default_thumbnail']  # 기본 썸네일
                
            cafe_info = self.cafeData.loc[self.channel_id, "cafeNameDict"][writerNickname]
            platform, user_id, current_thumbnail = cafe_info[1], cafe_info[0], cafe_info[2]
            
            if platform not in platform_config:
                return current_thumbnail
            config = platform_config[platform]
            
            data = await get_message(platform, config["get_link"](user_id))
            # 응답 데이터 처리
            if "content_path" in config:
                data = config["content_path"](data)
                
            # 썸네일 URL 추출
            _, _, profile_image = config["process_data"](
                data,
                user_id,
                current_thumbnail
            )
            
            # 새 썸네일 URL 저장
            self.cafeData.loc[self.channel_id, "cafeNameDict"][writerNickname][2] = profile_image
            return profile_image

        except Exception as e:
            error_msg = f"카페 썸네일 가져오기 실패 (작성자: {writerNickname}, 플랫폼: {platform if 'platform' in locals() else 'unknown'}): {str(e)}"
            asyncio.create_task(DiscordWebhookSender._log_error(error_msg))
            
            # 오류 발생 시 기존 썸네일 반환
            return current_thumbnail if 'current_thumbnail' in locals() else None
  
# 사용 예:
# async def main():
#     init = ... # 초기화 객체
#     cafe_post_title = getCafePostTitle()
#     await cafe_post_title.fCafeTitle(init)

# asyncio.run(main())
