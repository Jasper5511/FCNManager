"""
跨平台中文字型載入
Windows: 微軟正黑體 (Regular + Bold)
Linux/Render: Noto Sans TC (Static Regular + Variable for Bold)
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

    # Linux：先找系統字型
    for p in ['/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
              '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
              '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',
              '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc']:
        if os.path.exists(p):
            return p, p

    # 下載 Noto Sans TC 可變字型
    os.makedirs(FONT_DIR, exist_ok=True)
    static_regular = os.path.join(FONT_DIR, 'NotoSansTC-Regular.ttf')
    var_font = os.path.join(FONT_DIR, 'NotoSansTC-Variable.ttf')

    if not os.path.exists(var_font):
        import urllib.request
        url = 'https://github.com/google/fonts/raw/main/ofl/notosanstc/NotoSansTC%5Bwght%5D.ttf'
        try:
            print('下載中文字型...')
            urllib.request.urlretrieve(url, var_font)
        except Exception as e:
            print(f'字型下載失敗: {e}')
            return None, None

    # 產生靜態 Regular（fpdf2 需要靜態字型）
    if not os.path.exists(static_regular) or os.path.getsize(static_regular) < 100000:
        try:
            from fontTools.ttLib import TTFont
            print('轉換字型為靜態格式...')
            font = TTFont(var_font)
            for tag in ['fvar', 'STAT', 'gvar', 'cvar', 'avar', 'HVAR', 'VVAR', 'MVAR']:
                if tag in font:
                    del font[tag]
            font.save(static_regular)
            print(f'靜態字型已產生 ({os.path.getsize(static_regular)} bytes)')
        except Exception as e:
            print(f'字型轉換失敗: {e}')
            return var_font, var_font

    # Regular=靜態（給 fpdf2）, Bold=可變字型（給 Pillow，透過 set_variation 設粗體）
    return static_regular, var_font
