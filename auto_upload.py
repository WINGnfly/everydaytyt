import sys
import os
import time
import random
import re
import posixpath
from urllib.parse import urlparse

import requests
import boto3
from botocore.exceptions import ClientError
from bs4 import BeautifulSoup
from DrissionPage import ChromiumPage, ChromiumOptions

# === CẤU HÌNH MAP THƯ MỤC -> COOKIE + CI_SIZE ===
DIR_CONFIGS = {
    "noveldata": {
        "cookie": os.getenv("CI_SESSION"),
        "cookie_cf_clearance": os.getenv("CF_CLEARANCE"),
        "size": 5,
    },
    "noveldata_HY": {
        "cookie": os.getenv("HY_CI_SESSION"),
        "cookie_cf_clearance": os.getenv("HY_CF_CLEARANCE"),
        "size": 5,
    },
    "noveldata_7": {
        "cookie": os.getenv("CI_SESSION_7"),
        "cookie_cf_clearance": os.getenv("CF_CLEARANCE_7"),
        "size": random.choice([0, 1])
    },
    "noveldata_ling": {
        "cookie": os.getenv("CI_SESSION_LING"),
        "cookie_cf_clearance": os.getenv("CF_CLEARANCE_LING"),
        "size": random.choice([0, 2])
    }
}

BASE_URL = os.getenv("BASE_URL")
R2_ENDPOINT = os.getenv("R2_ENDPOINT")
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY")
R2_SECRET_KEY = os.getenv("R2_SECRET_KEY")
R2_BUCKET = os.getenv("R2_BUCKET")
R2_REGION = os.getenv("R2_REGION", "auto")

def get_r2_client():
    if not R2_ENDPOINT or not R2_ACCESS_KEY or not R2_SECRET_KEY or not R2_BUCKET:
        raise RuntimeError("Thiếu cấu hình R2. Cần R2_ENDPOINT, R2_ACCESS_KEY, R2_SECRET_KEY, R2_BUCKET.")
    return boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        region_name=R2_REGION,
    )


def list_truyen_keys(client, bucket: str, prefix: str):
    keys = []
    continuation = None
    while True:
        params = {"Bucket": bucket, "Prefix": f"{prefix}/"}
        if continuation:
            params["ContinuationToken"] = continuation
        resp = client.list_objects_v2(**params)
        for obj in resp.get("Contents", []):
            key = obj.get("Key", "")
            filename = key.rsplit("/", 1)[-1]
            if filename.startswith("truyen_") and filename.endswith(".txt"):
                keys.append(key)
        if resp.get("IsTruncated"):
            continuation = resp.get("NextContinuationToken")
        else:
            break
    return keys


def get_object_text(client, bucket: str, key: str) -> str:
    try:
        resp = client.get_object(Bucket=bucket, Key=key)
        return resp["Body"].read().decode("utf-8")
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
            return ""
        raise


def put_object_text(client, bucket: str, key: str, text: str):
    client.put_object(Bucket=bucket, Key=key, Body=text.encode("utf-8"))


def delete_object(client, bucket: str, key: str):
    client.delete_object(Bucket=bucket, Key=key)


def split_chapters(text):
    text = text.replace('\r\n', '\n')
    chapters = re.split(r'(?=^Chương\s+\d+(?:[:：]|$))', text, flags=re.MULTILINE)
    return [ch.strip() for ch in chapters if ch.strip()]


def extract_start_number(chapter_text):
    match = re.search(r'^Chương\s+(\d+)', chapter_text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def send_message(text: str):
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    CHAT_ID = os.getenv("CHAT_ID")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
    }
    response = requests.post(url, data=payload)
    return response.json()

