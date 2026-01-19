import sys
import os

# Add src to python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from utils.config import load_config, validate_config
from utils.logger import setup_logger
from bots.send_execute_query_bot import SendQueryBot
from bots.send_download_query_bot import SendDownloadQueryBot

def main():
    logger = setup_logger()
    logger.info("Starting WITS Automation (Modular Version)")

    try:
        # 1. Load configuration
        config = load_config()
        validate_config(config)
        
        # 2. Run Bot
        if config['workflow']['execute_send_query']:
            bot = SendQueryBot(config)
            bot.run()
        elif config['workflow']['execute_send_download_query']:
            bot = SendDownloadQueryBot(config)
            bot.run()
        
    except Exception as e:
        logger.exception(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
