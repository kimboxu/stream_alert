
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
            cls._instance.performance_manager = None  # 성능 매니저 선언
        return cls._instance

    # 초기화 함수 - 필요한 데이터 로드
    async def initialize(self):
        
        # 초기화가 아직 되지 않은 경우에만 실행
        if self.init_var is None:
            self.init_var = initVar()  # 기본 설정 변수 초기화
            
            # PerformanceManager 초기화 및 스케줄러 시작
            await self._initialize_performance_manager()

            await DataBaseVars(self.init_var)  # db의 데이터 로드
            await userDataVar(self.init_var)  # 사용자 데이터 로드

            

        return self.init_var

    async def _initialize_performance_manager(self):
        """성능 매니저 초기화 및 설정"""
        try:
            # 동적 임포트로 순환 임포트 방지
            from make_log_api_performance import PerformanceManager
            
            # PerformanceManager 인스턴스 생성
            self.performance_manager = PerformanceManager()
            
            # 스케줄러 설정 및 시작
            self.performance_manager.setup_scheduler()
            
            print(f"성능 매니저 초기화 완료")
            
        except Exception as e:
            print(f"성능 매니저 초기화 실패: {e}")
            self.performance_manager = None

    # 초기화 변수 객체를 반환하는 함수
    def get_init(self):
        return self.init_var
    
    # 성능 매니저 객체를 반환하는 함수
    def get_performance_manager(self):
        """성능 매니저 인스턴스 반환"""
        return self.performance_manager
    
    # API 성능 로깅을 위한 편의 함수
    async def log_api_performance(self, api_type: str, response_time_ms: int, 
                                is_success: bool, **kwargs):
        """API 성능 로깅 - 성능 매니저가 없어도 에러가 발생하지 않도록 안전하게 처리"""
        if self.performance_manager:
            try:
                await self.performance_manager.log_api_performance(
                    api_type=api_type,
                    response_time_ms=response_time_ms,
                    is_success=is_success,
                    **kwargs
                )
            except Exception as e:
                print(f"API 성능 로깅 실패: {e}")
        # 성능 매니저가 없거나 실패해도 조용히 넘어감
    
    # 시스템 종료시 정리 작업
    async def shutdown(self):
        """애플리케이션 종료시 정리 작업"""
        if self.performance_manager:
            try:
                await self.performance_manager.shutdown()
                print("성능 매니저 정리 완료")
            except Exception as e:
                print(f"성능 매니저 정리 중 오류: {e}")
        
        print("StateManager 종료 완료")