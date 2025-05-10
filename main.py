import questionary
from rich.console import Console
from rich.table import Table
import database
import redis_utils
from game1 import Game1
from game2 import Game2

console = Console()


def main():
    database.init_db()

    choice = questionary.select(
        "Select simulation game:",
        choices=["Game 1: Terms Valuation", "Game 2: Share Bidding", "Exit"]
    ).ask()

    if choice == "Exit":
        return

    team = questionary.select(
        "Select your team:",
        choices=["Team 1", "Team 2"]
    ).ask()

    if choice == "Game 1: Terms Valuation":
        game = Game1(team)
    else:
        game = Game2(team)

    game.run()


if __name__ == "__main__":
    main()