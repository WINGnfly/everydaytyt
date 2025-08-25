import requests
import re
import os
import time

# === CẤU HÌNH COOKIE ===
cookie_ci_session = os.getenv("CI_SESSION")  # lấy từ GitHub Secrets
if not cookie_ci_session:
    print("❌ Không tìm thấy CI_SESSION. Vui lòng thiết lập biến môi trường.")
    exit(1)

# === THƯ MỤC CHỨA TRUYỆN ===
DATA_DIR = "noveldata"

# === HÀM TÁCH CHƯƠNG ===
def split_chapters(text):
    chapters = re.split(r'(?=^Chương\s+\d+[:：])', text, flags=re.MULTILINE)
    return [ch.strip() for ch in chapters if ch.strip()]

# === HÀM LẤY SỐ CHƯƠNG ĐẦU TIÊN ===
def extract_start_number(chapter_text):
    match = re.search(r'^Chương\s+(\d+)', chapter_text, re.IGNORECASE)
    return int(match.group(1)) if match else None

# === HÀM GỬI 1 LÔ CHƯƠNG ===
def send_batch(story_id, start_number, chapters, published):
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
        "published": published
    }

    print(f"📤 Gửi chương {data['number_from']} → {data['number_to']} (published = {published}) ...")

    try:
        res = session.post(
            f"https://tytnovel.xyz/mystory/{story_id}/chapters/add_multi",
            headers=headers,
            data=data,
            timeout=30
        )
        res.raise_for_status()
        response_data = res.json()

        # Kiểm tra message có chứa "Thêm thành công:"
        if "Thêm thành công:" in response_data.get("message", ""):
            print("✅ Gửi thành công!")
            return True
        else:
            print(f"❌ Gửi thất bại hoặc không đúng định dạng: {response_data.get('message')}")
            return True

    except Exception as e:
        print(f"❌ Lỗi khi gửi chương {start_number}-{start_number + len(chapters) - 1}: {e}")
        return False

# === DUYỆT TẤT CẢ FILE TRUYỆN ===
for filename in os.listdir(DATA_DIR):
    if filename.startswith("truyen_") and filename.endswith(".txt"):
        story_id = filename.replace("truyen_", "").replace(".txt", "")
        file_path = os.path.join(DATA_DIR, filename)

        with open(file_path, "r", encoding="utf-8") as f:
            raw = f.read()

        chapters = split_chapters(raw)
        total_chapters = len(chapters)

        if total_chapters == 0:
            print(f"⚠️ Bỏ qua {filename}: không có chương nào.")
            continue

        # is_draft = total_chapters < 11
        # if is_draft:
        #     print(f"📄 Truyện {filename} chỉ có {total_chapters} chương → gửi ở chế độ NHÁP (published = 0)")

        # published = 0 if is_draft else 1

        published = 1

        # 👇 Nếu ít hơn 10 chương → gửi hết
        batch_size = min(10, total_chapters)
        batch = chapters[:batch_size]

        start_number = extract_start_number(batch[0])
        if start_number is None:
            print(f"❌ Không tìm thấy số bắt đầu trong {filename}. Bỏ qua.")
            continue

        success = send_batch(story_id, start_number, batch, published)

        if success:
            remaining = "\n\n".join(chapters[batch_size:])
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(remaining)
            print(f"🗑 Đã xóa chương {start_number} → {start_number + batch_size - 1} khỏi {filename}")
        else:
            print(f"⚠️ Gửi thất bại. Không xóa chương trong {filename}")

        # 💤 Delay 60s giữa các truyện
        print("⏳ Nghỉ 60 giây trước khi xử lý truyện tiếp theo...\n")
        time.sleep(0)
