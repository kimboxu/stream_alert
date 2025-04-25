# from requests import get
import json
from datetime import datetime, timedelta
# header = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}

# def getArticleList(CAFE_UNIQUE_ID, page_count=1):
#     ARTICLE_LIST_MAIN_PATH = "https://apis.naver.com/cafe-web/cafe2/ArticleListV2dot1.json"
    
#     all_articles = []
    
#     requestParameter = {
#         'search.queryType': 'lastArticle',
#         'ad': False,
#         "search.clubid": CAFE_UNIQUE_ID,
#         "search.page": 1
#     }
    
#     request = get(ARTICLE_LIST_MAIN_PATH, params=requestParameter, headers=header)
    
#     if request.status_code == 200:
#         data = json.loads(request.text)
#         articles = data.get('message', {}).get('result', {}).get('articleList', [])
#         all_articles.extend(articles)
#     else:
#         print(f"페이지 {1} 요청 실패: 상태 코드 {request.status_code}")

#     return all_articles

# # 사용 예시
# CAFE_UNIQUE_ID = 30697107
# articles = getArticleList(CAFE_UNIQUE_ID, page_count=5)  # 5페이지까지 크롤링

# for article in articles:
#     print(f"제목: {article.get('subject')}")
#     print(f"작성자: {article.get('writerNickName')}")
#     print(f"작성일: {article.get('writeDate')}")
#     print(f"조회수: {article.get('readCount')}")
#     print("-" * 50)
# from datetime import datetime

# current_time = datetime.now()
# print(current_time)
# a={'svcid': 'game', 'cid': 'N1KMLK', 'mbrCnt': 1074, 'uid': 'anonymous', 'profile': None, 'msg': '도와주는거 맞죠? 스트레스해소가 아니라?', 
#    'msgTypeCode': 10, 'msgStatusType': 'NORMAL', 
#    'extras': '{"emojis":{},"isAnonymous":true,"payType":"CURRENCY","payAmount":1000,"streamingChannelId":"219d8e65810a77d6e42c7df018d9632b","osType":"PC","donationType":"CHAT","weeklyRankList":[{"userIdHash":"0f4f5d1bfdc96abae7094df35f38991e","nickName":"sily jin","verifiedMark":false,"donationAmount":100000,"ranking":1},{"userIdHash":"15fa000f21cf0a822d679f94dfc0571f","nickName":"이탈리","verifiedMark":false,"donationAmount":67000,"ranking":2},{"userIdHash":"a19fe9fad9a61c4aa03c160363b34876","nickName":"찌니찌르","verifiedMark":false,"donationAmount":51000,"ranking":3},{"userIdHash":"5eba4286f97225cf936dd7c4fc2d7283","nickName":"모찌모링","verifiedMark":false,"donationAmount":21000,"ranking":4},{"userIdHash":"232c824adbd0fcd8b7c237c9c52850e9","nickName":"멍멍임","verifiedMark":false,"donationAmount":11000,"ranking":5},{"userIdHash":"2cbe6c07ad5c0fcc0dc5d19c6e70b2ec","nickName":"히지예요","verifiedMark":false,"donationAmount":10000,"ranking":6},{"userIdHash":"93bc9b1b60eae4533f02d0873d4c178f","nickName":"뫄카인","verifiedMark":false,"donationAmount":10000,"ranking":7},{"userIdHash":"7342ff924c1a24f173ae243a7970a897","nickName":"숲코프","verifiedMark":false,"donationAmount":10000,"ranking":8},{"userIdHash":"cf0d89bb997d2bfe90849e3c61bccc30","nickName":"11시11분11초","verifiedMark":false,"donationAmount":10000,"ranking":9},{"userIdHash":"0d275b971a27c34efb4e138a6ff51994","nickName":"빼빠민트","verifiedMark":false,"donationAmount":5000,"ranking":10}],"chatType":"STREAMING"}', 'ctime': 1722329002380, 'utime': 1722329002380, 'msgTid': None, 'msgTime': 1722329002380}
# b=json.loads(a['extras'])['payAmount']
# pass
# msg = ['\x1b\t012100024700', '{"type":"CHALLENGE_GIFT","chno":3503,"is_relay":false,"key":381166,"title":"100\ub808\ubca8","gift_count":1000,"user_id":"slmarta","user_nick":"sanyayeu2","bj_id":"alsdudtjdud1","bj_nick":"\uae40\ucc60\uba5c","image":"challenge_mission_gift_03"}', '']
# a=json.loads(msg[1])
# a['gift_count']
# pass


