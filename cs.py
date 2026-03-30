import os
import re
import zhconv
import time
import argparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(BASE_DIR, "in.txt")
OUTPUT_FILE = os.path.join(BASE_DIR, "out.txt")
BLACKLIST = ["购物", "备用", "测试", "福利", "广告", "下线", "加群", "提示", "教程", "联系", "推广", "免费"]
ENCODINGS = ["utf-8-sig", "utf-8", "gbk", "gb2312", "gb18030"]
FILE_BUFFER_SIZE = 65536
BATCH_SIZE = 10000
URL_IGNORE_TRAILING_SLASH = True
URL_TO_LOWER = True

# 正则预编译 - 核心修复：调整冗余标识正则，保留4K/8K/超高清；还原CCTV正则确保数字保留
PATTERN_BRACKET = re.compile(r'[\[（({【《<「『〖〝\(].*?[\]）)}】》>」』〗〞\)]', re.I)
PATTERN_ALL_SYMBOLS = re.compile(
    r'[·•·@#$%^&*_+-=|\\/:;"\'<>,.?~！@#￥%……&*（）——+|、；：”“‘’《》，。？￥￡€¢§№★☆●○◎◇◆□■△▲▽▼⊿※々∞Ψ∪∩∈∏∑⊥∥∠∟⊕⊗⊙⌒√∝∞∫∬∭℅‰〃¤￠]+',
    re.I
)
# 【完全还原最初】CCTV标识标准化正则 - 确保数字+加号完整保留
PATTERN_CCTV = re.compile(r'CCTV\s*[-—_～•·:·\s]*(\d{1,2})(\+)?', re.IGNORECASE)
# 【完全还原最初】CCTV核心提取正则 - 保留CCTV+数字+加号
PATTERN_CCTV_EXTRACT = re.compile(r'CCTV\d{1,2}\+?', re.IGNORECASE)
# 【保留不清洗】4K/8K/超高清检测正则 - 仅做判断，不参与清洗
PATTERN_CCTV_CHECK = re.compile(r'4K|8K|超高清', re.IGNORECASE)
# 核心修复：移除冗余标识中的4K/8K/超高清，不再清洗该类标识
PATTERN_REDUNDANT_TAG = re.compile(r'HD|HDR|高清|超清|标清|Vip|会员|直播|主線|线|台$|频道$|1080P|2K|蓝光|杜比|臻彩|源\d+|备用|采集|解析', re.I)
PATTERN_BLACK = re.compile('|'.join(BLACKLIST), re.I)
PATTERN_URL_VALID = re.compile(r'://')
PATTERN_MULTI_SPACE = re.compile(r'\s+', re.I)
# 新增优化：不可见字符清洗
PATTERN_INVISIBLE = re.compile(r'[\u200b\u200c\u200d\t\n\r\f\v\u3000]', re.I)
# 修复：修正Emoji正则的字符范围（解决bad character range错误）
PATTERN_EMOJI = re.compile(
    r'[\U00010000-\U0010ffff\u2600-\u27ff\u2300-\u23ff\u2500-\u25ff\u2b00-\u2bff\u2d00-\u2dff\u2700-\u27bf\u00a9\u00ae\u203c\u2049\u2122\u2139\u2194-\u2199\u21a9-\u21aa\u23e9\u23ea\u23eb\u25aa\u25ab\u25b6\u25c0\u25fb-\u25fe\u2600-\u26ff\u2702-\u27b0\u2705\u2708-\u2764\u2795-\u2797\u27a1\u27b0\u27bf\u2934-\u2935\u2b05-\u2b07\u2b1b-\u2b1c\u2b50\u2b55\u3030\u303d\u3297\u3299\U0000f600-\U0000f6ff\U0001f1e0-\U0001f1ff\U0001f300-\U0001f5ff\U0001f600-\U0001f64f\U0001f680-\U0001f6ff\U0001f900-\U0001f9ff\U0001fa70-\U0001faff]',
    re.I
)

