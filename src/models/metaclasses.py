class ModelMeta(type):
    _registry = {}

    def __new__(cls, name, bases, attrs, **kwargs):

        def to_dict(self):
            return self.__dict__
        attrs["to_dict"] = to_dict

        new_class = super().__new__(cls, name, bases, attrs)
        cls._registry[name] = new_class

        return new_class
