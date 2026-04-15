import time
import socket
import requests


def diagnose_page_loading(url_address):
    results = {}

    try:
        hostname = url_address.split('/')[2].split(':')[0]
        start = time.time()
        ip = socket.gethostbyname(hostname)
        print(f'Hostname: {hostname}, IP: {ip}')
        dns_time = time.time() - start
        results['dns'] = dns_time
    except Exception as e:
        results['dns'] = f"Ошибка: {e}"

    try:
        start = time.time()
        response = requests.get(url_address)
        total_time = time.time() - start
        results['total'] = total_time
        results['server'] = response.elapsed.total_seconds()
        results['status'] = response.status_code
        results['size'] = len(response.content)
    except Exception as e:
        results['error'] = str(e)

    return results


if __name__ == "__main__":
    url = "http://localhost:8000/products"
    results = diagnose_page_loading(url)
    print("Результаты измерения производительности:")
    for key, value in results.items():
        print(f"{key}: {value}")
