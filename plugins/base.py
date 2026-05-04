"""Шаблон плагина"""


class BasePlugin:
    """Базовый класс для всех плагинов Quantis."""
    
    name = "Название Плагина"
    version = "1.0"
    author = "Really-Fun"
    description = "Нет описания"

    def __init__(self, app_context):
        self.app = app_context

    def on_load(self):
        """Вызывается при загрузке плагина. Здесь инициализируются UI/Сигналы."""
        pass

    def on_unload(self):
        """Вызывается при отключении плагина. Обязательно очищать ресурсы!"""
        pass

    def on_minimize(self):
        """Вызывается, когда окно свернули (для оптимизации)."""
        pass

    def on_restore(self):
        """Вызывается, когда окно развернули."""
        pass 