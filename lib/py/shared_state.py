from base import initVar, userDataVar, DataBaseVars


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
            cls._instance.global_instances = {  # 전역 인스턴스 저장소 추가
                "cafe": {},
                "chzzk_video": {},
                "afreeca_video": {},
                "chzzk_live": {},
                "afreeca_live": {},
                "chzzk_hot_clips": {},
                "afreeca_hot_clips": {},
                "chzzk_chat": {},
                "afreeca_chat": {},
            }
            cls._instance.task_status = {}
            cls._instance.max_task_history = 10  # 최대 작업 이력 보관
        return cls._instance

    def add_task_status(self, task_id: str, initial_data: dict):
        """새 작업 상태 추가 (개수 제한 포함)"""
        # 최대 개수 초과 시 가장 오래된 완료 작업 제거
        if len(self.task_status) >= self.max_task_history:
            completed_tasks = [
                (tid, data)
                for tid, data in self.task_status.items()
                if data.get("status") in ["completed", "error"]
            ]

            if completed_tasks:
                # 가장 오래된 완료 작업 제거
                oldest_task = min(
                    completed_tasks, key=lambda x: x[1].get("started_at", "")
                )
                del self.task_status[oldest_task[0]]
                print(f"오래된 작업 제거: {oldest_task[0]}")

        self.task_status[task_id] = initial_data

    def get_task_status(self, task_id: str = None):
        """작업 상태 조회"""
        if task_id:
            return self.task_status.get(task_id)
        return self.task_status

    def update_task_status(self, task_id: str, update_data: dict):
        """작업 상태 업데이트"""
        if task_id in self.task_status:
            self.task_status[task_id].update(update_data)
        else:
            self.task_status[task_id] = update_data

    def remove_task_status(self, task_id: str):
        """특정 작업 상태 제거"""
        if task_id in self.task_status:
            del self.task_status[task_id]
            return True
        return False

    def cleanup_completed_tasks(self, hours_old: int = 6):
        """완료된 작업 정리"""
        from datetime import datetime, timedelta

        current_time = datetime.now()
        cutoff_time = current_time - timedelta(hours=hours_old)

        tasks_to_remove = []
        for task_id, task_data in self.task_status.items():
            try:
                if task_data.get("status") in ["completed", "error"]:
                    started_at = datetime.fromisoformat(task_data.get("started_at", ""))
                    if started_at < cutoff_time:
                        tasks_to_remove.append(task_id)
            except:
                tasks_to_remove.append(task_id)

        for task_id in tasks_to_remove:
            del self.task_status[task_id]

        return len(tasks_to_remove)

    # 초기화 함수 - 필요한 데이터 로드
    async def initialize(self):

        # 초기화가 아직 되지 않은 경우에만 실행
        if self.init_var is None:
            self.init_var = initVar()  # 기본 설정 변수 초기화

            # PerformanceManager 초기화 및 스케줄러 시작
            await self._initialize_performance_manager()

            await DataBaseVars(self.init_var, is_start=True)  # db의 데이터 로드
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
            print(f"성능 매니저 초기화 실패: {str(e)}")
            self.performance_manager = None

    # 초기화 변수 객체를 반환하는 함수
    def get_init(self):
        return self.init_var

    # 성능 매니저 객체를 반환하는 함수
    def get_performance_manager(self):
        """성능 매니저 인스턴스 반환"""
        return self.performance_manager

    # 전역 인스턴스 저장소 반환
    def get_global_instances(self):
        """전역 인스턴스 저장소 반환"""
        return self.global_instances

    # 특정 타입의 인스턴스 가져오기
    def get_instance_by_type(self, instance_type: str, channel_id: str = None):
        """
        특정 타입의 인스턴스를 가져오는 함수

        Args:
            instance_type: 인스턴스 타입 (예: 'chzzk_chat', 'afreeca_chat')
            channel_id: 채널 ID (선택사항)

        Returns:
            인스턴스 또는 인스턴스 딕셔너리
        """
        if instance_type not in self.global_instances:
            return None

        if channel_id:
            return self.global_instances[instance_type].get(channel_id)
        else:
            return self.global_instances[instance_type]

    # 인스턴스 저장
    def set_instance(self, instance_type: str, channel_id: str, instance):
        """
        인스턴스를 전역 저장소에 저장하는 함수

        Args:
            instance_type: 인스턴스 타입
            channel_id: 채널 ID
            instance: 저장할 인스턴스
        """
        if instance_type not in self.global_instances:
            self.global_instances[instance_type] = {}

        self.global_instances[instance_type][channel_id] = instance

    # 챗 인스턴스들만 가져오기 (편의 함수)
    def get_chat_instances(self, platform: str = None):
        """
        챗 인스턴스들을 가져오는 편의 함수

        Args:
            platform: 플랫폼명 ('chzzk', 'afreeca') 또는 None (전체)

        Returns:
            챗 인스턴스 딕셔너리
        """
        if platform:
            chat_key = f"{platform}_chat"
            return self.global_instances.get(chat_key, {})
        else:
            return {
                "chzzk": self.global_instances.get("chzzk_chat", {}),
                "afreeca": self.global_instances.get("afreeca_chat", {}),
            }

    # 하이라이트가 있는 챗 인스턴스들 찾기
    def get_chat_instances_with_highlights(self):
        """
        하이라이트 데이터가 있는 챗 인스턴스들을 찾는 함수

        Returns:
            하이라이트가 있는 인스턴스 정보 리스트
        """
        instances_with_highlights = []

        for platform in ["chzzk", "afreeca"]:
            chat_instances = self.get_chat_instances(platform)

            for channel_id, chat_instance in chat_instances.items():
                highlights_dict = self.init_var.titleData[platform].loc[channel_id, "highlights_dict_cache"]

                if not highlights_dict:
                    continue

                highlights_count = sum(len(v) for v in highlights_dict.values())

                if highlights_count <= 0:
                    continue

                # 채널명 가져오기
                try:
                    channel_name = self.init_var.IDList[platform].loc[
                        channel_id, "channelName"
                    ]

                except Exception:
                    channel_name = "Unknown"

                instances_with_highlights.append(
                    {
                        "channel_id": channel_id,
                        "channel_name": channel_name,
                        "platform": platform,
                        "highlights_count": highlights_count,
                        "instance": chat_instance,
                    }
                )

        return instances_with_highlights

    # API 성능 로깅을 위한 편의 함수
    async def log_api_performance(
        self, api_type: str, response_time_ms: int, is_success: bool, **kwargs
    ):
        """API 성능 로깅 - 성능 매니저가 없어도 에러가 발생하지 않도록 안전하게 처리"""
        if self.performance_manager:
            try:
                await self.performance_manager.log_api_performance(
                    api_type=api_type,
                    response_time_ms=response_time_ms,
                    is_success=is_success,
                    **kwargs,
                )
            except Exception as e:
                print(f"API 성능 로깅 실패: {str(e)}")
        # 성능 매니저가 없거나 실패해도 조용히 넘어감

    # 시스템 종료시 정리 작업
    async def shutdown(self):
        """애플리케이션 종료시 정리 작업"""
        if self.performance_manager:
            try:
                await self.performance_manager.shutdown()
                print("성능 매니저 정리 완료")
            except Exception as e:
                print(f"성능 매니저 정리 중 오류: {str(e)}")

        # 전역 인스턴스들 정리
        for instance_type in self.global_instances:
            self.global_instances[instance_type].clear()

        print("StateManager 종료 완료")
