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

    # 備援：下載標準 TTF 字型（非可變字重，相容 fpdf2）
    os.makedirs(FONT_DIR, exist_ok=True)
    font_file = os.path.join(FONT_DIR, 'NotoSansTC-Regular.ttf')
    if not os.path.exists(font_file):
        urls = [
            'https://github.com/google/fonts/raw/main/ofl/notosanstc/static/NotoSansTC-Regular.ttf',
            'https://github.com/googlefonts/noto-cjk/releases/download/Sans2.004/08_NotoSansCJKtc.zip',
        ]
        import urllib.request
        for url in urls:
            try:
                if url.endswith('.ttf'):
                    print(f'下載中文字型...')
                    urllib.request.urlretrieve(url, font_file)
                    if os.path.exists(font_file) and os.path.getsize(font_file) > 1000:
                        print('字型下載完成')
                        break
            except Exception as e:
                print(f'字型下載失敗 ({url}): {e}')
                continue

    if os.path.exists(font_file):
        return font_file, font_file
    return None, None
