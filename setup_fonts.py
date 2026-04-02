"""
跨平台中文字型載入
Windows: 微軟正黑體
Linux/Render: 下載 Noto Sans TC 並轉為靜態字型
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

    # 下載並轉換（Regular + Bold 兩個字重）
    os.makedirs(FONT_DIR, exist_ok=True)
    static_regular = os.path.join(FONT_DIR, 'NotoSansTC-Regular.ttf')
    static_bold = os.path.join(FONT_DIR, 'NotoSansTC-Bold.ttf')

    if (os.path.exists(static_regular) and os.path.getsize(static_regular) > 100000
            and os.path.exists(static_bold) and os.path.getsize(static_bold) > 100000):
        return static_regular, static_bold

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

    # 從可變字型產出 Regular(400) 和 Bold(700) 兩個靜態字型
    try:
        from fontTools.ttLib import TTFont
        from fontTools.instancer import instantiateVariableFont

        for weight, out_path in [(400, static_regular), (700, static_bold)]:
            if os.path.exists(out_path) and os.path.getsize(out_path) > 100000:
                continue
            print(f'產生字型 wght={weight}...')
            font = TTFont(var_font)
            instantiateVariableFont(font, {'wght': weight})
            for tag in ['fvar', 'STAT', 'gvar', 'cvar', 'avar', 'HVAR', 'VVAR', 'MVAR']:
                if tag in font:
                    del font[tag]
            font.save(out_path)
            print(f'已產生 {out_path} ({os.path.getsize(out_path)} bytes)')

        return static_regular, static_bold
    except ImportError:
        # 沒有 instancer，退回移除可變表的方式
        print('fontTools.instancer 不可用，使用預設字重')
        try:
            from fontTools.ttLib import TTFont
            font = TTFont(var_font)
            for tag in ['fvar', 'STAT', 'gvar', 'cvar', 'avar', 'HVAR', 'VVAR', 'MVAR']:
                if tag in font:
                    del font[tag]
            font.save(static_regular)
            return static_regular, static_regular
        except Exception as e:
            print(f'字型轉換失敗: {e}')
            return var_font, var_font
    except Exception as e:
        print(f'字型轉換失敗: {e}')
        return var_font, var_font
