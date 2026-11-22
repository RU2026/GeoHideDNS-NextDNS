
import os
import json
import ipaddress
import requests

SOURCE_URL = "https://raw.githubusercontent.com/Internet-Helper/GeoHideDNS/refs/heads/main/hosts/hosts"

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
    r = requests.request(
        method, url, headers=HEADERS,
        timeout=40, **kwargs
    )
    r.raise_for_status()
    data = r.json()

    if data.get("errors"):
        raise RuntimeError(str(data["errors"]))

    return data


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

    endpoint = f"{API}/profiles/{PROFILE}/rewrites"

    # Получаем существующие записи
    print("Получаю текущие записи NextDNS...")

    result = request("GET", endpoint + "?limit=500")
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

        request(
            "POST",
            endpoint,
            json={
                "name": domain,
                "content": ip
            }
        )

        print("Добавлен:", domain, "->", ip)

    with open("managed_domains.json", "w", encoding="utf-8") as f:
        json.dump(sorted(domains), f, indent=2)

    print("Успешно! Доменов:", len(domains))


if __name__ == "__main__":
    main()
