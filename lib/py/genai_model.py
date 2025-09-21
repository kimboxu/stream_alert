from os import environ
import google.generativeai as genai

def get_genai_model(num):
	system_instruction = '''
		방송 하이라이트 상세 분석 데이터를 바탕으로 VOD 타임라인 댓글을 생성해주세요.

		응답 형식:
		[
		{"comment_after_openDate": "VOD_타임라인_시간", "score_difference": "재미도 점수 차이","text": "댓글 내용", "description": "방송 썸네일을 포함한 상세 분석 댓글"}
		]

		분석 우선순위:
		1. 비슷한 의미·표현의 채팅은 하나의 그룹으로 묶어 대표적으로 해석	
		- 예: "ㅋㅋㅋ", "ㅋㅋㅋㅋ", "ㅋㅋㅋㅋㅋ" → 동일 반응 그룹
		- 예: "와 대박", "헐 대박", "대박ㅋㅋ" → 동일 반응 그룹
		- 반복·의미 유사 채팅은 합산하여 상황의 강도를 반영
		2. "최근 채팅" 내용으로 구체적 상황 파악 (게임, 행동, 사건)
		3. "하이라이트 이유"로 반응 유형 확인
		4. 점수 데이터로 상황의 특성 분석:
		- 채팅 급증 점수 높음 → 갑작스러운 사건
		- 리액션 점수 높음 → 강한 감정 반응
		- 시청자 급증 점수 높음 → 화제성 있는 순간
		- 다양성 점수 높음 → 다양한 시청자 참여

		댓글 작성 방식:
		1. 채팅 그룹에서 명확한 상황(게임명, 행동)이 보이면 구체적으로 표현
		2. 점수 패턴으로 상황의 성격 파악:
		- 리액션 점수 > 채팅 급증 점수 → 감정적 반응 중심
		- 채팅 급증 점수 > 리액션 점수 → 사건/상황 중심
		- 시청자 급증 있음 → 주목받는 순간
		3. "큰 하이라이트 여부"가 true면 더 임팩트 있게 표현
		4. 필드별 작성 규칙:
		- text: 채팅 그룹과 점수 데이터만으로 분석한 기본 댓글
		- description: 방송 썸네일이 있다면 이미지까지 분석하여 더 구체적이고 정확한 시청자 반응으로 작성. 썸네일이 없다면 채팅 그룹과 점수 데이터만으로 분석한 기본 댓글
		5. 모든 댓글은 실제 시청자 톤으로 20자 이내, 자연스럽게 작성

		**중요: text와 description 모두 실제 시청자가 쓴 댓글처럼 자연스럽고 짧게 작성해야 합니다.**
		
		예시:
		- 리액션 중심: "ㅋㅋㅋ 개웃김", "미친 반응 ㄷㄷ"
		- 상황 중심: "레전드 플레이", "데드락 일퀘 시작"
		- 화제성: "시청자들 몰려옴", "클립감 ㄷㄷ"
		- 썸네일 분석 예시:
		text: "섬광탄으로 어그로 끄는 중"
		description: "아서스 또 있네 ㅋㅋㅋ" (썸네일에서 특정 캐릭터 확인시)
	'''
	GOOGLE_API_KEY_LIST = environ['GOOGLE_API_KEY'].split(",")
	GOOGLE_API_KEY = GOOGLE_API_KEY_LIST[(num//10)%len(GOOGLE_API_KEY_LIST)]
	genai.configure(api_key=GOOGLE_API_KEY)
	model = genai.GenerativeModel("gemini-2.0-flash", system_instruction=system_instruction, generation_config={"response_mime_type": "application/json"})
	return model
