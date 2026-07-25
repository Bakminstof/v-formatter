class ReprMixin:
    def __str__(self) -> str:
        return self.__class__.__name__

    def __repr__(self) -> str:
        return f"'{self.__str__()}'"
