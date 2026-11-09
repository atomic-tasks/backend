from dataclasses import dataclass
from decimal import Decimal

from atomic_tasks.domain.exceptions import InvalidFieldError

MIN_WEIGHT = Decimal("0.5")
MAX_WEIGHT = Decimal("2.0")
DEFAULT_WEIGHT = Decimal("1.0")
_WEIGHT_STEP = Decimal("0.01")

MAX_TITLE_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 10_000


@dataclass(frozen=True)
class Weight:
    """Вес папки или задачи (ADR 0003): 0.5–2.0, не больше двух знаков после запятой.

    Decimal, а не float: веса перемножаются по пути в дереве, и 1.1 должно остаться 1.1.
    """

    value: Decimal

    def __post_init__(self) -> None:
        """Проверяет диапазон и точность, приводит к двум знакам (1.1 → 1.10).

        Лишние знаки — ошибка, а не округление: колонка numeric(3,2) молча округлила бы 1.005.
        """
        v = self.value
        if not v.is_finite() or not MIN_WEIGHT <= v <= MAX_WEIGHT or v != v.quantize(_WEIGHT_STEP):
            raise InvalidFieldError(
                f"Вес — число от {MIN_WEIGHT} до {MAX_WEIGHT} с шагом {_WEIGHT_STEP}.",
            )
        # frozen-dataclass: присвоение в __post_init__ только через object.__setattr__
        object.__setattr__(self, "value", v.quantize(_WEIGHT_STEP))

    @classmethod
    def default(cls) -> Weight:
        """Нейтральный вес 1.0: не влияет на приоритет."""
        return cls(DEFAULT_WEIGHT)


@dataclass(frozen=True, kw_only=True)
class ItemCount:
    """Сколько папок и задач — например, открытых в поддереве или прямых детей."""

    folders: int = 0
    tasks: int = 0

    @property
    def total(self) -> int:
        """Папки и задачи вместе."""
        return self.folders + self.tasks


def normalize_title(title: str) -> str:
    """Обрезает пробелы и проверяет длину названия: 1–200 символов."""
    title = title.strip()
    if not title or len(title) > MAX_TITLE_LENGTH:
        raise InvalidFieldError(f"Название — от 1 до {MAX_TITLE_LENGTH} символов.")
    return title


def normalize_description(description: str | None) -> str | None:
    """Обрезает пробелы и проверяет длину описания. Пустое описание хранится как None."""
    if description is None:
        return None
    description = description.strip()
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise InvalidFieldError(f"Описание — не длиннее {MAX_DESCRIPTION_LENGTH} символов.")
    return description or None
