import os, re
import zhconv  

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(BASE_DIR, "in.txt")
OUTPUT_FILE = os.path.join(BASE_DIR, "out.txt")
BLACKLIST = ["购物", "备用", "测试", "福利", "广告", "下线", "加群", "提示", "教程", "联系", "推广", "免费"]

PATTERN_BRACKET = re.compile(r'\[.*?\]|（.*?）|\(.*?\)|\{.*?\}|【.*?】|《.*?》', re.IGNORECASE)
PATTERN_CCTV = re.compile(r'CCTV\s*[-—_～•·:·\s]*(\d{1,2})(\+)?', re.IGNORECASE)
PATTERN_CCTV_CHECK = re.compile(r'4K|8K|超高清', re.IGNORECASE)
PATTERN_CCTV_EXTRACT = re.compile(r'CCTV\d{1,2}\+?', re.IGNORECASE)
PATTERN_REMOVE1 = re.compile(r'[-_—～•·:·\s]|HD|高清|超高清|HDR|标清|Vip', re.IGNORECASE)
PATTERN_REMOVE2 = re.compile(r'直播|主線|台$', re.IGNORECASE)
PATTERN_BLACKLIST = re.compile('|'.join(BLACKLIST), re.IGNORECASE)

def simplify(text):
    return zhconv.convert(text, 'zh-cn').upper().strip()

def clean_name(n):
    n = PATTERN_BRACKET.sub('', n)
    n = PATTERN_CCTV.sub(r'CCTV\1\2', n)
    if not PATTERN_CCTV_CHECK.search(n):
        m = PATTERN_CCTV_EXTRACT.search(n)
        if m:
            n = m.group()
    n = PATTERN_REMOVE1.sub('', n)
    n = PATTERN_REMOVE2.sub('', n)
    return simplify(n)

def is_blacklist(name):
    return PATTERN_BLACKLIST.search(name) is not None

def dedup_main():
    if not os.path.exists(INPUT_FILE):
        print(f"❌ 未找到输入文件: {INPUT_FILE}")
        return
    seen_urls = set()  
    output_data = []
    line_count = 0     
    black_count = 0    

    for enc in ['utf-8-sig', 'utf-8', 'gbk']:
        try:
            with open(INPUT_FILE, 'r', encoding=enc, errors='ignore') as f:
                for line in f:
                    line_count += 1
                    line = line.strip()
                    if not line:
                        continue
                    if "#genre#" in line:
                        genre_name = simplify(line.split(',')[0])
                        output_data.append(f"{genre_name},#genre#")
                        continue
                    if "," not in line:
                        continue
                    raw_name, url = line.split(",", 1)
                    c_url = url.strip()
                    if is_blacklist(raw_name):
                        black_count += 1
                        continue
                    if c_url not in seen_urls:
                        seen_urls.add(c_url)
                        c_name = clean_name(raw_name)
                        output_data.append(f"{c_name},{c_url}")
            break
        except Exception:
            continue

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("\n".join(output_data))

    print(f"🚀 纯 URL 智能去重+黑名单过滤完成！")
    print(f"📊 原始行数: {line_count}")
    print(f"🚫 黑名单过滤行数: {black_count}")
    print(f"✅ 独立 URL 数(输出): {len(seen_urls)}")
    print(f"💾 结果已存至: {OUTPUT_FILE}")

if __name__ == "__main__":
    dedup_main()