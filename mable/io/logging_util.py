import logging

from loguru import logger


class LoguruHandler(logging.Handler):
    """
    Handler to forward python logging to loguru logger.
    """
    def emit(self, record):
        log_entry = self.format(record)
        loguru_level = {
            'DEBUG': 'DEBUG',
            'INFO': 'INFO',
            'WARNING': 'WARNING',
            'ERROR': 'ERROR',
            'CRITICAL': 'CRITICAL'
        }.get(record.levelname, 'DEBUG')
        logger.log(loguru_level, log_entry)


def let_loguru_handle_logging(level=logging.INFO):
    """
    Set up python logging to forward to loguru logger.
    """
    loguru_handler = LoguruHandler()
    logging.basicConfig(handlers=[loguru_handler], level=level,
                        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
