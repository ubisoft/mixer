import logging
import logging.handlers
import argparse


def init_logging(args):
    """
    Initialize root logger of an application.
    """
    log_numeric_level = getattr(logging, args.log_level.upper(), None)
    if not isinstance(log_numeric_level, int):
        raise ValueError(f"Invalid log level: {args.log_level}")

    formatter = logging.Formatter(fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s [%(pathname)s:%(lineno)d]")
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    logger = logging.getLogger()

    logger.addHandler(handler)
    logger.setLevel(log_numeric_level)

    if args.log_file:
        maxBytes = 1024 * 1000 * 512  # 512 MB
        backupCount = 1024 * 1000  # 1B backup files
        handler = logging.handlers.RotatingFileHandler(args.log_file, maxBytes=maxBytes, backupCount=backupCount)
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        logger.info(f"Logging to file {args.log_file}")


def add_logging_cli_args(parser: argparse.ArgumentParser):
    """
    Set CLI arguments for logger configuration.
    """
    parser.add_argument("--log-level", default="WARNING", help="Level of log to use by default.")
    parser.add_argument("--log-file", help="Path to log file.")
