import requests
import re
import os
import time

# === CẤU HÌNH COOKIE ===
cookie_ci_session = os.getenv("CI_SESSION")  # lấy từ biến môi trường GitHub Actions

# === THƯ MỤC CHỨA TRUYỆN ===
DATA_DIR = "noveldata"
BATCH_SIZE = 10

# === HÀM TÁCH CHƯƠNG ===
def split_chapters(text):
    chapters = re.split(r'(?=^Chương\s+\d+[:：])', text, flags=re.MULTILINE)
    return [ch.strip() for ch in chapters if ch.strip()]

# === HÀM LẤY SỐ CHƯƠNG ĐẦU TIÊN ===
def extract_start_number(chapter_text):
    match = re.search(r'^Chương\s+(\d+)', chapter_text, re.IGNORECASE)
    return int(match.group(1)) if match else None

# === GỬI LÔ CHƯƠNG ===
def send_batch(story_id, start_number, chapters):
    session = requests.Session()
    session.cookies.set("ci_session", cookie_ci_session)

    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "User-Agent": "Mozilla/5.0",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"https://tytnovel.xyz/mystory/{story_id}/chapters/new"
    }

    chapter_content = ""
    for ch in chapters:
        lines = ch.splitlines()
        if not lines:
            continue
        title_line = lines[0].strip()
        body_lines = lines[1:]
        content = '\n'.join(f"<p>{line.strip()}</p>" for line in body_lines if line.strip())
        chapter_html = f"<p>{title_line}</p>{content}"
        chapter_content += chapter_html

    data = {
        "story_id": story_id,
        "number_from": start_number,
        "number_to": start_number + len(chapters) - 1,
        "chapter_content": chapter_content,
        "published": 1
    }

    print(f"📤 Gửi chương {data['number_from']} → {data['number_to']} ...")

    try:
        res = session.post(
            f"https://tytnovel.xyz/mystory/{story_id}/chapters/add_multi",
            headers=headers,
            data=data,
            timeout=30
        )
        res.raise_for_status()
        print("✅ Thành công!")
        return True
    except Exception as e:
        print(f"❌ Lỗi khi gửi chương {start_number}-{start_number + len(chapters) - 1}: {e}")
        return False

# === QUÉT FILE TRONG THƯ MỤC ===
for filename in os.listdir(DATA_DIR):
    if filename.startswith("truyen_") and filename.endswith(".txt"):
        story_id = filename.replace("truyen_", "").replace(".txt", "")
        file_path = os.path.join(DATA_DIR, filename)

        with open(file_path, "r", encoding="utf-8") as f:
            raw = f.read()

        chapters = split_chapters(raw)
        if len(chapters) < 21:
            print(f"⚠️ Bỏ qua {filename} (chỉ có {len(chapters)} chương, yêu cầu tối thiểu 20).")
            continue

        start_number = extract_start_number(chapters[0])
        if start_number is None:
            print(f"❌ Không tìm thấy số bắt đầu trong {filename}. Bỏ qua.")
            continue

        batch = chapters[:BATCH_SIZE]
        success = send_batch(story_id, start_number, batch)

        # Nếu gửi thành công → ghi lại phần chưa gửi vào file
        if success:
            remaining = "\n\n".join(chapters[BATCH_SIZE:])
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(remaining)
            print(f"🗑 Đã xóa chương {start_number} → {start_number + BATCH_SIZE - 1} khỏi {filename}")
        else:
            print(f"⚠️ Bỏ qua xóa chương do gửi lỗi.")
            
        time.sleep(60)
