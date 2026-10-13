#!/usr/bin/env python3
"""Замер скорости скачивания по десяти последовательным HTTP-запросам."""

import argparse
import math
import sys
from http.client import HTTPException
from time import perf_counter
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


REQUEST_COUNT = 10
CHUNK_SIZE = 64 * 1024
DEFAULT_URL = "https://bom.proof.ovh.net/files/10Mb.dat"


def positive_timeout(value: str) -> float:
    timeout = float(value)
    if not math.isfinite(timeout) or timeout <= 0:
        raise argparse.ArgumentTypeError("таймаут должен быть положительным конечным числом")
    return timeout


def download(url: str, timeout: float) -> tuple[int, float]:
    request = Request(
        url,
        headers={"Accept-Encoding": "identity", "Cache-Control": "no-cache"},
    )
    downloaded_bytes = 0
    started_at = perf_counter()
    with urlopen(request, timeout=timeout) as response:
        expected_size = response.headers.get("Content-Length")
        while chunk := response.read(CHUNK_SIZE):
            downloaded_bytes += len(chunk)
        if expected_size is not None and downloaded_bytes != int(expected_size):
            raise ValueError("ответ получен не полностью (размер отличается от Content-Length)")
    return downloaded_bytes, perf_counter() - started_at


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "url",
        nargs="?",
        default=DEFAULT_URL,
        help="HTTP(S)-адрес файла (по умолчанию: тестовый файл OVH на 10 МиБ)",
    )
    parser.add_argument(
        "--timeout",
        type=positive_timeout,
        default=30.0,
        help="таймаут сетевой операции в секундах (по умолчанию: 30)",
    )
    args = parser.parse_args()
    address = urlsplit(args.url)
    if address.scheme not in ("http", "https") or not address.netloc:
        parser.error("укажите HTTP(S)-адрес файла")

    total_bytes = 0
    total_seconds = 0.0
    for number in range(1, REQUEST_COUNT + 1):
        try:
            downloaded_bytes, elapsed = download(args.url, args.timeout)
        except (URLError, OSError, HTTPException, ValueError) as error:
            print(f"Ошибка запроса {number}/{REQUEST_COUNT}: {error}", file=sys.stderr)
            return 1
        total_bytes += downloaded_bytes
        total_seconds += elapsed
        print(f"Запрос {number}/{REQUEST_COUNT}: {downloaded_bytes} байт, {elapsed:.6f} с")

    speed_mbps = total_bytes * 8 / total_seconds / 1_000_000
    print(f"\nВсего скачано: {total_bytes} байт ({total_bytes / 1_000_000:.2f} МБ)")
    print(f"Суммарное время: {total_seconds:.6f} с")
    print(f"Среднее время: {total_seconds / REQUEST_COUNT:.6f} с")
    print(f"Скорость: {speed_mbps:.2f} Мбит/с")
    return 0


if __name__ == "__main__":
    sys.exit(main())
