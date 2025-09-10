import asyncio
from os import environ
from time import gmtime
from datetime import datetime
from urllib.parse import quote
from dataclasses import dataclass
from discord_webhook_sender import DiscordWebhookSender, get_list_of_urls
from make_log_api_performance import PerformanceManager
from base import (
    initVar,
    subjectReplace, 
    afreeca_getChannelOffStateData, 
    chzzk_getChannelOffStateData, 
    get_message, 
    iconLinkData, 
    chzzk_getLink, 
    afreeca_getLink, 
    saveCafeData,
    log_error,
    )

from notification_service import send_push_notification

# 카페 게시글 데이터를 저장하는 데이터 클래스
@dataclass
class CafePostData:
    cafe_link: str         # 게시글 링크
    menu_id: str           # 카페 게시판 ID
    menu_name: str         # 카페 게시판 이름
    subject: str           # 게시글 제목
    image: str             # 게시글 대표 이미지
    write_timestamp: str   # 작성 시간
    writer_nickname: str   # 작성자 닉네임
    
class getCafePostTitle:
    # 초기화 함수: 필요한 데이터와 채널 ID 설정
    def __init__(self, init_var: initVar, performance_manager: PerformanceManager, channel_id):
        self.DO_TEST: bool = init_var.DO_TEST                # 테스트 모드 여부
        self.userStateData = init_var.userStateData          # 사용자 상태 데이터
        self.cafeData = init_var.cafeData                    # 카페 데이터
        self.channel_id: str = channel_id                    # 채널 ID
        self.performance_manager = performance_manager

    async def start(self):
        try:
            self.message_list: list = []                     # 알림을 보낼 게시글 목록
            await self.getCafeDataDic()                      # 카페 데이터 가져오기
            await self.postCafe()                            # 카페 게시글 알림 전송
                
        except Exception as e:
            asyncio.create_task(log_error(f"error cafe {self.channel_id}.{e}"))

    # 카페 API에서 게시글 데이터 가져오기
    async def getCafeDataDic(self):
        # 네이버 카페 API URL 구성
        BASE_URL = f"https://apis.naver.com/cafe-web/cafe2/ArticleListV2dot1.json,{str(self.cafeData.loc[self.channel_id, 'cafeNum'])}"
        response = await get_message(self.performance_manager, "cafe", BASE_URL)  # API 요청

        # 현재 저장된 카페 데이터 가져오기
        cafe_json = self.cafeData.loc[self.channel_id, 'cafe_json']
        cafe_json_ref_articles = cafe_json["refArticleId"]                           # 이미 처리한 게시글 ID 목록
        max_ref_article = max(cafe_json_ref_articles) if cafe_json_ref_articles else 0  # 최근 게시글 ID
        update_time = int(self.cafeData.loc[self.channel_id, 'update_time'])         # 마지막 업데이트 시간
        cafe_name_dict = self.cafeData.loc[self.channel_id, "cafeNameDict"]          # 필터링할 작성자 닉네임 목록
     
        try:
            # 게시글 목록 처리
            self._process_article_list(response, cafe_name_dict, max_ref_article, update_time, cafe_json_ref_articles)
        except Exception as e:
            asyncio.create_task(log_error(f"게시글 처리 중 오류 발생: {e}"))

        return

    # 게시글 목록 처리 함수
    def _process_article_list(self, request, cafe_name_dict, max_ref_article, update_time, cafe_json_ref_articles):
        """
        Args:
            request: API 요청 결과
            cafe_name_dict: 필터링할 작성자 닉네임 딕셔너리
            max_ref_article: 가장 최근의 현재까지의 게시글 ID
            update_time: 마지막 업데이트 시간
            cafe_json_ref_articles: 게시글 ID 목록들
        """
        # API 응답에서 게시글 목록 추출
        article_list = request.get('message', {}).get('result', {}).get('articleList', [])
        
        # 역순으로 처리 (오래된 글부터 처리)
        for article in reversed(article_list):
            #특정 작성자의 게시글만 처리
            if article["writerNickname"] not in cafe_name_dict:
                continue
                
            # 새 게시글인지 확인 (ID가 더 크고, 작성 시간이 더 최신)
            if not (article["refArticleId"] > max_ref_article and article['writeDateTimestamp'] > update_time):
                continue
            
            # 게시글 제목 처리(특수문자 등 처리)
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

    # 참조 게시글 ID 목록을 업데이트하는 함수
    def _update_ref_article_ids(self, ref_article_ids, new_id):
        """
        Args:
            ref_article_ids: 참조 게시글 ID 목록
            new_id: 추가할 새 게시글 ID
        """
        # 목록이 이미 10개 이상인 경우 가장 오래된 것 제거
        if len(ref_article_ids) >= 10:
            ref_article_ids[:-1] = ref_article_ids[1:]
            ref_article_ids[-1] = new_id
        else:
            # 아니면 그냥 추가
            ref_article_ids.append(new_id)

    # 카페 게시글을 메시지 목록에 추가하는 함수
    def _add_cafe_post(self, article):
        """
        Args:
            article: 게시글 데이터
        """
        # 카페 ID 가져오기
        cafeID = self.cafeData.loc[self.channel_id, 'cafeID']
        
        # 카페 게시글 데이터 객체 생성
        cafe_post = CafePostData(
            cafe_link=f"https://cafe.naver.com/{cafeID}/{article['refArticleId']}",  # 게시글 링크
            menu_id=article["menuId"],                   # 카페 게시판 ID
            menu_name=article["menuName"],              # 카페 게시판 이름
            subject=article["subject"],                 # 게시글 제목
            image=article.get("representImage", ""),    # 대표 이미지 (없으면 빈 문자열)
            write_timestamp=article["writeDateTimestamp"],  # 작성 시간
            writer_nickname=article["writerNickname"]   # 작성자 닉네임
        )
        
        # 메시지 목록에 추가
        self.message_list.append(cafe_post)

    # 카페 게시글 알림을 전송하는 함수
    async def postCafe(self):
        try:
            # 메시지 목록이 비어있으면 종료
            if not self.message_list:
                return
            
            # 각 게시글에 대해 알림 전송
            for post_data in self.message_list:
                # 웹훅 JSON 데이터 생성
                json_data = await self.create_cafe_json(post_data)
                print(f"{datetime.now()} {post_data.writer_nickname} post cafe {post_data.subject}")

                # 알림을 보낼 웹훅 URL 목록 가져오기
                list_of_urls = get_list_of_urls(self.DO_TEST, self.userStateData, post_data.writer_nickname, self.channel_id, "cafe_user_json")

                # 푸시 알림 및 디스코드 웹훅 전송
                asyncio.create_task(send_push_notification(list_of_urls, json_data))
                asyncio.create_task(DiscordWebhookSender().send_messages(list_of_urls, json_data))

            # 카페 데이터 저장
            await saveCafeData(self.cafeData, self.channel_id)
            
        except Exception as e:
            # 오류 발생 시 로그 기록 및 메시지 목록 초기화
            asyncio.create_task(log_error(f"error postCafe {e}"))
            self.message_list.clear()

    # 카페 게시글용 웹훅 JSON 데이터 생성 함수
    async def create_cafe_json(self, post_data: CafePostData) -> dict:
        # 타임스탬프를 ISO 형식으로 변환하는 내부 함수
        def getTime(timestamp):
            tm = gmtime(timestamp/1000)
            return f"{tm.tm_year}-{tm.tm_mon:02d}-{tm.tm_mday:02d}T{tm.tm_hour:02d}:{tm.tm_min:02d}:{tm.tm_sec:02d}Z"
    
        # 카페 정보 가져오기
        cafe_info = self.cafeData.loc[self.channel_id]
        
        # 카페 게시판 URL 구성
        menu_url = (f"https://cafe.naver.com/{cafe_info['cafeID']}"
                f"?iframe_url=/ArticleList.nhn%3F"
                f"search.clubid={int(cafe_info['cafeNum'])}"
                f"%26search.menuid={post_data.menu_id}")

        # 디스코드 임베드 생성
        embed = {
            "author": {
                "name": post_data.menu_name,  # 카페 게시판 이름
                "url": menu_url,              # 카페 게시판 URL
            },
            "color": 248125,                  # 임베드 색상
            "title": post_data.subject,       # 게시글 제목
            "url": post_data.cafe_link,       # 게시글 링크
            "thumbnail": {
                "url": quote(post_data.image, safe='/%:@&=+$,!?*\'()')  # 이미지 URL (URL 인코딩)
            },
            "footer": {
                "text": "cafe",
                "inline": True,
                "icon_url": iconLinkData().cafe_icon  # 카페 아이콘
            },
            "timestamp": getTime(post_data.write_timestamp)  # ISO 형식 시간
        }

        # 최종 웹훅 JSON 데이터 반환
        return {
            "username": f"[카페 알림] {cafe_info['cafeName']} - {post_data.writer_nickname}",  # 웹훅 표시 이름
            "avatar_url": await self.get_cafe_thumbnail_url(post_data.writer_nickname),       # 프로필 이미지
            "embeds": [embed]                                                                # 임베드 배열
        }
        
    # 작성자의 프로필 이미지 URL을 가져오는 함수
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
                
            # 카페 데이터에서 작성자 정보 추출
            cafe_info = self.cafeData.loc[self.channel_id, "cafeNameDict"][writerNickname]
            platform, user_id, current_thumbnail = cafe_info[1], cafe_info[0], cafe_info[2]
            
            # 지원하지 않는 플랫폼이면 현재 썸네일 반환
            if platform not in platform_config:
                return current_thumbnail
                
            # 플랫폼 설정 가져오기
            config = platform_config[platform]
            
            # API 요청 및 데이터 가져오기
            data = await get_message(self.performance_manager, platform, config["get_link"](user_id))
            
            # 응답 데이터 처리 (플랫폼별 다른 경로)
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
            # 오류 발생 시 로그 기록
            error_msg = f"카페 썸네일 가져오기 실패 (작성자: {writerNickname}, 플랫폼: {platform if 'platform' in locals() else 'unknown'}): {str(e)}"
            asyncio.create_task(log_error(error_msg))
            
            # 오류 발생 시 기존 썸네일 반환
            return current_thumbnail if 'current_thumbnail' in locals() else None
  
# 사용 예:
# async def main():
#     init = ... # 초기화 객체
#     cafe_post_title = getCafePostTitle()
#     await cafe_post_title.fCafeTitle(init)

# asyncio.run(main())