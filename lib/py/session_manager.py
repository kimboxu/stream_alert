
import logging
from typing import Optional, Dict
from dataclasses import dataclass
from aiohttp import ClientSession, TCPConnector


logger = logging.getLogger(__name__)


# ==================== 설정 클래스 ====================
@dataclass
class ConnectorConfig:
    """TCPConnector 설정"""
    limit: int = 100                          # 전체 동시 연결 수
    limit_per_host: int = 10                  # 호스트당 동시 연결 수
    ttl_dns_cache: int = 300                  # DNS 캐시 시간 (초)
    enable_cleanup_closed: bool = True        # 닫힌 연결 자동 정리
    keepalive_timeout: float = 15.0           # Keep-Alive 타임아웃 (초)
    force_close: bool = False                 # True면 매번 새 연결, False면 재사용
    ssl_verify: bool = True                   # SSL 검증
    
    def to_dict(self) -> Dict:
        """딕셔너리로 변환"""
        return {
            "limit": self.limit,
            "limit_per_host": self.limit_per_host,
            "ttl_dns_cache": self.ttl_dns_cache,
            "enable_cleanup_closed": self.enable_cleanup_closed,
            "keepalive_timeout": self.keepalive_timeout,
            "force_close": self.force_close,
        }


# ==================== 세션 관리자 ====================
class SessionManager:

    _instance: Optional["SessionManager"] = None
    _session: Optional[ClientSession] = None
    _connector: Optional[TCPConnector] = None
    _config: ConnectorConfig = ConnectorConfig()
    _session_stats: Dict[str, int] = {
        "created": 0,
        "reused": 0,
        "reconnected": 0,
    }
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def configure(cls, config: ConnectorConfig):
        cls._config = config
        logger.info(f"SessionManager 설정 업데이트: {config.to_dict()}")
    
    async def get_session(self) -> ClientSession:
        # 세션이 없거나 닫혀있으면 새로 생성
        if self._session is None or self._session.closed:
            await self._create_session()
            self._session_stats["created"] += 1
            logger.info(
                f"세션 생성됨 (생성 횟수: {self._session_stats['created']})"
            )
        else:
            self._session_stats["reused"] += 1
        
        return self._session
    
    async def _create_session(self):

        # 기존 세션 정리
        if self._session and not self._session.closed:
            await self._session.close()
        
        # 기존 커넥터 정리
        if self._connector and not self._connector.closed:
            await self._connector.close()
        
        # 새로운 TCPConnector 생성 (연결 풀 포함)
        self._connector = TCPConnector(
            limit=self._config.limit,
            limit_per_host=self._config.limit_per_host,
            ttl_dns_cache=self._config.ttl_dns_cache,
            enable_cleanup_closed=self._config.enable_cleanup_closed,
            keepalive_timeout=self._config.keepalive_timeout,
            force_close=self._config.force_close,
            ssl=self._config.ssl_verify,
        )
        
        # 새로운 ClientSession 생성
        self._session = ClientSession(connector=self._connector)
        
        logger.debug(
            f"TCPConnector 설정: limit={self._config.limit}, "
            f"limit_per_host={self._config.limit_per_host}"
        )
