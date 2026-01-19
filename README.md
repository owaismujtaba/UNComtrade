# WITS Trade Data Automation

This project automates the process of navigating the World Bank's WITS website, selecting an existing trade query, and modifying its reporters.

## Features
- Modular design for easy maintenance.
- Robust login and navigation handling.
- Automatic handling of 'New Query' modals.
- Comprehensive logging and screenshots for verification.

## Prerequisites
- Python 3.8+
- Playwright

## Setup
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```
2. Update `config.yaml` with your WITS credentials and target query name.

## Running the Automation
Simply run the orchestrator:
```bash
python main.py
```

## Project Structure
- `main.py`: Entry point and orchestrator.
- `src/automation/`: Core logic modules (browser, login, navigation, reporter).
- `src/utils/`: Helper modules (config, logger).
- `config.yaml`: Externalized configuration.
- `wits_result.png` & `reporter_selection_result.png`: Generated screenshots.
