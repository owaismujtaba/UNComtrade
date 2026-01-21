import sys
import os

# Add src to python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from utils.config import load_config, validate_config
from utils.logger import setup_logger
from bots.send_execute_query_bot import SendQueryBot
from bots.send_download_query_bot import SendDownloadQueryBot
from bots.manage_suspended_queries_bot import ManageSuspendedQueriesBot
from bots.delete_queries_bot import DeleteQueriesBot
from bots.reprocess_suspended_bot import ReprocessSuspendedBot

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
        elif config['workflow'].get('execute_manage_suspended_queries'):
            bot = ManageSuspendedQueriesBot(config)
            bot.run()
        elif config['workflow'].get('execute_delete_queries'):
            bot = DeleteQueriesBot(config)
            bot.run()
        elif config['workflow'].get('execute_reprocess_suspended'):
            bot = ReprocessSuspendedBot(config)
            bot.run()
        else:
            logger.warning("No workflow selected in config.yaml. Please set one of the execute_* flags to true.")
        
    except Exception as e:
        logger.exception(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
