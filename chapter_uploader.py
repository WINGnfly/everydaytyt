import requests
import re
import os
import time
from pathlib import Path

# 🛡 Lấy token từ biến môi trường (GitHub Actions secret)
AUTH_TOKEN = os.environ.get("AUTH_TOKEN")

# 🔧 Cấu hình
FOLDER_PATH = "noveldata"  # Thư mục chứa các file chương, ví dụ: truyen_32854696.txt
CHAPTERS_PER_RUN = 5  # Mỗi truyện chỉ đăng 5 chương mỗi lần chạy

import json

PROGRESS_FILE = "progress.json"

def load_progress():
    if not Path(PROGRESS_FILE).exists():
        return {}
    return json.loads(Path(PROGRESS_FILE).read_text(encoding="utf-8"))

def save_progress(progress):
    Path(PROGRESS_FILE).write_text(json.dumps(progress, indent=2), encoding="utf-8")

# ==============================================
# HÀM TÁCH CHƯƠNG TỪ FILE TXT
# ==============================================
def tach_cac_chuong(noi_dung):
    pattern = r"^Chương\s(\d+):\s(.*)$"
    matches = list(re.finditer(pattern, noi_dung, re.MULTILINE))

    chapters = []
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(noi_dung)

        chapter_num = int(match.group(1))
        chapter_name = match.group(2).strip()
        chapter_content_raw = noi_dung[start:end].strip()

        chapter_content = "".join(
            f"<p>{line.strip()}</p>"
            for line in chapter_content_raw.splitlines()
            if line.strip()
        )

        chapters.append({
            "num": chapter_num,
            "name": chapter_name,
            "content": chapter_content
        })
    return chapters

# ==============================================
# GỬI POST ĐĂNG CHƯƠNG
# ==============================================
def dang_chuong(book_code, chapter):
    url = "https://tienvuc.info/api/chapters"
    payload = {
        "num": chapter["num"],
        "name": chapter["name"],
        "bookCode": book_code,
        "checked": True,
        "coins": 0,
        "content": chapter["content"],
        "isPublic": True,
        "override": False,
        "uploaded": False
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": AUTH_TOKEN,
        "Origin": "https://tienvuc.info",
        "Referer": f"https://tienvuc.info/dashboard/books/{book_code}/chapters/import",
        "DNT": "1",
    }

    response = requests.post(url, json=payload, headers=headers)
    if response.status_code in [200, 201]:
        print(f"✅ Đăng chương {chapter['num']} thành công.")
        return True
    else:
        print(f"❌ Lỗi khi đăng chương {chapter['num']}: {response.status_code} - {response.text}")
        return False

# ==============================================
# HÀM CHÍNH: LẶP QUA CÁC FILE CHƯƠNG
# ==============================================
def ghi_lai_file(file_path, noi_dung_con_lai):
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(noi_dung_con_lai)

def main():
    txt_files = list(Path(FOLDER_PATH).glob("truyen_*.txt"))
    if not txt_files:
        print("❌ Không tìm thấy file nào có tên dạng truyen_<bookCode>.txt")
        return

    for file_path in txt_files:
        book_code = file_path.stem.split("_")[1]
        print(f"\n📚 Đang xử lý truyện bookCode={book_code} từ file {file_path.name}")

        noi_dung = file_path.read_text(encoding="utf-8")
        cac_chuong = tach_cac_chuong(noi_dung)

        if not cac_chuong:
            print("⚠️  Không tìm thấy chương nào.")
            continue

        print(f"🔢 Tổng {len(cac_chuong)} chương. Đăng tối đa {CHAPTERS_PER_RUN} chương lần này.")

        # Xác định vị trí chương cuối cùng đã đăng thành công
        vi_tri_cuoi = 0
        da_dang = 0

        for i, chapter in enumerate(cac_chuong[:CHAPTERS_PER_RUN]):
            print(f"🚀 Đăng chương {chapter['num']}: {chapter['name']}")
            success = dang_chuong(book_code, chapter)
            if success:
                vi_tri_cuoi = noi_dung.find(chapter["name"], vi_tri_cuoi)
                da_dang += 1
                time.sleep(3)

        if da_dang > 0:
            # Tìm lại vị trí bắt đầu của chương tiếp theo
            match = re.search(rf"Chương\s+{chapter['num'] + 1}:", noi_dung)
            noi_dung_con_lai = noi_dung[match.start():] if match else ""
            ghi_lai_file(file_path, noi_dung_con_lai)
            print(f"🧹 Đã xóa {da_dang} chương đã đăng khỏi {file_path.name}")


if __name__ == "__main__":
    main()
