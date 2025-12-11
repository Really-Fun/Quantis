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

    def __init__(self, values: Iterable[Any]):
        self._index = 0
        self.values = tuple(values)

    def __iter__(self):
        return self

    def __next__(self) -> Optional[Any]:
        temp = self.values[self._index]
        self._index = (self._index + 1) % len(self.values)
        return temp

    def move_previous(self) -> Optional[Any]:
        if self._index != 0:
            self._index -= 1
        else:
            self._index = len(self.values) - 1
        return self.values[self._index]

    def peek_current(self) -> Optional[Any]:
        return self.values[self._index]

    def peek_previous(self) -> Optional[Any]:
        if self._index != 0:
            return self.values[self._index - 1]
        return self.values[len(self.values) - 1]