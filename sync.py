
import os
import json
import ipaddress
import requests
import time
import random

SOURCE_URL = "https://raw.githubusercontent.com/Internet-Helper/GeoHideDNS/refs/heads/main/hosts/eu/hosts"

API = "https://api.nextdns.io"
KEY = os.environ["NEXTDNS_API_KEY"]
PROFILE = os.environ["NEXTDNS_PROFILE_ID"]

HEADERS = {
    "X-Api-Key": KEY,
    "Content-Type": "application/json"
}

BLOCKS = {
    "# Supercell",
    "# Google Gemini AI",
    "# ChatGPT (OpenAI) AI",
    "# Claude AI"
}




def request(method, url, **kwargs):
    for attempt in range(7):
        r = requests.request(
            method,
            url,
            headers=HEADERS,
            timeout=40,
            **kwargs
        )

        if r.status_code == 429:
            retry = r.headers.get("Retry-After")

            try:
                wait = float(retry) if retry else min(30 * (2 ** attempt), 600)
            except ValueError:
                wait = min(30 * (2 ** attempt), 600)

            wait += random.uniform(1, 5)

            print(
                f"NextDNS ограничил запросы. "
                f"Попытка {attempt + 1}/7. "
                f"Ожидание {wait:.0f} секунд."
            )

            if attempt == 6:
                r.raise_for_status()

            time.sleep(wait)
            continue

        if not r.ok:
            print("ОШИБКА NEXTDNS API:")
            print("HTTP:", r.status_code)
            print("Ответ:", r.text)
            r.raise_for_status()

        data = r.json()

        if data.get("errors"):
            raise RuntimeError(str(data["errors"]))

        return data

    raise RuntimeError("Превышено количество попыток NextDNS API")


def main():
    print("Скачиваю исходный hosts...")

    r = requests.get(SOURCE_URL, timeout=60)
    r.raise_for_status()

    selected = []
    current = None

    for line in r.text.splitlines():
        s = line.strip()

        if s.startswith("# "):
            current = s if s in BLOCKS else None

        if current:
            selected.append(line)

    if not selected:
        raise RuntimeError("Нужные блоки не найдены!")

    domains = {}

    for line in selected:
        s = line.strip()

        if not s or s.startswith("#"):
            continue

        parts = s.split()
        if len(parts) < 2:
            continue

        ip, domain = parts[0], parts[1]

        try:
            ipaddress.ip_address(ip)
        except ValueError:
            continue

        domains.setdefault(domain, ip)

    if not domains:
        raise RuntimeError("Домены не найдены!")

    if len(domains) > 500:
        raise RuntimeError("Превышен лимит 500 DNS Rewrites!")

    with open("hosts.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(selected) + "\n")

    endpoint = f"{API}/profiles/{PROFILE}/rewrites/"

    # Получаем существующие записи
    print("Получаю текущие записи NextDNS...")

    result = request("GET", endpoint)
    existing = result.get("data", [])

    try:
        with open("managed_domains.json", encoding="utf-8") as f:
            previous = set(json.load(f))
    except FileNotFoundError:
        previous = set()

    existing_by_name = {
        item["name"]: item for item in existing
        if "name" in item
    }

    # Удаляем только устаревшие записи,
    # ранее добавленные этим скриптом
    for domain in previous - set(domains):
        item = existing_by_name.get(domain)

        if item:
            request("DELETE", f"{endpoint}/{item['id']}")
            print("Удалён:", domain)

    # Создаём новые или изменяем старые записи
    for domain, ip in domains.items():
        item = existing_by_name.get(domain)

        if item and item.get("content") == ip:
            continue

        if item:
            request("DELETE", f"{endpoint}/{item['id']}")
            time.sleep(1.5)

        request(
            "POST",
            endpoint,
            json={
                "name": domain,
                "content": ip
            }
        )
        time.sleep(1.5)

        print("Добавлен:", domain, "->", ip)

    with open("managed_domains.json", "w", encoding="utf-8") as f:
        json.dump(sorted(domains), f, indent=2)

    print("Успешно! Доменов:", len(domains))


if __name__ == "__main__":
    main()
