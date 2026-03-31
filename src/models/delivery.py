from abc import ABC, abstractmethod


class Delivery(ABC):
    @abstractmethod
    def calculate_cost(self, distance: float) -> float:
        pass


class StandardDelivery(Delivery):
    def calculate_cost(self, distance: float) -> float:
        return distance * 10


class ExpressDelivery(Delivery):
    def calculate_cost(self, distance: float) -> float:
        return distance * 20


def delivery_cost(delivery: Delivery, distance: float) -> float:
    return delivery.calculate_cost(distance)
