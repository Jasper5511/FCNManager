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
        import urllib.request
        urls = [
            'https://github.com/google/fonts/raw/main/ofl/notosanstc/NotoSansTC%5Bwght%5D.ttf',
            'https://raw.githubusercontent.com/googlefonts/noto-cjk/main/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Regular.otf',
        ]
        for url in urls:
            try:
                print(f'下載中文字型: {url[:60]}...')
                urllib.request.urlretrieve(url, font_file)
                if os.path.exists(font_file) and os.path.getsize(font_file) > 10000:
                    print(f'字型下載完成 ({os.path.getsize(font_file)} bytes)')
                    break
                else:
                    os.remove(font_file)
            except Exception as e:
                print(f'字型下載失敗: {e}')
                if os.path.exists(font_file):
                    os.remove(font_file)

    if os.path.exists(font_file):
        return font_file, font_file
    return None, None
