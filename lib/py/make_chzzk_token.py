# Access Token을 발급받기 위한 코드
import os
import requests
import secrets
import webbrowser
from urllib.parse import quote
from chzzk_token import client_secret, client_id, refresh_token, access_token, redirect_url
 
class ChzzkAuth:
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.naver_auth_url = "https://chzzk.naver.com/account-interlock"
        self.naver_token_url = "https://openapi.chzzk.naver.com/auth/v1/token"
        
    def get_auth_url(self, redirect_uri, state):
        """네이버 인증 코드를 받기 위한 URL을 생성합니다"""
        encoded_redirect = quote(redirect_uri)
        auth_url = (
            f"{self.naver_auth_url}"
            f"?response_type=code"
            f"&clientId={self.client_id}"
            f"&redirectUri={encoded_redirect}"
            f"&state={state}"
        )
        return auth_url
        
    def get_access_token(self, code, state, redirect_uri):
        """네이버 인증 코드로 Access Token을 발급받습니다"""
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.client_secret}'
        }
        
        data = {
            "grantType": "authorization_code",
            "clientId": self.client_id,
            "clientSecret": self.client_secret,
            "code": code,
            "state": state,
            "redirectUri": redirect_uri
        }
        
        try:
            response = requests.post(self.naver_token_url, headers=headers, json=data)
            
            if response.status_code == 200:
                return response.json()
            else:
                return f"Error: {response.status_code} - {response.text}"
                
        except Exception as e:
            return f"Error: {str(e)}"
 
def refresh_access_token():
    """Refresh Token을 사용하여 새로운 Access Token을 발급받습니다"""
    url = 'https://openapi.chzzk.naver.com/auth/v1/token'
    
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Content-Type': 'application/json'
    }
    
    data = {
        'grantType': 'refresh_token',
        'clientId': client_id,
        'clientSecret': client_secret,
        'refreshToken': refresh_token
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code == 200:
            token_info = response.json()
            print(f"""
Access Token 재발급:
Access Token: {token_info.get('content',{}).get('accessToken')}
Refresh Token: {token_info.get('content',{}).get('refreshToken')}
Access Token 만료시간: {token_info.get('content',{}).get('expiresIn')}초
Scope: {token_info.get('content').get('scope')}
""")  
            return token_info.get('content', {})
        else:
            print(f"Error: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"Error: {str(e)}")
        return None
 
def save_tokens(token_info):
    """발급받은 토큰을 파일에 저장합니다"""
    if token_info and token_info.get('accessToken') and token_info.get('refreshToken'):
        try:
            # 현재 스크립트의 디렉토리 경로 가져오기
            current_dir = os.path.dirname(os.path.abspath(__file__))
            token_file_path = os.path.join(current_dir, 'chzzk_token.py')
            
            # 파일 내용 준비
            file_content = f"""# 치지직 API 토큰 정보
redirect_url = 'https://discordBot.com'
client_id = '{client_id}'
client_secret = '{client_secret}'
access_token = '{token_info['accessToken']}'
refresh_token = '{token_info['refreshToken']}'
"""
            
            # 파일 쓰기
            with open(token_file_path, 'w', encoding='utf-8') as f:
                f.write(file_content)
            
            print(f"\n토큰이 다음 파일에 저장되었습니다: {token_file_path}")
            print("\n저장된 토큰 정보:")
            print(f"Access Token: {token_info['accessToken']}")
            print(f"Refresh Token: {token_info['refreshToken']}")
                    
        except Exception as e:
            print(f"\n토큰 저장 중 오류 발생: {str(e)}")
            print(f"시도한 파일 경로: {token_file_path}")
    else:
        print("\n저장할 토큰 정보가 올바르지 않습니다.")
        print(f"받은 토큰 정보: {token_info}")

def revoke_access_token():
    """Access Token을 삭제(revoke)합니다"""
    url = 'https://openapi.chzzk.naver.com/auth/v1/token/revoke'
    
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Content-Type': 'application/json'
    }
    
    data = {
        'clientId': client_id,
        'clientSecret': client_secret,
        'token': access_token,  # 'accessToken' 대신 'token' 사용
        'tokenTypeHint': 'access_token'  # 토큰 타입 명시. default 값은 access_token
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('code') == 200:
                print("Access Token이 성공적으로 삭제되었습니다.")
                return True
            else:
                print(f"삭제 실패: {result.get('message')}")
                return False
        else:
            print(f"Error: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"Error: {str(e)}")
        return False

 
if __name__ == "__main__":
    state = input("\n어떠한 작업을 하시나여? 1.발급, 2.재발급 및 저장, 3.삭제:\n")
    if '발급' in state and not '재발급' in state:
        # 클라이언트 정보 설정
        CLIENT_ID = client_id  # 치지직에서 발급받은 client id
        CLIENT_SECRET = client_secret  # 치지직에서 발급받은 client secret
        REDIRECT_URI = redirect_url
        STATE = secrets.token_urlsafe(16)  # 보안을 위한 랜덤 문자열 생성
        
        # 인증 객체 생성
        auth = ChzzkAuth(CLIENT_ID, CLIENT_SECRET)
        
        # 1. 인증 URL 생성 및 브라우저로 열기
        auth_url = auth.get_auth_url(REDIRECT_URI, STATE)
        print("인증 URL:", auth_url)
        print("\n브라우저에서 인증 페이지를 열고 로그인을 진행합니다.")
        webbrowser.open(auth_url)
        
        print("\n1. 네이버 로그인을 완료해주세요.")
        print("2. 권한 승인 후 리디렉션된 URL에서 'code' 파라미터 값을 복사해주세요.")
        print("3. 실제 받은 state 값이 다음과 일치하는지 확인해주세요:", STATE)
        
        # 2. 인증 코드로 Access Token 발급
        code = input("\n인증 코드를 입력해주세요: ")
        token_info = auth.get_access_token(code, STATE, REDIRECT_URI)
        print("\n토큰 정보:", token_info)

    if '재발급' in state:
        # Access Token 재발급 및 저장
        new_token_info = refresh_access_token()
        if new_token_info:
            save_tokens(new_token_info)

    if '삭제' in state:
        # Access Token 삭제
        revoke_access_token()