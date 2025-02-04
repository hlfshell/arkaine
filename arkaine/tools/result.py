class Result:

    def __init__(
        self,
        type: str,
        description: str,
    ):
        self.type = type
        self.description = description

    def __str__(self):
        return f"({self.type}) - {self.description}"

    def __repr__(self):
        return self.__str__()

    @property
    def type_str(self) -> str:
        """
        Since some might pass in the literal type instead of the str of the
        class, we should ensure we convert the type correctly to a string for
        parsing.

        It is not simply str(self.type) as that tends to add "<class 'type'>"
        to the string.
        """
        if isinstance(self.type, str):
            return self.type
        else:
            try:
                return str(self.type).split("'")[1]
            except Exception:
                return str(self.type)

    def to_json(self):
        return {
            "type": self.type_str,
            "description": self.description,
        }

    def from_json(self, json):
        return Result(json["type"], json["description"])
