# stream_alert

A new Flutter project.

## Getting Started

This project is a starting point for a Flutter application.

A few resources to get you started if this is your first Flutter project:

- [Lab: Write your first Flutter app](https://docs.flutter.dev/get-started/codelab)
- [Cookbook: Useful Flutter samples](https://docs.flutter.dev/cookbook)

For help getting started with Flutter development, view the
[online documentation](https://docs.flutter.dev/), which offers tutorials,
samples, guidance on mobile development, and a full API reference.

# 캐싱 시스템 통합 가이드

이 문서는 streamAlert 프로젝트에 캐싱 시스템을 통합하는 방법을 설명합니다. 이 캐싱 시스템은 API 요청과 데이터베이스 접근을 최적화하여 Supabase 무료 플랜의 Egress 사용량을 크게 줄일 수 있습니다.

## 설치 방법

1. 프로젝트 루트 디렉토리에 세 개의 새 파일을 추가합니다:
   - `base_cache.py` - 캐싱 시스템 핵심 기능
   - `cached_api.py` - 캐싱된 API 클라이언트
   - `base_with_cache.py` - 기존 base.py 대체 모듈

2. 기존 코드에서 base.py 임포트를 base_with_cache.py로 변경합니다:
   ```python
   # 변경 전
   from base import get_message, ...
   
   # 변경 후
   from base_with_cache import get_message, ...
   ```

3. 프로젝트 시작 시 캐시 관리 작업을 초기화합니다:
   ```python
   # discordbot.py 또는 메인 진입점에 추가
   from cached_api import start_cache_tasks
   
   async def main():
       # 캐시 관리 작업 시작
       cache_tasks = await start_cache_tasks()
       
       # 기존 코드...
   ```

## 주요 개선 사항

1. **API 요청 캐싱**:
   - 동일한 API 요청은 설정된 TTL(Time-To-Live) 동안 캐시됩니다.
   - 플랫폼별로 다른 TTL 값을 적용하여 최적의 캐싱 전략을 구현했습니다.

2. **데이터베이스 요청 최적화**:
   - 중복 DB 업데이트를 방지하기 위한 트랜잭션 캐싱이 적용되었습니다.
   - 자주 변경되지 않는 데이터는 더 오래 캐시됩니다.

3. **대기 시간 조정**:
   - API 요청 간 최소 대기 시간이 증가되어 과도한 요청을 방지합니다.
   - 폴링 간격이 최적화되어 불필요한 요청을 줄입니다.

4. **메모리 관리**:
   - 캐시 크기를 제한하여 메모리 사용량을 관리합니다.
   - 정기적으로 만료된 캐시 항목을 정리합니다.

## 캐싱 설정 조정

`base_cache.py`의 `CacheConfig` 클래스에서 TTL 값을 조정할 수 있습니다:

```python
class CacheConfig:
    DEFAULT_TTL = 10  # 기본 TTL (초)
    
    TTL_SETTINGS = {
        # 플랫폼별 API 요청에 대한 TTL
        "afreeca": 10,  # 필요에 따라 조정
        "chzzk": 10,    # 필요에 따라 조정
        # 기타 설정...
    }
```

## 성능 모니터링

캐싱 시스템의 성능을 모니터링하려면:

```python
from base_cache import get_cache_stats

# 캐시 통계 출력
stats = get_cache_stats()
print(f"캐시 히트율: {stats['hit_ratio']:.2%}")
print(f"캐시된 항목 수: {stats['items']}")
print(f"캐시 크기: {stats['size_bytes'] / 1024 / 1024:.2f} MB")
```

## 캐시 관리

필요한 경우 캐시를 수동으로 관리할 수 있습니다:

```python
from base_cache import clear_cache

# 전체 캐시 지우기
clear_cache()

# 특정 패턴과 일치하는 항목만 지우기
clear_cache("chzzk")  # "chzzk"를 포함하는 모든 캐시 항목 지우기
```

## 권장 사항

1. 처음에는 API 응답을 모니터링하여 캐싱이 데이터 정확성에 영향을 미치지 않는지 확인하세요.
2. 필요한 경우 TTL 값을 조정하여 최적의 균형을 찾으세요:
   - TTL이 너무 짧으면 캐싱 효과가 적습니다.
   - TTL이 너무 길면 데이터가 오래됩니다.
3. 실시간성이 중요한 기능(예: 채팅)과 그렇지 않은 기능(예: 프로필 이미지)을 구분하여 다른 TTL 값을 적용하세요.

## 추가 최적화

Supabase 사용량을 더 줄이려면 다음 사항을 고려하세요:

1. **배치 처리**: 
   - 여러 개별 업데이트 대신 배치 업데이트를 사용하세요.
   - 메시지 전송을 일괄 처리하여 요청 수를 줄이세요.

2. **데이터 압축**:
   - 큰 데이터는 전송 전에 압축하세요.
   - 필요한 필드만 선택적으로 가져오세요.

3. **폴링 간격 조정**:
   - 중요도가 낮은 기능의 폴링 간격을 늘리세요.
   - 활동이 적은 시간대에는 폴링 빈도를 줄이세요.


# Supabase 데이터베이스 최적화 방안

이 문서는 현재 Supabase 사용량과 관련된 문제점을 분석하고, 데이터베이스 사용을 최적화하기 위한 방안을 제시합니다.

## 현재 상황 분석

현재 시스템은 다음과 같은 특성으로 인해 Egress 사용량이 높습니다:

1. **실시간 상태 확인**: 스트리머의 온라인/오프라인 상태와 방송 제목을 지속적으로 확인합니다.
2. **채팅 데이터 저장**: 모든 채팅 메시지가 데이터베이스에 저장됩니다.
3. **중복 요청**: 동일한 데이터에 대해 반복적으로 요청이 발생합니다.
4. **과도한 폴링**: 짧은 간격으로 상태 변화를 확인합니다.

## 데이터베이스 스키마 최적화

### 1. 인덱스 최적화

```sql
-- 자주 조회하는 필드에 인덱스 추가
CREATE INDEX IF NOT EXISTS idx_user_state_data_discord_url ON userStateData (discordURL);
CREATE INDEX IF NOT EXISTS idx_chzzk_title_data_live_state ON chzzk_titleData (live_state);
CREATE INDEX IF NOT EXISTS idx_afreeca_title_data_live_state ON afreeca_titleData (live_state);
```

### 2. 불필요한 컬럼 제거

데이터베이스 테이블을 검토하여 실제로 사용되지 않는 컬럼을 식별하고 제거합니다.

### 3. 데이터 타입 최적화

```sql
-- 텍스트 필드의 최대 길이 제한
ALTER TABLE chzzk_titleData ALTER COLUMN title1 TYPE VARCHAR(255);
ALTER TABLE chzzk_titleData ALTER COLUMN title2 TYPE VARCHAR(255);

-- 날짜/시간 필드 최적화
ALTER TABLE chzzk_titleData ALTER COLUMN update_time TYPE TIMESTAMP;
```

## Supabase 쿼리 최적화

### 1. 필요한 필드만 조회

```javascript
// 변경 전
supabase.table("chzzkIDList").select("*").execute()

// 변경 후
supabase.table("chzzkIDList").select("channelID,channelName,profile_image").execute()
```

### 2. 데이터 배치 처리

```javascript
// 변경 전: 개별 업데이트
for (const id of channelIds) {
    supabase.table("userStateData").update({ notifications: [...] }).eq("discordURL", id).execute();
}

// 변경 후: 배치 업데이트
const updates = channelIds.map(id => ({
    id: id,
    notifications: [...] 
}));
supabase.table("userStateData").upsert(updates).execute();
```

### 3. 데이터 압축

큰 JSON 데이터를 저장하거나 전송할 때 압축을 고려하세요.

```javascript
// LZ 문자열 압축 구현 예시
import { compress, decompress } from 'lz-string';

// 압축 저장
const compressedData = compress(JSON.stringify(largeObject));
supabase.table("some_table").upsert({ data: compressedData }).execute();

// 압축 해제
const compressedResult = await supabase.table("some_table").select("data").single().execute();
const originalData = JSON.parse(decompress(compressedResult.data.data));
```

## 실시간 구독 대신 폴링 최적화

현재 시스템은 폴링 방식으로 데이터를 지속적으로 확인하고 있습니다. 이 접근 방식을 최적화하세요:

```javascript
// 폴링 간격 증가 및 차등화 적용
const POLLING_INTERVALS = {
    high_priority: 10, // 10초
    medium_priority: 30, // 30초
    low_priority: 60 // 60초
};

// 활동 수준에 따라 폴링 간격 조정
function getPollingInterval(channelId) {
    const activity = getChannelActivity(channelId);
    
    if (activity === 'high') return POLLING_INTERVALS.high_priority;
    if (activity === 'medium') return POLLING_INTERVALS.medium_priority;
    return POLLING_INTERVALS.low_priority;
}
```

## 데이터 청소 및 보관

오래된 데이터를 정기적으로 삭제하거나 보관하여 데이터베이스 크기를 관리하세요.

```sql
-- 30일 이상 된 알림 삭제
DELETE FROM userNotifications WHERE created_at < NOW() - INTERVAL '30 days';

-- 1년 이상 된 채팅 로그를 별도 테이블로 이동
INSERT INTO chat_logs_archive (SELECT * FROM chat_logs WHERE created_at < NOW() - INTERVAL '1 year');
DELETE FROM chat_logs WHERE created_at < NOW() - INTERVAL '1 year';
```

## Supabase Edge Functions 활용

Supabase Edge Functions를 사용하여 클라이언트-서버 간 데이터 전송량을 줄일 수 있습니다:

```javascript
// Edge Function 예시 (supabase/functions/update-status/index.ts)
import { serve } from 'https://deno.land/std@0.168.0/http/server.ts'
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

serve(async (req) => {
  const supabase = createClient(
    Deno.env.get('SUPABASE_URL') ?? '',
    Deno.env.get('SUPABASE_ANON_KEY') ?? ''
  )

  const { channelId, status } = await req.json()
  
  // 데이터베이스 업데이트 직접 수행
  const { data, error } = await supabase
    .from('channels')
    .update({ status })
    .eq('id', channelId)
  
  // 최소한의 데이터만 반환
  return new Response(
    JSON.stringify({ success: !error }),
    { headers: { 'Content-Type': 'application/json' } },
  )
})
```

## 중복 트랜잭션 방지

동일한 데이터에 대한 중복 업데이트를 방지하기 위해 조건부 업데이트를 사용하세요:

```javascript
// 변경 전
supabase.table("chzzk_titleData")
  .update({ live_state: "OPEN" })
  .eq("channelID", channelId)
  .execute();

// 변경 후: 상태가 실제로 변경된 경우에만 업데이트
supabase.table("chzzk_titleData")
  .update({ live_state: "OPEN" })
  .eq("channelID", channelId)
  .not("live_state", "eq", "OPEN")  // 이미 OPEN 상태가 아닌 경우에만 업데이트
  .execute();
```

## 유료 플랜 고려사항

현재 사용량이 무료 플랜 한도를 지속적으로 초과한다면, 유료 플랜 업그레이드를 고려하세요:

- **Pro 플랜**: 월 $25로 더 높은 Egress 한도(200GB)와 더 많은 데이터베이스 공간을 제공합니다.
- **Team 플랜**: 더 많은 사용량과 고급 기능이 필요한 경우 적합합니다.

## 모니터링 및 알림 설정

Supabase 사용량을 모니터링하고 문제를 조기에 발견할 수 있는 알림 시스템을 구축하세요:

```javascript
// 주기적으로 사용량 확인 및 알림
async function checkUsage() {
  const { data } = await supabase.rpc('get_project_usage');
  
  const egress = data.egress_bytes / (1024 * 1024 * 1024); // GB로 변환
  const egressLimit = 5; // 무료 플랜 한도 (GB)
  
  if (egress > egressLimit * 0.8) {
    // 사용량이 한도의 80%를 초과하면 알림
    sendAlert(`Supabase Egress 사용량이 한도의 ${(egress/egressLimit*100).toFixed(1)}%에 도달했습니다.`);
  }
}
```

## 결론

위의 최적화 방안을 적용하면 Supabase 사용량, 특히 Egress 사용량을 크게 줄일 수 있습니다. 가장 중요한 것은 불필요한 데이터 전송을 최소화하고, 효율적인 캐싱 전략을 구현하는 것입니다. 만약 모든 최적화 후에도 무료 플랜의 한계에 도달한다면, 서비스 규모에 맞는 유료 플랜으로의 전환을 고려하세요.