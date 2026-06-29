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


def refresh_dataset(*, generate_report: bool = True, report_use_llm: bool = False) -> bool:
    """Fetch fresh data.json from ENDPOINT and optionally regenerate report.html."""
    if not config.ENDPOINT:
        filelogger.logger.error("ENDPOINT is not set in .env")
        return dataset_is_ready()

    filelogger.logger.info("Refreshing data.json from ENDPOINT")
    if not fetch_data():
        filelogger.logger.error("Failed to fetch fresh data from ENDPOINT")
        return False

    if generate_report:
        try:
            report_path = deepseek.analyze(use_llm=report_use_llm)
            filelogger.logger.info(f"Report written to {report_path.resolve()}")
        except Exception as e:
            filelogger.logger.error(f"Report generation failed: {e}")
            return False

    return True


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
            deepseek.analyze(use_llm=True)
        except Exception as e:
            filelogger.logger.error(f"Report generation failed: {e}")

    return True


def run_pipeline() -> bool:
    return refresh_dataset(generate_report=True, report_use_llm=True)


def main() -> None:
    success = run_pipeline()
    if not success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
