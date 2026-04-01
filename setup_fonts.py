"""
跨平台中文字型載入
Windows: 微軟正黑體
Linux/Render: Noto Sans CJK (apt 安裝) 或下載
"""
import os

FONT_DIR = os.path.join(os.path.dirname(__file__), 'fonts')


def get_font_paths():
    """回傳 (regular, bold) 字型路徑"""
    # Windows：微軟正黑體
    win_regular = 'C:/Windows/Fonts/msjh.ttc'
    win_bold = 'C:/Windows/Fonts/msjhbd.ttc'
    if os.path.exists(win_regular):
        bold = win_bold if os.path.exists(win_bold) else win_regular
        return win_regular, bold

    # Linux：先找系統安裝的 Noto CJK（apt install fonts-noto-cjk）
    linux_paths = [
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
    ]
    for p in linux_paths:
        if os.path.exists(p):
            return p, p

    # 備援：下載字型
    os.makedirs(FONT_DIR, exist_ok=True)
    font_file = os.path.join(FONT_DIR, 'NotoSansTC.ttf')
    if not os.path.exists(font_file):
        try:
            import urllib.request
            url = 'https://github.com/google/fonts/raw/main/ofl/notosanstc/NotoSansTC%5Bwght%5D.ttf'
            print('下載中文字型...')
            urllib.request.urlretrieve(url, font_file)
        except Exception as e:
            print(f'字型下載失敗: {e}')
            return None, None

    return font_file, font_file
