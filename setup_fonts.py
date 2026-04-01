"""
在 Linux 環境下載中文字型（Render 部署用）
"""
import os
import urllib.request

FONT_DIR = os.path.join(os.path.dirname(__file__), 'fonts')
FONT_URL = 'https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Regular.otf'
FONT_BOLD_URL = 'https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Bold.otf'


def get_font_paths():
    """回傳 (regular, bold) 字型路徑"""
    # Windows：用微軟正黑體
    win_regular = 'C:/Windows/Fonts/msjh.ttc'
    win_bold = 'C:/Windows/Fonts/msjhbd.ttc'
    if os.path.exists(win_regular):
        bold = win_bold if os.path.exists(win_bold) else win_regular
        return win_regular, bold

    # Linux：用 Noto Sans CJK
    os.makedirs(FONT_DIR, exist_ok=True)
    regular = os.path.join(FONT_DIR, 'NotoSansCJKtc-Regular.otf')
    bold = os.path.join(FONT_DIR, 'NotoSansCJKtc-Bold.otf')

    if not os.path.exists(regular):
        print('下載中文字型 (Regular)...')
        urllib.request.urlretrieve(FONT_URL, regular)

    if not os.path.exists(bold):
        print('下載中文字型 (Bold)...')
        urllib.request.urlretrieve(FONT_BOLD_URL, bold)

    return regular, bold
