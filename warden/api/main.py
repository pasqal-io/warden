import argparse

import uvicorn

from warden.api.app import create_app
from warden.lib.config import Config


def create_configured_app():
    config = Config()
    return create_app(config)


def main():
    parser = argparse.ArgumentParser(description="Run the Warden API server.")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development.",
    )
    args = parser.parse_args()

    config = Config()
    if args.reload:
        uvicorn.run(
            "warden.api.main:create_configured_app",
            host=config.api.host,
            port=config.api.port,
            reload=True,
            factory=True,
            log_config=config.logging,
        )
    else:
        app = create_app(config)
        uvicorn.run(
            app,
            host=config.api.host,
            port=config.api.port,
            log_config=config.logging,
        )


if __name__ == "__main__":
    main()
