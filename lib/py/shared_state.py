from base import (initVar, userDataVar, DataBaseVars)

# 애플리케이션 상태를 관리하는 클래스
class StateManager:
    _instance = None  # 싱글톤 인스턴스 저장 변수
    
    # 싱글톤 인스턴스를 가져오는 클래스 메서드
    @classmethod
    def get_instance(cls):
        # 인스턴스가 없으면 새로 생성
        if cls._instance is None:
            cls._instance = cls()
            cls._instance.init_var = None  # 초기화 변수 선언
        return cls._instance

    # 초기화 함수 - 필요한 데이터 로드
    async def initialize(self):
        # 초기화가 아직 되지 않은 경우에만 실행
        if self.init_var is None:
            self.init_var = initVar()  # 기본 설정 변수 초기화
            await DataBaseVars(self.init_var)  # db의 데이터 로드
            await userDataVar(self.init_var)  # 사용자 데이터 로드
        return self.init_var

    # 초기화 변수 객체를 반환하는 함수
    def get_init(self):
        return self.init_var