"""Продвинутый циклический итератор с навигацией вперёд/назад.

Паттерн Итератор: ✓
Single Responsibility: ✓ — только навигация по коллекции
"""

from __future__ import annotations

from typing import Iterable, Iterator, TypeVar

TrackType = TypeVar("TrackType")


class UpgradeCycle(Iterator[TrackType]):
    """Продвинутый цикл.

    Attributes:
        values: Кортеж элементов.
    """

    def __init__(self, values: Iterable[TrackType]) -> None:
        self._index = 0
        self.values: tuple[TrackType, ...] = tuple(values)

    def __iter__(self) -> UpgradeCycle[TrackType]:
        """Возвращаем итератор

        Returns:
            UpgradeCycle: итератор
        """
        return self

    def __next__(self) -> TrackType:
        """Возвращаем следующее значение

        Returns:
            Optional[TrackType]: следующее значение
        """

        self._index = (self._index + 1) % len(self.values)
        return self.values[self._index]

    def __len__(self) -> int:
        return len(self.values)

    def __getitem__(self, index: int) -> TrackType:
        return self.values[index]

    def index(self, item: TrackType) -> int:
        return self.values.index(item)

    def remove(self, item: TrackType) -> bool:
        """Удаляет элемент из цикла.

        Returns:
            ``True`` если элемент найден и удалён, иначе ``False``.
        """
        lst = list(self.values)
        try:
            idx = lst.index(item)
        except ValueError:
            return False
        lst.pop(idx)
        self.values = tuple(lst)
        if self._index >= len(self.values) > 0:
            self._index = len(self.values) - 1
        return True

    def move_previous(self) -> TrackType:
        """Переключаемся на предыдущий трек

        Returns:
            Optional[TrackType]: предыдущий трек
        """
        if self._index != 0:
            self._index -= 1
        else:
            self._index = len(self.values) - 1
        return self.values[self._index]

    def peek_current(self) -> TrackType:
        """Получаем текущий трек

        Returns:
            Optional[TrackType]: текущий трек
        """
        return self.values[self._index]

    def peek_previous(self) -> TrackType:
        """Получаем предыдущий трек

        Returns:
            Optional[TrackType]: предыдущий трек
        """
        if self._index != 0:
            return self.values[self._index - 1]
        return self.values[len(self.values) - 1]

    def set_index(self, index: int) -> None:
        """Устанавливает текущий индекс."""
        self._index = index
