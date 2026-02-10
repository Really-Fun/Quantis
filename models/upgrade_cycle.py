"""Продвинутая цикл, который позволяет получать предыдущий трек, текущий и следующий
Протокол и паттерн итератора: ✓
Single responsibility - True
Open/Closed - 50/50
Liskov - True
Interface segregation - True
Dependency - from Iterable (but this is okay)
"""

from typing import Iterable, Any, Optional

class UpgradeCycle:

    def __init__(self, values: Iterable[Any]) -> None:
        """Инициализируем цикл

        Args:
            values (Iterable[Any]): значения для цикла
        """
        self._index = 0
        self.values = tuple(values)

    def __iter__(self) -> "UpgradeCycle":
        """Возвращаем итератор

        Returns:
            UpgradeCycle: итератор
        """
        return self

    def __next__(self) -> Optional[Any]:
        """Возвращаем следующее значение

        Returns:
            Optional[Any]: следующее значение
        """
        temp = self.values[self._index]
        self._index = (self._index + 1) % len(self.values)
        return temp
    
    def __len__(self) -> int:
        """Возвращаем длину цикла

        Returns:
            int: длина цикла
        """
        return len(self.values)

    def move_previous(self) -> Optional[Any]:
        """Переключаемся на предыдущий трек

        Returns:
            Optional[Any]: предыдущий трек
        """
        if self._index != 0:
            self._index -= 1
        else:
            self._index = len(self.values) - 1
        return self.values[self._index]

    def peek_current(self) -> Optional[Any]:
        """Получаем текущий трек

        Returns:
            Optional[Any]: текущий трек
        """
        return self.values[self._index]

    def peek_previous(self) -> Optional[Any]:
        """Получаем предыдущий трек

        Returns:
            Optional[Any]: предыдущий трек
        """
        if self._index != 0:
            return self.values[self._index - 1]
        return self.values[len(self.values) - 1]
