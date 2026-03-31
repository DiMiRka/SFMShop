class ShoppingCart:
    def __init__(self):
        self.items = []

    def __add__(self, item):
        self.items.append(item)
        return self.items

    def __len__(self):
        return len(self.items)

    def __iter__(self):
        return iter(self.items)