# 性能优化：全局方法→局部变量
_strip = str.strip
_upper = str.upper
_lower = str.lower
_convert = zhconv.convert
_bracket_sub = PATTERN_BRACKET.sub
_all_symbols_sub = PATTERN_ALL_SYMBOLS.sub
_cctv_sub = PATTERN_CCTV.sub
_cctv_check_search = PATTERN_CCTV_CHECK.search
_cctv_extract_search = PATTERN_CCTV_EXTRACT.search
_redundant_tag_sub = PATTERN_REDUNDANT_TAG.sub
_black_search = PATTERN_BLACK.search
_url_valid_search = PATTERN_URL_VALID.search
_multi_space_sub = PATTERN_MULTI_SPACE.sub
_invisible_sub = PATTERN_INVISIBLE.sub
_emoji_sub = PATTERN_EMOJI.sub

# 新增优化：全角转半角函数
def full2half(s: str) -> str:
    if not s or not isinstance(s, str):
        return ""
    res = []
    for c in s:
        ord_c = ord(c)
        if ord_c == 12288:  # 全角空格转半角
            res.append(chr(32))
        elif 65281 <= ord_c <= 65374:  # 全角数字/字母/符号转半角
            res.append(chr(ord_c - 65248))
        else:
            res.append(c)
    return ''.join(res)

# 频道名清洗：核心修复+保留4K/8K/超高清，确保CCTV数字完整保留
def clean_channel_name(name: str) -> str:
    if not name or not isinstance(name, str):
        return ""
    # 新增优化前置：不影响核心标识
    name = _invisible_sub('', name)
    name = _emoji_sub('', name)
    name = full2half(name)
    
    # 【核心修复】调整执行顺序，先提取4K/8K/超高清标识再做后续清洗，避免被误删
    cctv_4k_tag = ""
    # 修复：变量名从 4k_match 改为 match_4k（合法命名）
    match_4k = _cctv_check_search(name)
    if match_4k:
        cctv_4k_tag = match_4k.group()  # 提取4K/8K/超高清标识暂存
    
    # 最初的CCTV清洗逻辑 - 确保数字完整保留
    name = _bracket_sub('', name)
    name = _cctv_sub(r'CCTV\1\2', name)  # 还原CCTV+数字+加号
    # 有4K/8K标识时，不提取纯CCTV，保留完整名称+4K标识
    if not match_4k:
        cctv_match = _cctv_extract_search(name)
        if cctv_match:
            name = cctv_match.group()
    
    # 常规清洗：移除特殊符号和冗余标识（已排除4K/8K/超高清）
    name = _all_symbols_sub('', name)
    name = _redundant_tag_sub('', name)
    name = _convert(_strip(name), 'zh-cn').upper().strip()
    name = _multi_space_sub(' ', name)
    name = _strip(name)
    
    # 【关键步骤】将暂存的4K/8K/超高清标识拼接回CCTV名称后，形成CCTV+数字+4K格式
    if cctv_4k_tag and name.startswith('CCTV'):
        name = name + cctv_4k_tag
    
    return name

# URL归一化：原有优化保留，无修改
def normalize_url(url: str) -> str:
    if not url or not isinstance(url, str):
        return ""
    url = _strip(url)
    url = full2half(url)
    if '?' in url:
        url = url.split('?', 1)[0]
    if '&' in url:
        url = url.split('&', 1)[0]
    if URL_IGNORE_TRAILING_SLASH and url.endswith('/'):
        url = url[:-1]
    if URL_TO_LOWER:
        url = _lower(url)
    return url

