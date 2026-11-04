"""Хуки python-for-android (buildozer p4a.hook).

Выполняются в папке dist перед build.py, который собирает из шаблонов
ресурсы и манифест.
"""

from pathlib import Path

# Фон приложения (Theme.bg).
BG = "#0B0D12"

# Стиль активности KivySupportCutout — без родителя и без фона: пока стартует
# Python, Android показывал белое окно между заставкой и интерфейсом. Тёмный
# фон окна и заставки (API 31+), панели — в тон.
_THEME_ITEMS = """
        <item name="android:windowBackground">@color/quantis_bg</item>
        <item name="android:colorBackground">@color/quantis_bg</item>
        <item name="android:statusBarColor">@color/quantis_bg</item>
        <item name="android:navigationBarColor">@color/quantis_bg</item>
        <item name="android:windowSplashScreenBackground">@color/quantis_bg</item>"""
_MARK = "quantis_bg"


def _dark_theme() -> None:
    strings = Path("templates/strings.tmpl.xml")
    text = strings.read_text(encoding="utf-8")
    if _MARK in text:
        return
    anchor = '<item name="android:windowNoTitle">true</item>'
    if anchor not in text:
        print("[quantis] p4a_hook: стиль активности не найден, фон не задан")
        return
    text = text.replace(anchor, anchor + _THEME_ITEMS, 1)
    text = text.replace(
        "</resources>", f'    <color name="quantis_bg">{BG}</color>\n</resources>', 1
    )
    strings.write_text(text, encoding="utf-8")
    print("[quantis] p4a_hook: тёмный фон окна и заставки")


def before_apk_build(toolchain) -> None:
    # В шаблоне бутстрапа qt нет res/mipmap-anydpi-v26, а build.py пишет туда
    # icon.xml адаптивного значка, не создавая папку (FileNotFoundError).
    Path("src/main/res/mipmap-anydpi-v26").mkdir(parents=True, exist_ok=True)
    _dark_theme()
