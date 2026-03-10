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

    if settings.webhook_url:
        log.info("Starting in webhook mode: %s", settings.webhook_url)
        application.run_webhook(
            listen="0.0.0.0",
            port=8443,
            webhook_url=settings.webhook_url,
        )
    else:
        log.info("Starting in polling mode")
        application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