def _build_fetch_js(url: str, form_data: dict):
    # Hàm phụ để xử lý các ký tự đặc biệt có thể làm gãy cú pháp JS Template Literal
    def escape_js_template(text: str):
        if not isinstance(text, str):
            text = str(text)
        text = text.replace('\\', '\\\\')
        text = text.replace('`', '\\`')
        text = text.replace('${', '\\${')
        return text

    # KHÔNG dùng dấu phẩy (,) khi join, chỉ dùng ký tự xuống dòng (\n)
    form_items = "\n        ".join(
        [f"body.append('{k}', `{escape_js_template(v)}`);" for k, v in form_data.items()]
    )

    js = f"""
    async function send() {{
        const url = `{url}`;
        const body = new URLSearchParams();
        {form_items}
        try {{
            const res = await fetch(url, {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                    'X-Requested-With': 'XMLHttpRequest'
                }},
                body: body.toString(),
            }});
            const text = await res.text();
            let json;
            try {{
                json = JSON.parse(text);
            }} catch (e) {{
                return {{status: res.status, text}};
            }}
            return {{status: res.status, json}};
        }} catch (e) {{
            return {{status: -1, error: e.toString()}};
        }}
    }}
    return send();
    """
    return js

def create_page(cookie: str, cookie_cf_clearance: str):
    # Determine cookie domain from BASE_URL
    parsed = urlparse(BASE_URL)
    domain = parsed.hostname or ""

    co = ChromiumOptions()
    
    # KHÔNG dùng co.headless(True) nếu chạy bằng Xvfb (để bypass Cloudflare tốt hơn)
    # Nếu không dùng Xvfb ở YML, hãy bật dòng dưới đây:
    co.headless(True)

    # Các tham số bắt buộc cho môi trường Linux/Docker/GitHub Actions
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-gpu')
    co.set_argument('--disable-dev-shm-usage')
    # co.set_argument('--window-size=1920,1080') # Fix lỗi hiển thị
    # co.set_argument('--disable-blink-features=AutomationControlled') # Giúp bypass Cloudflare
    
    # time.sleep(2)
    
    page = ChromiumPage(co)

    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "X-Requested-With": "XMLHttpRequest",
    }
    page.set.headers(headers)

    cookies = [
        {"name": "cf_clearance", "value": cookie_cf_clearance, "domain": domain, "path": "/"},
        {"name": "ci_session", "value": cookie, "domain": domain, "path": "/"},
    ]
    page.set.cookies(cookies)

    for attempt in range(3):
        try:
            page.get(BASE_URL)
            page.wait(2, 4)
            page.wait.load_start()
            html = ""
            try:
                html = (page.html or "").lower()
            except Exception:
                continue

            if "just a moment" in html or "checking your browser" in html:
                print(f"⚠️ Lần {attempt+1}: Phát hiện Cloudflare, đợi thêm...")
                page.wait(5, 7)
                continue
            
            return page

        except Exception as e:
            print(f"⚠️ Lần {attempt+1} gặp lỗi kỹ thuật: {e}")
            page.wait(3)
            continue

    return page


def send_batch(page, story_id, start_number, chapters, published):
    chapter_content = ""
    for ch in chapters:
        lines = ch.splitlines()
        if not lines:
            continue
        title_line = lines[0].strip()
        body_lines = lines[1:]
        content = "\n".join(f"<p>{line.strip()}</p>" for line in body_lines if line.strip())
        chapter_html = f"<p>{title_line}</p>{content}"
        chapter_content += chapter_html

    data = {
        "story_id": story_id,
        "number_from": str(start_number),
        "number_to": str(start_number + len(chapters) - 1),
        "chapter_content": chapter_content,
        "published": str(published),
    }

    print(f"📤 Gửi chương {data['number_from']} → {data['number_to']} (published={published}) ...")

    url = f"{BASE_URL}/mystory/{story_id}/chapters/add_multi"
    js = _build_fetch_js(url, data)
    try:
        res = page.run_js(js)
        status = res.get("status") if isinstance(res, dict) else None
        if status == -1:
            err = res.get("error") if isinstance(res, dict) else None
            print(f"❌ Lỗi khi gọi fetch(): {err}")
            return False
        if status != 200:
            print(f"❌ Lỗi HTTP {status}: Không thể gửi chương.")
            return False

        response_data = res.get("json") if isinstance(res, dict) else None
        if not isinstance(response_data, dict):
            print(f"❌ Server không trả về JSON hợp lệ. Kết quả: {res}")
            return False

        if "Thêm thành công:" in response_data.get("message", ""):
            print("✅ Gửi thành công!")
            return True
        else:
            print(f"❌ Gửi thất bại hoặc không đúng định dạng: {response_data.get('message')}")
            send_message(f"❌ {story_id} gửi thất bại: {response_data.get('message')}")
            return False
    except Exception as e:
        print(f"❌ Lỗi khi gửi chương {start_number}-{start_number + len(chapters) - 1}: {e}")
        return False


