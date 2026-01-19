import sys
import os

# Add src to python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from utils.config import load_config, validate_config
from utils.logger import setup_logger
from bots.send_query_bot import SendQueryBot

def main():
    logger = setup_logger()
    logger.info("Starting WITS Automation (Modular Version)")

    try:
        # 1. Load configuration
        config = load_config()
        validate_config(config)
        
        # 2. Run Bot
        bot = SendQueryBot(config)
        bot.run()
        
    except Exception as e:
        logger.exception(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
