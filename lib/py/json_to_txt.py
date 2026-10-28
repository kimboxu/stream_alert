"""하이라이트 JSON 파일을 VOD 댓글용 TXT 파일로 변환하는 도구.

변환 결과는 unified_vod.py 의 _get_highlight_msg_from_file() 과 같은
줄 형식(재미도 1~5점)을 사용합니다.

    [ 00:03:00] - 재미도: 1 - 서로 죽여라 ㅋㅋㅋ 난리났네
    [ 00:08:30] - 재미도: 5 - 가르치는 입장 되니까 어때? ㅋㅋㅋ

안내 문구(🤖 ...)는 convert_txt_to_vod_comment() 가 전송 시점에
자동으로 맨 윗줄에 붙여주므로 TXT 파일에는 넣지 않습니다.

사용 예:
    python json_to_txt.py highlight_chat_빅헤드_20261011_000000.json
    python json_to_txt.py input.json -o output/reports/빅헤드/빅헤드_highlights_20261012.txt
"""

import argparse
import json
from pathlib import Path

# unified_vod.py 의 fun_difference1~5 와 동일한 기준값.
# score_difference 가 이 값을 초과할 때마다 재미도가 1점씩 올라갑니다. (최대 5점)
FUN_SCORE_THRESHOLDS = (20, 35, 45, 60, 75)

# unified_vod.py 의 time_offset 과 동일한 값(초).
# 하이라이트 장면보다 조금 앞에서 시청자가 볼 수 있도록 시간을 이만큼 앞당깁니다.
DEFAULT_TIME_OFFSET_SECONDS = 25

TIME_KEY = "comment_after_openDate"


def load_json(file_path):
    """JSON 파일을 읽어서 dict 로 반환합니다."""
    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


def get_fun_score(score_difference):
    """score_difference 를 재미도(0~5)로 변환합니다.

    기준값(FUN_SCORE_THRESHOLDS)을 초과한 개수가 곧 재미도입니다.
    """
    return sum(score_difference > threshold for threshold in FUN_SCORE_THRESHOLDS)


def parse_time_to_seconds(time_str):
    """'HH:MM:SS' / 'MM:SS' / 'SS' 문자열을 초로 변환합니다. 형식이 잘못되면 None."""
    try:
        parts = [int(part) for part in time_str.split(":")]
    except ValueError:
        return None

    seconds = 0
    for part in parts:
        seconds = seconds * 60 + part
    return seconds


def format_seconds(total_seconds):
    """초를 'HH:MM:SS' 문자열로 변환합니다."""
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def apply_time_offset(time_str, offset_seconds):
    """시간 문자열에서 offset_seconds 만큼 뺀 시간 문자열을 반환합니다.

    시간을 해석할 수 없거나 결과가 0초 미만이면 None 을 반환합니다.
    (unified_vod.py 도 변환 결과가 비어 있으면 해당 줄을 건너뜁니다.)
    """
    total_seconds = parse_time_to_seconds(time_str)
    if total_seconds is None:
        return None

    shifted_seconds = total_seconds - offset_seconds
    if shifted_seconds < 0:
        return None

    return format_seconds(shifted_seconds)


def build_comment_line(comment, offset_seconds):
    """타임라인 댓글 1건을 TXT 한 줄로 변환합니다.

    시간 또는 내용이 비어 있거나 시간 보정에 실패하면 None 을 반환합니다.
    """
    time_str = comment.get(TIME_KEY, "")
    text = comment.get("image_text", "") or comment.get("text", "")

    if not time_str or not text:
        return None

    formatted_time = apply_time_offset(time_str, offset_seconds)
    if not formatted_time:
        return None

    score_difference = float(comment.get("score_difference", 0))

    # unified_vod.py 와 동일하게, 점수가 0 이면 재미도를 표시하지 않습니다.
    if score_difference != 0:
        text = f"재미도: {get_fun_score(score_difference)} - {text}"

    return f"[ {formatted_time}] - {text}"


def convert_to_lines(data, offset_seconds=DEFAULT_TIME_OFFSET_SECONDS):
    """JSON 데이터 전체를 시간순으로 정렬된 TXT 줄 목록으로 변환합니다."""
    timeline_comments = data.get("timeline_comments", [])
    sorted_comments = sorted(timeline_comments, key=lambda item: item.get(TIME_KEY, ""))

    lines = (build_comment_line(comment, offset_seconds) for comment in sorted_comments)
    return [line for line in lines if line]


def get_default_output_path(json_path):
    """출력 경로를 만듭니다.

    test_chzzk_vod_chat_send.py 의 TXT 검색 조건(날짜 + 'highlights' 포함,
    'test' / 'ai' 미포함)을 만족하도록 파일명 끝에 '_highlights' 를 붙입니다.
    """
    return json_path.with_name(f"{json_path.stem}_highlights.txt")


def save_lines(lines, output_path):
    """줄 목록을 TXT 파일로 저장합니다."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines) + "\n")


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="하이라이트 JSON 파일을 VOD 댓글용 TXT 파일로 변환합니다."
    )
    parser.add_argument("json_file", help="변환할 하이라이트 JSON 파일 경로")
    parser.add_argument(
        "--time-offset",
        type=int,
        default=DEFAULT_TIME_OFFSET_SECONDS,
        help=f"하이라이트 시간에서 뺄 초 (기본값: {DEFAULT_TIME_OFFSET_SECONDS}, unified_vod.py 와 동일)",
    )
    parser.add_argument(
        "-o", "--output",
        help="저장할 TXT 파일 경로 (기본값: JSON 파일과 같은 폴더의 *_highlights.txt)",
    )
    return parser.parse_args()


def main():
    args = parse_arguments()

    json_path = Path(args.json_file)
    if not json_path.is_file():
        raise SystemExit(f"❌ JSON 파일을 찾을 수 없습니다: {json_path}")

    lines = convert_to_lines(load_json(json_path), args.time_offset)
    if not lines:
        raise SystemExit("❌ 변환할 타임라인 댓글이 없습니다.")

    output_path = Path(args.output) if args.output else get_default_output_path(json_path)
    save_lines(lines, output_path)

    print(f"✅ 변환 완료: {len(lines)}줄")
    print(f"📄 저장 위치: {output_path}")


if __name__ == "__main__":
    main()