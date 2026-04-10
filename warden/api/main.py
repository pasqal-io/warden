import argparse
from copy import deepcopy

import uvicorn

from warden.api.app import create_app
from warden.lib.config import Config


def create_configured_app():
    config = Config()
    return create_app(config)


def build_api_log_config(config: Config) -> dict:
    log_config = deepcopy(config.logging)
    loggers = log_config.setdefault("loggers", {})
    root_handlers = log_config.get("root", {}).get("handlers", [])
    warden_logger = loggers.get("warden", {})

    shared_handlers = list(warden_logger.get("handlers") or root_handlers)
    shared_level = warden_logger.get("level", "INFO")

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger_config = loggers.get(logger_name, {})
        logger_config["handlers"] = shared_handlers
        logger_config["level"] = logger_config.get("level", shared_level)
        logger_config["propagate"] = False
        loggers[logger_name] = logger_config

    return log_config


def main():
    parser = argparse.ArgumentParser(description="Run the Warden API server.")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development.",
    )
    args = parser.parse_args()

    config = Config()
    log_config = build_api_log_config(config)
    if args.reload:
        uvicorn.run(
            "warden.api.main:create_configured_app",
            host=config.api.host,
            port=config.api.port,
            reload=True,
            factory=True,
            log_config=log_config,
        )
    else:
        app = create_app(config)
        uvicorn.run(
            app,
            host=config.api.host,
            port=config.api.port,
            log_config=log_config,
        )


if __name__ == "__main__":
    main()
