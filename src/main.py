import json
from pathlib import Path

import requests

import config
import deepseek
import filelogger


def fetch_data(data_path: Path | None = None) -> bool:
    """Fetch JSON from the configured endpoint and save to data.json."""
    data_path = data_path or config.DATA_PATH

    if not config.ENDPOINT:
        filelogger.logger.error("ENDPOINT is not set in .env")
        return False

    headers = {}
    if config.API_KEY:
        headers["apikey"] = config.API_KEY

    proxies = config.parse_proxy(config.PROXY)

    try:
        filelogger.logger.info(
            f"Sending GET request to {config.ENDPOINT} "
            f"(verify_ssl={config.VERIFY_SSL})"
        )
        response = requests.get(
            config.ENDPOINT,
            headers=headers,
            proxies=proxies,
            timeout=60,
            verify=config.VERIFY_SSL,
        )
        response.raise_for_status()

        data_path.parent.mkdir(parents=True, exist_ok=True)
        data_path.write_text(response.text, encoding="utf-8")
        filelogger.logger.info(f"Saved response to {data_path}")
        return True

    except requests.exceptions.RequestException as e:
        filelogger.logger.error(f"Request failed: {e}")
        return False
    except Exception as e:
        filelogger.logger.error(f"Unexpected error: {e}")
        return False


def dataset_is_ready(data_path: Path | None = None) -> bool:
    data_path = data_path or config.DATA_PATH
    if not data_path.exists():
        return False
    try:
        rows = json.loads(data_path.read_text(encoding="utf-8"))
        return isinstance(rows, list) and bool(rows)
    except (json.JSONDecodeError, ValueError):
        return False


def ensure_dataset(*, generate_report: bool = True) -> bool:
    """Load data.json from ENDPOINT when the file is missing or empty."""
    if dataset_is_ready():
        rows = json.loads(config.DATA_PATH.read_text(encoding="utf-8"))
        filelogger.logger.info(
            f"Using existing {config.DATA_PATH.name} ({len(rows)} records)"
        )
        return True

    if not config.ENDPOINT:
        filelogger.logger.warning(
            f"{config.DATA_PATH.name} missing and ENDPOINT is not set in .env"
        )
        return False

    filelogger.logger.info(
        f"{config.DATA_PATH.name} missing or empty; fetching from ENDPOINT"
    )
    if not fetch_data():
        filelogger.logger.error("Failed to fetch dataset on startup")
        return False

    if generate_report:
        try:
            deepseek.analyze()
        except Exception as e:
            filelogger.logger.error(f"Report generation failed: {e}")

    return True


def run_pipeline() -> bool:
    if not fetch_data():
        return False

    try:
        deepseek.analyze()
        return True
    except Exception as e:
        filelogger.logger.error(f"Analysis failed: {e}")
        return False


def main() -> None:
    success = run_pipeline()
    if not success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
