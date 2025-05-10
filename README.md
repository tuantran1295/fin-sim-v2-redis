# Simulation Games CLI

A command-line program that replicates two financial simulation games with real-time updates between teams using Redis and PostgreSQL.

## Project Structure

```
simulation-games/
├── main.py              # Main entry point with game selection
├── database.py          # PostgreSQL connection and initialization
├── redis_utils.py       # Redis connection and pub/sub helpers
├── game1.py             # Implementation of Simulation Game 1
├── game2.py             # Implementation of Simulation Game 2
├── requirements.txt     # Python dependencies
├── .env                 # Environment variables (not committed)
└── README.md            # Project documentation
```

## Installation Instructions

1. **Prerequisites**:
   - Python 3.8+
   - PostgreSQL (running locally or accessible)
   - Redis server (running locally or accessible)

2. **Set up environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Database setup**:
   - Create a PostgreSQL database
   - Update `.env` file with your credentials:
     ```
     DB_NAME=simulation_games
     DB_USER=your_username
     DB_PASSWORD=your_password
     DB_HOST=localhost
     REDIS_HOST=localhost
     REDIS_PORT=6379
     REDIS_PASSWORD=
     ```

## How to Run the Project

1. **Initialize the database** (first time only):
   ```bash
   python -c "import database; database.init_db()"
   ```

2. **Run the application**:
   ```bash
   python main.py
   ```

3. **Game instructions**:
   - For Game 1:
     - Team 1 enters term values
     - Team 2 approves/rejects terms
     - Both teams see updates in real-time
   - For Game 2:
     - Team 1 enters company pricing and shares first
     - Team 2 enters share bids after Team 1 completes
     - Both teams see final results

4. **Running multiple teams**:
   Open two terminal windows:
   - In first terminal: `python main.py` → Select Game → Select Team 1
   - In second terminal: `python main.py` → Select same Game → Select Team 2

## Features

- Real-time updates between teams using Redis pub/sub
- Data persistence with PostgreSQL
- Interactive CLI interface with questionary
- Formatted output with rich
- Complete implementation of both simulation games with all financial formulas