from urllib.parse import unquote
chat_data = {'svcid': 'game', 'cid': 'N1lGJ2', 'mbrCnt': 2873, 'uid': 'anonymous', 'profile': None, 'msg': '바니걸 라이브', 'msgTypeCode': 10, 'msgStatusType': 'NORMAL', 'extras': '{"isAnonymous":true,"payType":"CURRENCY","payAmount":1500,"donationId":"7GgkAxNl6XDcVPfHB7JVp5UiV3k4X","donationType":"VIDEO","weeklyRankList":[{"userIdHash":"d59cb9944a2811ce2fd1c5451ec4840d","nickName":"어디까지올라가는거엥","verifiedMark":false,"activatedAchievementBadgeIds":[],"donationAmount":100000,"ranking":1},{"userIdHash":"799c6d3a5f4d627cfbfeaca9b5ad561d","nickName":"염룡2","verifiedMark":false,"activatedAchievementBadgeIds":[],"donationAmount":100000,"ranking":2},{"userIdHash":"2610c2393928d2380d15df5b83585952","nickName":"참이슬참좋아","verifiedMark":false,"activatedAchievementBadgeIds":[],"donationAmount":30100,"ranking":3},{"userIdHash":"b69a88bcad56ef48801b5e70508df0c4","nickName":"료햄","verifiedMark":false,"activatedAchievementBadgeIds":[],"donationAmount":30000,"ranking":4},{"userIdHash":"0581b551fcc7637752092c3d93d0351e","nickName":"설원슾햄","verifiedMark":false,"activatedAchievementBadgeIds":[],"donationAmount":30000,"ranking":5},{"userIdHash":"b9c5b763b2745062103ab993c7f1937f","nickName":"아르세야","verifiedMark":false,"activatedAchievementBadgeIds":[],"donationAmount":19000,"ranking":6},{"userIdHash":"0a9482b841ad3d58ee1eba1ee4f69378","nickName":"프 노","verifiedMark":false,"activatedAchievementBadgeIds":[],"donationAmount":9000,"ranking":7},{"userIdHash":"7f8322ba439f7abd81b96286b1fa0055","nickName":"용사비군","verifiedMark":false,"activatedAchievementBadgeIds":[],"donationAmount":8000,"ranking":8},{"userIdHash":"5da8c7376eb90c57cc4501d245fc3080","nickName":"뚜띠투구굽한동수칸","verifiedMark":false,"activatedAchievementBadgeIds":[],"donationAmount":7950,"ranking":9},{"userIdHash":"8a4226ea80d57019f69c8ad31c8078e2","nickName":"마싯는뻐네너","verifiedMark":false,"activatedAchievementBadgeIds":[],"donationAmount":6000,"ranking":10}]}', 'ctime': 1744775870701, 'utime': 1744775870701, 'msgTid': None, 'msgTime': 1744775870697}
profile_data = chat_data.get('profile', {})
extras = json.loads(chat_data['extras'])
p = json.loads(unquote(profile_data))

from discord_webhook_sender import DiscordWebhookSender
import base
from os import environ
from supabase import create_client
import asyncio
async def main():
    supabase = create_client(environ['supabase_url'], environ['supabase_key'])
    init = base.initVar()
    await base.discordBotDataVars(init)
    await base.userDataVar(init, supabase)
    await asyncio.sleep(1)
    thumbnail_url = environ['default_thumbnail']


if __name__ == "__main__":
    asyncio.run(main())
print(((datetime.now()+ timedelta(seconds=300)))<= datetime.now())


