import json
import time
import os
import sys
import random
import datetime
import posixpath
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError
from DrissionPage import ChromiumPage, ChromiumOptions

# Lay cookie session tu GitHub Secrets
cookie_ci_session = os.getenv("CI_SESSION")
cookie_cf_clearance = os.getenv("CF_CLEARANCE")
DATA_DIR = os.getenv("DATA_DIR")
BASE_URL = os.getenv("BASE_URL")
R2_ENDPOINT = os.getenv("R2_ENDPOINT")
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY")
R2_SECRET_KEY = os.getenv("R2_SECRET_KEY")
R2_BUCKET = os.getenv("R2_BUCKET")
R2_REGION = os.getenv("R2_REGION", "auto")

if not cookie_ci_session:
    print("❌ Thiếu CI_SESSION (chưa set secrets).")
    sys.exit(1)

if not cookie_cf_clearance:
    print("❌ Thiếu CF_CLEARANCE (chưa set secrets).")
    sys.exit(1)

if not DATA_DIR:
    print("❌ Thiếu DATA_DIR (chưa set env).")
    sys.exit(1)

story_list_key = posixpath.join(DATA_DIR, "storyidlist.txt")

if not R2_ENDPOINT or not R2_ACCESS_KEY or not R2_SECRET_KEY or not R2_BUCKET:
    print("Thiếu các biến R2.")
    sys.exit(1)


def get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        region_name=R2_REGION,
    )


def get_object_text_required(client, bucket: str, key: str) -> str:
    try:
        resp = client.get_object(Bucket=bucket, Key=key)
        return resp["Body"].read().decode("utf-8")
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
            print(f"Không tìm thấy file: {key}")
            sys.exit(1)
        raise

def _build_fetch_js(url: str, form_data: dict):
    def escape_js_template(text: str):
        if not isinstance(text, str):
            text = str(text)
        text = text.replace("\\", "\\\\")
        text = text.replace("`", "\\`")
        text = text.replace("${", "\\${")
        return text

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
    co.set_argument('--window-size=1920,1080') # Fix lỗi hiển thị
    co.set_argument('--disable-blink-features=AutomationControlled') # Giúp bypass Cloudflare

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
        except Exception as e:
            print(f"⚠️ Không thể truy cập {BASE_URL}: {e}")
            time.sleep(3)
            continue

        html = (page.html or "").lower()
        if "just a moment" in html or "checking your browser" in html:
            print("⚠️ Phát hiện Cloudflare challenge, đợi 5s rồi thử lại...")
            time.sleep(5)
            continue
        break

    return page


def split_into_7_parts(lst):
    return [lst[i::7] for i in range(7)]


def main():
    r2 = get_r2_client()
    story_text = get_object_text_required(r2, R2_BUCKET, story_list_key)
    all_story_ids = [line.strip() for line in story_text.splitlines() if line.strip()]

    parts = split_into_7_parts(all_story_ids)
    today_index = datetime.datetime.today().weekday()
    story_ids = parts[today_index]

    page = create_page(cookie_ci_session, cookie_cf_clearance)

    for i, storyid in enumerate(story_ids, 1):
        url = f"{BASE_URL}/mystory/{storyid}/withdraw_to_owner"
        js = _build_fetch_js(url, {})
        try:
            res = page.run_js(js)
            status = res.get("status") if isinstance(res, dict) else None
            if status == -1:
                err = res.get("error") if isinstance(res, dict) else None
                print(f"[{i}] {storyid}: 🚨 Lỗi khi gọi fetch() -> {err}")
                time.sleep(random.randint(10, 20))
                continue
            if status != 200:
                print(f"[{i}] {storyid}: ⚠️ HTTP {status}: {res}")
                time.sleep(random.randint(10, 20))
                continue

            data = res.get("json") if isinstance(res, dict) else None
            if not isinstance(data, dict):
                text = res.get("text") if isinstance(res, dict) else ""
                print(f"[{i}] {storyid}: ⚠️ Không phải JSON hợp lệ -> {str(text)[:100]}...")
                time.sleep(random.randint(10, 20))
                continue

            if data.get("status") is True and "thành công" in data.get("message", "").lower():
                print(f"[{i}] {storyid}: ✅ Thành công ({data['message']})")
            else:
                print(f"[{i}] {storyid}: ❌ Thất bại ({data})")

        except Exception as e:
            print(f"[{i}] {storyid}: 🚨 Lỗi khi gửi request -> {e}")
        time.sleep(random.randint(10, 20))

    page.quit()


if __name__ == "__main__":
    main()
