import logging
import sys

from feelinq.config import settings


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )
    log = logging.getLogger(__name__)

    from feelinq.platforms.telegram.bot import build_application

    application = build_application()

    log.info("Starting in polling mode")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