test_url = "https://discord.com/api/webhooks/1365183976964231168/F4EOYSoxp0Al6F4sOouVv6mVVhsuo-Za_kZ5aoHKmC8CmzJxVTW1B90_kouAQpG7mT3z"
from discord_webhook_sender import DiscordWebhookSender
async def main ():
    await asyncio.create_task(DiscordWebhookSender().send_messages([test_url], {}))
    # await DiscordWebhookSender()._log_error("test")
    # asyncio.create_task(DiscordWebhookSender()._log_error("test"))

if __name__ == '__main__':
    asyncio.run(main())

import base64
import json

# base64 인코딩된 문자열
encoded_str = "eyJ1dWlkIjoiYmRiMmYwOTgtZmM5Zi00MjQyLWE3NTAtMzY5NTdkNjMyNzcxIiwicGFnZV90aW1lIjoxNzM5MjUyMjE1LCJwYWdlX3VybCI6Imh0dHA6Ly93dzcuZGlzY29yZGJvdC5jb20vYXV0aC92MS90b2tlbiIsInBhZ2VfbWV0aG9kIjoiUE9TVCIsInBhZ2VfcmVxdWVzdCI6e30sInBhZ2VfaGVhZGVycyI6eyJyZWZlcmVyIjpbImh0dHA6Ly93dzcuZGlzY29yZGJvdC5jb20vYXV0aC92MS90b2tlbj91c2lkPTI3XHUwMDI2dXRpZD0xMDk3NzA2OTEwMCJdfSwiaG9zdCI6Ind3Ny5kaXNjb3JkYm90LmNvbSIsImlwIjoiMTE0LjI5LjE0LjEwNCJ9Cg=="

# print(json.dumps(json.loads(base64.b64decode(encoded_str).decode('utf-8')), indent=4))


# from json import loads    
from requests import get, post
from base import getChzzkCookie
def getChzzkHeaders(): 
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    }

def get_auth_params():
    return {
        'clientId': '1788f977-a0c2-4a5c-ae47-4b3e00dde97e',
        'redirectUri': 'https://discordBot.com',  
        'state': 'zxclDasdfA25'
    }

auth_response = get(
    'https://chzzk.naver.com/account-interlock',
    headers=getChzzkHeaders(),
    params=get_auth_params(),
    cookies=getChzzkCookie(),
    timeout=10,
)

print("Auth Response URL:", auth_response.url)
print("Auth Status Code:", auth_response.status_code)
print("Auth Response Content:", auth_response.content)


def getChzzkHeaders(): 
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    }


url = "https://discordBot.com/auth/v1/token"
payload = {
    "grantType": "authorization_code",
    "clientId": "1788f977-a0c2-4a5c-ae47-4b3e00dde97e",
    "clientSecret": "moVfjEmiC3EI0eEYG9Sf7KYBrdttZmx5eH42jGx48rg",
    "code": "q7mNdYvjFPwNqGEkSzEtexpGmqE",
    "state": "zxclDasdfA25"
}
response = post(url, headers=getChzzkHeaders(), cookies=getChzzkCookie() ,data=payload)

try:
    response_data = response.text
    print("Response JSON:", response_data)
except ValueError:
    print("Invalid JSON response")

# 응답 데이터에서 필요한 정보 추출 (예시)
access_token = response_data.get('accessToken')
print("Access Token:", access_token)

# 여기서 받은 authorization code를 사용하여 2단계로 진행
# code = auth_response에서 받은 authorization code

# 2단계: Access Token 받기 (authorization code를 받은 후에 실행)
def get_api_headers():
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Client-Id': '1788f977-a0c2-4a5c-ae47-4b3e00dde97e',
        'Client-Secret': 'moVfjEmiC3EI0eEYG9Sf7KYBrdttZmx5eH42jGx48rg',
        'Content-Type': 'application/json'
    }

# Authorization code를 받은 후에 실행할 코드
api_response = get(
    'https://openapi.chzzk.naver.com',  # token 엔드포인트 사용
    headers=get_api_headers(),
    timeout=10
)

print("API Response:", api_response.text)
"f819bd37-4bfc-4034-9974-074c078fbe8b"
pass