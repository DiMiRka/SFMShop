import sys
from dataclasses import dataclass
from math import ceil

sys.stdout.reconfigure(encoding="utf-8")


HEADROOM = 1.5


@dataclass(frozen=True)
class Endpoint:
    name: str
    expected_rps: float
    avg_ms: float


def worker_capacity(avg_ms: float) -> float:
    if avg_ms <= 0:
        raise ValueError("avg_ms must be greater than 0")
    return 1000 / avg_ms


def workers_needed(ep: Endpoint, headroom: float) -> int:
    if headroom <= 0:
        raise ValueError("headroom must be greater than 0")
    required_rps = ep.expected_rps * headroom
    return ceil(required_rps / worker_capacity(ep.avg_ms))


def tier(total_rps: float) -> str:
    if total_rps < 100:
        return "VPS/PaaS"
    if total_rps <= 1000:
        return "Cloud"
    return "Cloud + Kubernetes"


def format_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.1f}"


def main():
    endpoints = [
        Endpoint("auth_login", 12.0, 180.0),
        Endpoint("auth_refresh", 8.0, 80.0),
        Endpoint("auth_register", 5.0, 220.0),
        Endpoint("orders_create", 8.0, 250.0),
        Endpoint("orders_delete", 2.0, 150.0),
        Endpoint("orders_get", 20.0, 90.0),
        Endpoint("orders_list", 15.0, 120.0),
        Endpoint("products_create", 4.0, 180.0),
        Endpoint("products_delete", 2.0, 140.0),
        Endpoint("products_get", 45.0, 35.0),
        Endpoint("products_list", 60.0, 40.0),
        Endpoint("products_update", 3.0, 160.0),
        Endpoint("users_delete", 2.0, 140.0),
        Endpoint("users_get", 18.0, 80.0),
        Endpoint("users_list", 10.0, 110.0),
        Endpoint("users_orders", 10.0, 180.0),
        Endpoint("users_update", 3.0, 160.0),
    ]

    sorted_endpoints = sorted(endpoints, key=lambda endpoint: endpoint.name)
    total_rps = sum(endpoint.expected_rps for endpoint in sorted_endpoints)
    total_workers = sum(workers_needed(endpoint, HEADROOM) for endpoint in sorted_endpoints)

    endpoint_header = "\u042d\u043d\u0434\u043f\u043e\u0438\u043d\u0442"
    workers_header = "\u0412\u043e\u0440\u043a\u0435\u0440\u044b"
    total_rps_label = "\u0418\u0442\u043e\u0433\u043e RPS"
    total_workers_label = "\u0412\u043e\u0440\u043a\u0435\u0440\u043e\u0432 \u0432\u0441\u0435\u0433\u043e"
    tier_label = "\u0422\u0430\u0440\u0438\u0444 \u0445\u043e\u0441\u0442\u0438\u043d\u0433\u0430"

    print(f"Headroom: {HEADROOM}x")
    print(f"{endpoint_header:<20} {'RPS':>7} {'Avg ms':>8} {workers_header:>8}")
    print("-" * 47)

    for endpoint in sorted_endpoints:
        print(
            f"{endpoint.name:<20} "
            f"{format_number(endpoint.expected_rps):>7} "
            f"{format_number(endpoint.avg_ms):>8} "
            f"{workers_needed(endpoint, HEADROOM):>8}"
        )

    print(f"{total_rps_label}: {format_number(total_rps)}")
    print(f"{total_workers_label}: {total_workers}")
    print(f"{tier_label}: {tier(total_rps)}")


if __name__ == "__main__":
    main()
