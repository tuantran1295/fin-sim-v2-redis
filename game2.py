import questionary
from rich.console import Console
from rich.table import Table
from typing import Dict, List, Union
import database
from redis_utils import redis_manager
import threading
import time
import psycopg2

console = Console()


class Game2:
    def __init__(self, team: str):
        self.team = team
        self.companies = [1, 2, 3]
        self.investors = [1, 2, 3]
        self.conn = database.get_connection()
        self.console = Console()
        self.redis = redis_manager
        self.should_exit = threading.Event()
        self.needs_refresh = threading.Event()
        self.display_lock = threading.Lock()
        self.team_1_done_input = False
        self.team_2_done_input = False

    def run(self):
        if self.team == "Team 1":
            self.team1_flow()
        else:
            self.team2_flow()

    def team1_flow(self):
        """Handle Team 1's input flow with real-time updates"""
        self.console.print("[bold]Team 1: Enter Pricing Information[/bold]")
        self.input_pricing()

        # Start listener for Team 2 completion
        with self.redis.subscribe_to_channel("team2_completed") as pubsub:
            listener_thread = threading.Thread(
                target=self.listen_for_updates,
                args=(pubsub, "Team 2")
            )
            listener_thread.daemon = True
            listener_thread.start()

            try:
                # Notify Team 2
                self.redis.publish_update("team1_completed", "ready_for_team2")
                self.console.print("\n[bold yellow]Waiting for Team 2 to complete their inputs...[/bold yellow]")

                while not self.team_2_done_input and not self.should_exit.is_set():
                    if self.needs_refresh.is_set():
                        self.needs_refresh.clear()
                        self.console.print("\nStill waiting for Team 2...", style="italic")

                    time.sleep(0.5)  # Reduce CPU usage

                if not self.should_exit.is_set():
                    self.display_results()
            finally:
                self.should_exit.set()
                listener_thread.join(timeout=1)

    def team2_flow(self):
        """Handle Team 2's input flow with real-time updates"""
        self.console.print("\n[bold yellow]Waiting for Team 1 to complete their inputs...[/bold yellow]")
        # Start listener for Team 1 completion
        with self.redis.subscribe_to_channel("team1_completed") as pubsub:
            listener_thread = threading.Thread(
                target=self.listen_for_updates,
                args=(pubsub, "Team 1")
            )
            listener_thread.daemon = True
            listener_thread.start()

            try:
                while not self.team_1_done_input:
                    # if self.needs_refresh.is_set():
                    #     self.needs_refresh.clear()
                    #     self.console.print("\nTeam 1 ready - enter your bids:", style="bold green")
                    #     self.input_bids()
                    #     self.redis.publish_update("team2_completed", "done")
                    #     self.display_results()
                    #     self.team_2_done_input = True

                    time.sleep(0.5)

            finally:
                self.should_exit.set()
                listener_thread.join(timeout=1)

    def listen_for_updates(self, pubsub, team_name: str):
        """Listen for updates from the other team"""
        try:
            for message in pubsub.listen():
                # console.print(f"Received Message: {message}")

                if self.should_exit.is_set():
                    break

                if message['type'] == 'message':
                    if message['channel'] == "team1_completed" and message['data']:
                        self.console.print("\nTeam 1 ready - enter your bids:", style="bold green")
                        self.input_bids()
                        self.redis.publish_update("team2_completed", "done")
                        self.display_results()
                        self.team_2_done_input = True
                    elif message['channel'] == "team2_completed" and message['data']:
                        self.team_2_done_input = True
                        self.needs_refresh.set()

        except Exception as e:
            self.console.print(f"[red]Error in listener: {e}[/red]")

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
        with self.display_lock:
            results = self.calculate_results()
            most_bids = self.find_most_bids_company()

            self.console.clear()
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
            self.console.print(
                f"\nWhich company received the most bids from investors?",
                style="bold"
            )
            self.console.print(
                f"→ Company {most_bids}",
                style="bold green"
            )
            self.console.print("\n[green]All teams have completed![/green]")