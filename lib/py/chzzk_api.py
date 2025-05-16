import requests

# 채널 ID로부터 채팅 채널 ID를 가져오는 함수
def fetch_chatChannelId(chzzkID: str) -> str:

    url = f'https://api.chzzk.naver.com/polling/v2/channels/{chzzkID}/live-status'
    try:
        # 사용자 에이전트 설정 (브라우저처럼 요청)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}
        # API 요청 및 JSON 응답 파싱
        response = requests.get(url, headers=headers).json()
        # 채팅 채널 ID 반환
        return response['content']['chatChannelId']
    except:
        # 요청 실패 시 오류 발생
        raise ValueError(f'잘못된 입력값 : {chzzkID}')


# 채널 ID로부터 채널 이름을 가져오는 함수
def fetch_channelName(chzzkID: str) -> str:
    url = f'https://api.chzzk.naver.com/service/v1/channels/{chzzkID}'
    try:
        # 사용자 에이전트 설정
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}
        # API 요청 및 JSON 응답 파싱
        response = requests.get(url, headers=headers).json()
        # 채널 이름 반환
        return response['content']['channelName']
    except:
        # 요청 실패 시 오류 발생
        raise ValueError(f'잘못된 입력값 : {chzzkID}')


# 채팅 액세스 토큰을 가져오는 함수
def fetch_accessToken(chatChannelId, cookies: dict) -> str:
    url = f'https://comm-api.game.naver.com/nng_main/v1/chats/access-token?channelId={chatChannelId}&chatType=STREAMING'
    try:
        # 사용자 에이전트 설정
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}
        # 쿠키와 함께 API 요청 및 JSON 응답 파싱
        response = requests.get(url, cookies=cookies, headers=headers).json()
        # 액세스 토큰과 추가 토큰 반환
        return response['content']['accessToken'], response['content']['extraToken']
    except:
        # 요청 실패 시 오류 발생
        raise ValueError(f'잘못된 입력값 : {chatChannelId}, {cookies}')


# 사용자 ID 해시를 가져오는 함수
def fetch_userIdHash(cookies: dict) -> str:
    try:
        # 사용자 에이전트 설정
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}
        # 쿠키와 함께 사용자 상태 API 요청 및 JSON 응답 파싱
        response = requests.get('https://comm-api.game.naver.com/nng_main/v1/user/getUserStatus', cookies=cookies,
                                headers=headers).json()
        # 사용자 ID 해시 반환
        return response['content']['userIdHash']
    except:
        # 요청 실패 시 오류 발생
        raise ValueError(f'잘못된 입력값 : {cookies}')