def mark_story_full(page, story_id):
    url_info = f"{BASE_URL}/mystory/{story_id}/"
    try:
        page.get(url_info)
    except Exception as e:
        print(f"❌ Lỗi kết nối: {e}")
        return False

    html = page.html
    soup = BeautifulSoup(html, "html.parser")

    def safe_val(selector):
        el = soup.select_one(selector)
        if el is None:
            return ""
        return el.get("value", "") if el.has_attr("value") else el.text.strip()

    try:
        title = safe_val("input#title")
        author = safe_val("input#author")
        if not title or not author:
            print(f"⚠️ CẢNH BÁO: Không lấy được thông tin truyện {story_id}. Có thể cookie hết hạn. Hủy cập nhật FULL để tránh mất dữ liệu.")
            return False
        cover = safe_val("input#cover")
        type_el = soup.select_one("select#type option[selected]") or soup.select_one("select#type option")
        type_ = type_el.get("value", "") if type_el else ""
        genre = safe_val("input#genre")
        desc_el = soup.select_one("#story-desc")
        desc = desc_el.decode_contents() if desc_el else ""
    except Exception as e:
        print(f"⚠️ Lỗi khi parse HTML truyện {story_id}: {e}")
        return False

    data = {
        "title": title,
        "cover": cover,
        "desc": desc,
        "genre": genre,
        "author": author,
        "status": "1",  # FULL
        "type": type_,
    }

    url_update = f"{BASE_URL}/mystory/{story_id}/update"
    js = _build_fetch_js(url_update, data)
    try:
        res = page.run_js(js)
        status = res.get("status") if isinstance(res, dict) else None
        if status == -1:
            err = res.get("error") if isinstance(res, dict) else None
            print(f"❌ Lỗi khi gọi fetch() cập nhật FULL: {err}")
            return False
        if status != 200:
            print(f"❌ Lỗi HTTP {status} khi cập nhật FULL")
            return False
    except Exception as e:
        print(f"❌ Cập nhật thất bại: {e}")
        return False

    print(f"✅ Đã cập nhật truyện {story_id} thành FULL")
    return True


def add_story_id(client, bucket: str, key: str, story_id: str):
    existing_text = get_object_text(client, bucket, key)
    existing_ids = {line.strip() for line in existing_text.splitlines() if line.strip()}

    if story_id in existing_ids:
        return False

    new_text = (existing_text.rstrip("\n") + "\n" if existing_text else "") + story_id + "\n"
    put_object_text(client, bucket, key, new_text)
    return True


def adjust_ci_size(ci_size: int, start_number: int) -> int:
    """Điều chỉnh ci_size dựa vào start_number"""
    if ci_size == 5:
        ci_size = ci_size - random.randint(0, 3)
        if start_number < 100:
            return ci_size * 5 * random.randint(1, 2)
        elif start_number < 300:
            return ci_size
        elif start_number < 1000:
            return ci_size * 2 * random.randint(0, 2)
        elif start_number < 3000:
            return ci_size * 4 * random.randint(0, 2)
        else:
            return ci_size * 6 * random.randint(0, 2)

    elif ci_size == 1:
        ci_size = random.choice([1, 2])
        if start_number < 100:
            return ci_size
        elif start_number < 125:
            return ci_size * random.randint(9, 11) if random.randint(1, 10) == 1 else 0
        elif start_number < 200:
            return ci_size * 2
        elif start_number < 225:
            return ci_size * 2 * random.randint(9, 11) if random.randint(1, 10) == 1 else 0
        elif start_number < 400:
            return ci_size * random.randint(9, 11)
        elif start_number < 800:
            return ci_size * random.randint(18, 22) * random.randint(0, 2)
        elif start_number < 1600:
            return ci_size * random.randint(75, 85) if random.randint(1, 2) == 1 else 0
        else:
            return ci_size * random.randint(230, 250) if random.randint(1, 3) == 1 else 0

    elif ci_size == 2:
        if start_number < 100:
            return ci_size - random.randint(0, 1)
        else:
            return ci_size + random.randint(100, 200)