# 以下函数完全无修改：文件读取、写入、核心处理、主入口
def read_lines(input_file: str) -> tuple[iter, str] | tuple[None, None]:
    if not os.path.exists(input_file):
        print(f"Error: Input file not found - {input_file}")
        return None, None
    for enc in ENCODINGS:
        try:
            with open(input_file, 'r', encoding=enc, errors='ignore', buffering=FILE_BUFFER_SIZE) as f:
                f.read(1024)
            def line_generator():
                with open(input_file, 'r', encoding=enc, errors='ignore', buffering=FILE_BUFFER_SIZE) as f:
                    for line in f:
                        s = _strip(line)
                        if s:
                            yield s
            return line_generator(), enc
        except Exception:
            continue
    print(f"Error: All encodings tried failed, cannot read file - {input_file}")
    return None, None

def write_lines(output_file: str, data: list):
    temp_file = f"{output_file}.tmp"
    try:
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(temp_file, 'w', encoding='utf-8', newline='', buffering=FILE_BUFFER_SIZE) as f:
            for i in range(0, len(data), BATCH_SIZE):
                batch = data[i:i+BATCH_SIZE]
                f.write('\n'.join(batch))
                if i + BATCH_SIZE < len(data):
                    f.write('\n')
        if os.path.exists(output_file):
            os.remove(output_file)
        os.rename(temp_file, output_file)
    except Exception as e:
        if os.path.exists(temp_file):
            os.remove(temp_file)
        raise e

def process_iptv(input_file: str) -> tuple[list, dict]:
    lines, enc = read_lines(input_file)
    if not lines:
        return [], {}
    stat = {
        "total_lines": 0,
        "genre_lines": 0,
        "black_lines": 0,
        "invalid_lines": 0,
        "dup_url_lines": 0,
        "valid_lines": 0
    }
    seen_urls = set()
    output_data = []
    for line in lines:
        stat["total_lines"] += 1
        if "#genre#" in line:
            output_data.append(line)
            stat["genre_lines"] += 1
            continue
        if "," not in line:
            stat["invalid_lines"] += 1
            continue
        try:
            name, url = line.split(",", 1)
        except:
            stat["invalid_lines"] += 1
            continue
        name_stripped = _strip(name)
        url_raw = _strip(url)
        if not name_stripped or not url_raw or not _url_valid_search(url_raw):
            stat["invalid_lines"] += 1
            continue
        if _black_search(name_stripped):
            stat["black_lines"] += 1
            continue
        url_norm = normalize_url(url_raw)
        if url_norm not in seen_urls:
            seen_urls.add(url_norm)
            clean_name = clean_channel_name(name_stripped)
            final_name = clean_name if clean_name else name_stripped
            output_data.append(f"{final_name},{url_raw}")
            stat["valid_lines"] += 1
        else:
            stat["dup_url_lines"] += 1
    return output_data, stat

def main():
    parser = argparse.ArgumentParser(description="IPTV Channel Clean & Deduplicate Tool")
    parser.add_argument("-i", "--input", type=str, default=INPUT_FILE, help=f"Input file path, default: {INPUT_FILE}")
    args = parser.parse_args()
    input_file = args.input
    start_time = time.time()
    print("Start IPTV channel clean & deduplicate process...")
    try:
        output_data, process_stat = process_iptv(input_file)
        if not process_stat:
            print("Error: Core process failed, no statistics data")
            return
        write_lines(OUTPUT_FILE, output_data)
        cost_time = time.time() - start_time
        print("Process completed!")
        print(f"Total lines: {process_stat['total_lines']:,} | Genre lines: {process_stat['genre_lines']:,}")
        print(f"Filtered lines: {process_stat['black_lines']+process_stat['invalid_lines']:,} (Blacklist: {process_stat['black_lines']:,} | Invalid: {process_stat['invalid_lines']:,})")
        print(f"Deduplicated lines: {process_stat['dup_url_lines']:,} | Invalid: {process_stat['invalid_lines']:,})")
        print(f"Deduplicated lines: {process_stat['dup_url_lines']:,} | Valid lines: {process_stat['valid_lines']:,}")
        print(f"Output file: {OUTPUT_FILE} | Total time: {cost_time:.2f}s")
    except KeyboardInterrupt:
        print("Process terminated by user")
    except Exception as e:
        print(f"Process failed: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()