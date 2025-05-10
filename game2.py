import questionary
from rich.console import Console
from rich.table import Table
from typing import Dict, List, Union
import database
import redis_utils
from time import sleep
import psycopg2

console = Console()


class Game2:
    def __init__(self, team: str):
        self.team = team
        self.companies = [1, 2, 3]
        self.investors = [1, 2, 3]
        self.conn = database.get_connection()
        self.console = Console()

    def run(self):
        if self.team == "Team 1":
            self.team1_flow()
        else:
            self.team2_flow()

    def team1_flow(self):
        """Handle Team 1's input flow"""
        self.console.print("[bold]Team 1: Enter Pricing Information[/bold]")
        self.input_pricing()
        redis_utils.publish_update("team1_completed", "ready_for_team2")

        # Wait for Team 2 to complete
        pubsub = redis_utils.subscribe_to_channel("team2_completed")
        self.console.print("Waiting for Team 2 to complete their inputs...")

        while True:
            message = pubsub.get_message()
            if message and message['data'] == b"done":
                break
            sleep(1)

        self.display_results()

    def team2_flow(self):
        """Handle Team 2's input flow"""
        # Wait for Team 1 to finish
        pubsub = redis_utils.subscribe_to_channel("team1_completed")
        self.console.print("Waiting for Team 1 to complete their inputs...")

        while True:
            message = pubsub.get_message()
            if message and message['data'] == b"ready_for_team2":
                break
            sleep(1)

        self.console.print("[bold]Team 2: Enter Share Bids[/bold]")
        self.input_bids()
        redis_utils.publish_update("team2_completed", "done")
        self.display_results()

    def input_pricing(self):
        """Collect pricing and shares for each company from Team 1"""
        for company in self.companies:
            price = questionary.text(
                f"Enter price for Company {company}:",
                validate=lambda x: x.replace('.', '', 1).isdigit()
            ).ask()

            shares = questionary.text(
                f"Enter shares available for Company {company}:",
                validate=lambda x: x.isdigit()
            ).ask()

            self.save_pricing(company, float(price), int(shares))

    def input_bids(self):
        """Collect share bids from each investor for each company (Team 2)"""
        for investor in self.investors:
            self.console.print(f"\n[bold]Investor {investor}:[/bold]")
            for company in self.companies:
                bid = questionary.text(
                    f"Enter shares bid for Company {company}:",
                    validate=lambda x: x.isdigit()
                ).ask()
                self.save_bid(investor, company, int(bid))

    def save_pricing(self, company: int, price: float, shares: int):
        """Save Team 1's pricing input to database"""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO game2_pricing (company, price, shares, team_id)
                VALUES (%s, %s, %s, 1)
                ON CONFLICT (company, team_id) 
                DO UPDATE SET price = %s, shares = %s
            """, (company, price, shares, price, shares))
            self.conn.commit()

    def save_bid(self, investor: int, company: int, shares_bid: int):
        """Save Team 2's bid input to database"""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO game2_bids (investor, company, shares_bid, team_id)
                VALUES (%s, %s, %s, 2)
                ON CONFLICT (investor, company, team_id) 
                DO UPDATE SET shares_bid = %s
            """, (investor, company, shares_bid, shares_bid))
            self.conn.commit()

    def calculate_results(self) -> Dict[str, Dict[int, Union[float, str]]]:
        """Calculate all game results"""
        return {
            "shares_bid": self.calculate_shares_bid(),
            "capital_raised": self.calculate_capital_raised(),
            "subscription": self.determine_subscription(),
            "most_bids": self.find_most_bids_company()
        }

    def calculate_shares_bid(self) -> Dict[int, float]:
        """Sum all bids for each company"""
        shares_bid = {}
        with self.conn.cursor() as cur:
            for company in self.companies:
                cur.execute("""
                    SELECT SUM(shares_bid) FROM game2_bids 
                    WHERE company = %s AND team_id = 2
                """, (company,))
                shares_bid[company] = cur.fetchone()[0] or 0
        return shares_bid

    def calculate_capital_raised(self) -> Dict[int, Union[float, str]]:
        """Calculate capital raised for each company"""
        capital_raised = {}
        shares_bid = self.calculate_shares_bid()

        with self.conn.cursor() as cur:
            for company in self.companies:
                cur.execute("""
                    SELECT price, shares FROM game2_pricing
                    WHERE company = %s AND team_id = 1
                """, (company,))
                price, available_shares = cur.fetchone()

                if shares_bid[company] <= available_shares:
                    capital_raised[company] = shares_bid[company] * price
                else:
                    capital_raised[company] = "Allocate"

        return capital_raised

    def determine_subscription(self) -> Dict[int, str]:
        """Determine subscription status for each company"""
        subscription = {}
        shares_bid = self.calculate_shares_bid()

        with self.conn.cursor() as cur:
            for company in self.companies:
                cur.execute("""
                    SELECT shares FROM game2_pricing
                    WHERE company = %s AND team_id = 1
                """, (company,))
                available_shares = cur.fetchone()[0]

                if shares_bid[company] == available_shares:
                    subscription[company] = "Filled"
                elif shares_bid[company] < available_shares:
                    subscription[company] = "Under"
                else:
                    subscription[company] = "Over"

        return subscription

    def find_most_bids_company(self) -> int:
        """Identify which company received the most bids"""
        shares_bid = self.calculate_shares_bid()
        return max(shares_bid.items(), key=lambda x: x[1])[0]

    def display_results(self):
        """Display results in a formatted table"""
        results = self.calculate_results()
        most_bids = self.find_most_bids_company()

        # Create summary table
        summary_table = Table(title="Common Outputs Shown to Both Teams", show_header=True)
        summary_table.add_column("Metric", style="cyan")
        for company in self.companies:
            summary_table.add_column(f"Company {company}", justify="right")

        # Add shares bid row
        shares_row = ["Shares Bid For"]
        shares_row.extend([str(results["shares_bid"][c]) for c in self.companies])
        summary_table.add_row(*shares_row)

        # Add capital raised row
        capital_row = ["Capital Raised"]
        capital_row.extend([
            str(results["capital_raised"][c]) for c in self.companies
        ])
        summary_table.add_row(*capital_row)

        # Add subscription row
        sub_row = ["Subscription"]
        sub_row.extend(results["subscription"][c] for c in self.companies)
        summary_table.add_row(*sub_row)

        self.console.print(summary_table)

        # Display most bids
        self.console.print(
            f"\nWhich company received the most bids from investors?",
            style="bold"
        )
        self.console.print(
            f"→ Company {most_bids}",
            style="bold green"
        )