def main():
    r2 = get_r2_client()
    all_files = []
    for d, conf in DIR_CONFIGS.items():
        if not conf.get("cookie") or not conf.get("cookie_cf_clearance"):
            print(f"⚠️ Bỏ qua {d}: thiếu cookie hoặc cf_clearance.")
            continue
        for key in list_truyen_keys(r2, R2_BUCKET, d):
            all_files.append(
                {
                    "key": key,
                    "cookie": conf["cookie"],
                    "cookie_cf_clearance": conf.get("cookie_cf_clearance"),
                    "size": conf["size"],
                }
            )

    random.shuffle(all_files)
    print(f"📂 Tổng số file cần xử lý: {len(all_files)}")

    for f in all_files:
        object_key = f["key"]
        cookie = f["cookie"]
        cookie_cf_clearance = f.get("cookie_cf_clearance")
        ci_size = f["size"]

        dirname, filename = posixpath.split(object_key)
        story_id = filename.replace("truyen_", "").replace(".txt", "")
        story_id_list_key = posixpath.join(dirname, "storyidlist.txt")

        raw = get_object_text(r2, R2_BUCKET, object_key)

        chapters = split_chapters(raw)
        total_chapters = len(chapters)

        if total_chapters == 0:
            print(f"⚠️ Bỏ qua {filename}: không có chương hợp lệ.")
            continue

        published = 1
        max_batch = 10

        sent_count = 0
        success_all = True

        start_number_first = extract_start_number(chapters[0])
        if start_number_first is None:
            print(f"❌ Bỏ qua {filename} vì không tìm thấy số bắt đầu\n")
            continue

        ci_size = adjust_ci_size(ci_size, start_number_first) if ci_size != 0 else ci_size
        ci_size = min(400, ci_size)
        if ci_size == 0:
            print(f"⏸ Bỏ qua {filename} vì ci_size = 0\n")
            continue
        else:
            print(f"📌 {filename} sẽ thử gửi {ci_size} chương")

        page = create_page(cookie, cookie_cf_clearance)

        while sent_count < ci_size and sent_count < total_chapters:
            remaining_quota = ci_size - sent_count
            batch_size = min(max_batch, remaining_quota)
            this_batch = chapters[sent_count : sent_count + batch_size]

            start_number = extract_start_number(this_batch[0])
            if start_number is None:
                print(f"❌ Bỏ qua {filename} vì không tìm thấy số bắt đầu")
                success_all = False
                break

            if 40 <= start_number <= 50:
                added = add_story_id(r2, R2_BUCKET, story_id_list_key, story_id)
                if added:
                    print(f"✅ Đã thêm {story_id} vào {story_id_list_key}")
                else:
                    print(f"ℹ️ {story_id} đã có trong {story_id_list_key}")

            success = send_batch(page, story_id, start_number, this_batch, published)
            if not success:
                success_all = False
                break

            sent_count += len(this_batch)
            time.sleep((batch_size * 3) + random.randint(5, 10))

        if sent_count > 0:
            remaining = "\n\n".join(chapters[sent_count:])
            if remaining.strip() == "":
                delete_object(r2, R2_BUCKET, object_key)
            else:
                put_object_text(r2, R2_BUCKET, object_key, remaining)

            if remaining.strip() == "":
                print(f"File {filename} empty, deleted")

                if success_all:
                    if mark_story_full(page, story_id):
                        print(f"📗 Truyện {story_id} đã được cập nhật sang FULL")
                    else:
                        print(f"⚠️ Cập nhật truyện {story_id} sang FULL thất bại")
            else:
                print(f"🗑 Đã xóa {sent_count} chương khỏi {filename}")

            time.sleep(random.randint(0, 20))
            page.quit()
            delay = max(0, 300 - (sent_count * 3))
            print(f"⏳ Nghỉ {delay} giây trước khi xử lý file tiếp theo...\n")
            time.sleep(delay)
        else:
            print(f"⚠️ Gửi thất bại, chưa gửi được chương nào trong {filename}. Không xóa chương.")
        
        


if __name__ == "__main__":
    main()

