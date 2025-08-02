import requests
import re
import os
import time
from pathlib import Path
import json

# 🛡 Token từ biến môi trường (đặt trong GitHub Secrets)
AUTH_TOKEN = os.environ.get("AUTH_TOKEN")

# 🔧 Cấu hình
FOLDER_PATH = "noveldata"  # Thư mục chứa các file chương
CHAPTERS_PER_RUN = 10       # Số chương mỗi truyện sẽ đăng mỗi lần chạy

# ============================================
# TÁCH CHƯƠNG TỪ FILE TXT
# ============================================
def tach_cac_chuong(noi_dung):
    pattern = r"^Chương\s+(\d+):\s+(.*)$"
    matches = list(re.finditer(pattern, noi_dung, re.MULTILINE))
    chapters = []

    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(noi_dung)

        chapter_num = int(match.group(1))
        chapter_name = match.group(2).strip()
        chapter_raw = noi_dung[start:end].strip()

        chapter_content = "".join(
            f"<p>{line.strip()}</p>" for line in chapter_raw.splitlines() if line.strip()
        )

        chapters.append({
            "num": chapter_num,
            "name": chapter_name,
            "content": chapter_content
        })
    return chapters

# ============================================
# GỬI POST ĐĂNG CHƯƠNG
# ============================================
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

# ============================================
# GHI LẠI NỘI DUNG CÒN LẠI VÀO FILE
# ============================================
def ghi_lai_file(file_path, noi_dung_con_lai):
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(noi_dung_con_lai)

# ============================================
# HÀM CHÍNH
# ============================================
def main():
    txt_files = list(Path(FOLDER_PATH).glob("truyen_*.txt"))
    if not txt_files:
        print("❌ Không tìm thấy file nào dạng truyen_<bookCode>.txt")
        return

    for file_path in txt_files:
        book_code = file_path.stem.split("_")[1]
        print(f"\n📘 Xử lý truyện bookCode={book_code} từ file {file_path.name}")

        noi_dung = file_path.read_text(encoding="utf-8")
        cac_chuong = tach_cac_chuong(noi_dung)

        if not cac_chuong:
            print("⚠️  Không tìm thấy chương nào.")
            continue

        print(f"🔢 Tổng cộng {len(cac_chuong)} chương. Đăng tối đa {CHAPTERS_PER_RUN} chương.")

        da_dang = 0
        for i, chapter in enumerate(cac_chuong[:CHAPTERS_PER_RUN]):
            print(f"🚀 Đang đăng chương {chapter['num']}: {chapter['name']}")
            success = dang_chuong(book_code, chapter)
            if success:
                da_dang += 1
                time.sleep(3)  # Giãn cách tránh spam
            else:
                print(f"⚠️  Bỏ qua chương {chapter['num']} do lỗi khi đăng.")

        if da_dang > 0:
            # Xóa nội dung chương đã đăng khỏi file
            last_chap = cac_chuong[da_dang - 1]["num"]
            match = re.search(rf"^Chương\s+{last_chap + 1}:", noi_dung, re.MULTILINE)
            if match:
                noi_dung_con_lai = noi_dung[match.start():]
                ghi_lai_file(file_path, noi_dung_con_lai)
                print(f"🧹 Đã xoá {da_dang} chương đã đăng khỏi {file_path.name}")
            else:
                # Không còn chương tiếp theo -> xoá file
                file_path.unlink()
                print(f"🗑 Đã xoá file {file_path.name} vì đã đăng hết tất cả chương.")

if __name__ == "__main__":
    main()
