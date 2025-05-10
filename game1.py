import os
import signal

from rich.console import Console
from rich.table import Table
import questionary
import database
from redis_utils import redis_manager
import threading
import time
from typing import Dict

console = Console()


class Game1:
    def __init__(self, team: str):
        self.team = team
        self.terms = ["EBITDA", "Interest Rate", "Multiple", "Factor Score"]
        self.conn = database.get_connection()
        self.redis = redis_manager
        self.should_exit = threading.Event()
        self.needs_refresh = threading.Event()
        self.display_lock = threading.Lock()

    def all_terms_approved(self) -> bool:
        """Check if all terms have been approved by Team 2"""
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM game1_terms WHERE team2_status != 'OK'")
            return cur.fetchone()[0] == 0

    def get_term_data(self) -> Dict:
        """Fetch current term data from database"""
        with self.conn.cursor() as cur:
            cur.execute("SELECT term, team1_value, unit, team2_status FROM game1_terms")
            return {row[0]: {'value': row[1], 'unit': row[2], 'status': row[3]} for row in cur.fetchall()}

    def run(self):
        if self.team == "Team 1":
            self.team1_flow()
        else:
            self.team2_flow()

    def team1_flow(self):
        # Initial term input
        for term in self.terms:
            self.update_term(term)

        with self.redis.subscribe_to_channel("team2_updates") as pubsub:
            listener_thread = threading.Thread(
                target=self.listen_for_updates,
                args=(pubsub, "Team 2")
            )
            listener_thread.daemon = True
            listener_thread.start()

            try:
                self.display_outputs()  # Initial display

                while not self.should_exit.is_set():
                    if self.needs_refresh.is_set():
                        self.display_outputs()
                        self.needs_refresh.clear()

                    action = questionary.select(
                        "Select action:",
                        choices=[
                            {"name": "Edit a term", "value": "edit"},
                            {"name": "Refresh view", "value": "refresh"},
                            {"name": "Exit", "value": "exit"}
                        ]
                    ).ask()

                    if action == "exit":
                        self.should_exit.set()
                    elif action == "edit":
                        term = questionary.select("Select term to edit:", choices=self.terms).ask()
                        self.update_term(term)
                        self.redis.publish_update("team1_updates", term)
                        console.print(f"\n[bold yellow]Updated {term} - Team 2 notified[/bold yellow]")
                        time.sleep(1)
                        self.display_outputs()
                    elif action == "refresh":
                        self.display_outputs()

            finally:
                self.should_exit.set()
                listener_thread.join(timeout=1)

    def team2_flow(self):
        with self.redis.subscribe_to_channel("team1_updates") as pubsub:
            listener_thread = threading.Thread(
                target=self.listen_for_updates,
                args=(pubsub, "Team 1")
            )
            listener_thread.daemon = True
            listener_thread.start()

            try:
                self.display_outputs()  # Initial display

                while not self.all_terms_approved() and not self.should_exit.is_set():
                    if self.needs_refresh.is_set():
                        self.display_outputs()
                        self.needs_refresh.clear()

                    action = questionary.select(
                        "Select action:",
                        choices=[
                            {"name": "Approve/reject term", "value": "approve"},
                            {"name": "Refresh view", "value": "refresh"},
                            {"name": "Exit", "value": "exit"}
                        ]
                    ).ask()

                    if action == "exit":
                        self.should_exit.set()
                    elif action == "approve":
                        term = questionary.select("Select term:", choices=self.terms).ask()
                        status = questionary.select(
                            f"Status for {term}:",
                            choices=[
                                {"name": "Approve (OK)", "value": "OK"},
                                {"name": "Reject (TBD)", "value": "TBD"}
                            ]
                        ).ask()

                        with self.conn.cursor() as cur:
                            cur.execute("""
                                UPDATE game1_terms
                                SET team2_status = %s
                                WHERE term = %s
                            """, (status, term))
                            self.conn.commit()

                        self.redis.publish_update("team2_updates", term)
                        console.print(f"\n[bold green]{term} status updated to {status}[/bold green]")
                        time.sleep(1)
                        self.display_outputs()
                    elif action == "refresh":
                        self.display_outputs()

            finally:
                self.should_exit.set()
                listener_thread.join(timeout=1)
                if self.all_terms_approved():
                    console.print("\n[green]All terms approved![/green]")
                    self.display_final_output()


    def listen_for_updates(self, pubsub, team_name: str):
        """Listen for updates and handle all refresh logic"""
        try:
            for message in pubsub.listen():
                if self.should_exit.is_set():
                    break

                if message['type'] == 'message':
                    term = message['data']
                    if self.all_terms_approved():
                        with self.display_lock:
                            self.display_final_output()
                        break
                    else:
                        with self.display_lock:
                            console.print(f"\n[bold green]{team_name} updated {term}[/bold green]")
                            self.display_outputs()
                            # console.print("[i]Press Enter to continue...[/i]")
                        self.needs_refresh.set()

        except Exception as e:
            console.print(f"[red]Error in listener: {e}[/red]")
        finally:
            pubsub.unsubscribe()

    def update_term(self, term: str):
        """Update a term's value and reset status to TBD"""
        with self.conn.cursor() as cur:
            cur.execute("SELECT unit FROM game1_terms WHERE term = %s", (term,))
            unit = cur.fetchone()[0]

        value = questionary.text(
            f"Enter {term} ({unit}):",
            validate=lambda val: val.replace('.', '', 1).isdigit()
        ).ask()

        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE game1_terms
                SET team1_value = %s, team2_status = 'TBD', last_updated = NOW()
                WHERE term = %s
            """, (float(value), term))
            self.conn.commit()

    def display_outputs(self):
        """Display current terms and statuses"""
        console.clear()
        term_data = self.get_term_data()

        table = Table(title=f"{self.team} View")
        table.add_column("Term", style="cyan")
        table.add_column("Value", style="magenta")
        table.add_column("Unit")
        table.add_column("Status", justify="right")

        for term, data in term_data.items():
            status = '[green]OK[/green]' if data['status'] == 'OK' else '[red]TBD[/red]'
            table.add_row(
                term,
                str(data['value']),
                data['unit'],
                status
            )

        console.print(table)

        if not self.all_terms_approved():
            if self.team == "Team 2":
                console.print("\n[i]Select terms to approve/reject[/i]")

    def display_final_output(self):
        """Show final approved valuation"""
        console.clear()
        term_data = self.get_term_data()

        table = Table(title="🎉 Final Valuation 🎉")
        table.add_column("Term", style="cyan")
        table.add_column("Value", style="magenta")
        table.add_column("Unit")
        table.add_column("Status", style="green")

        for term, data in term_data.items():
            table.add_row(
                term,
                str(data['value']),
                data['unit'],
                "OK"
            )

        valuation = self.calculate_valuation(term_data)
        table.add_row("", "", "", "")
        table.add_row("[bold]Valuation[/bold]", f"[green]{valuation}[/green]", "", "")

        console.print(table)
        console.print("\n[green]Deal successfully negotiated![/green]")
        self.should_exit.set()
        # os.kill(os.getpid(), signal.SIGINT)  # Like Ctrl+C to exit program

    def calculate_valuation(self, term_data: Dict) -> str:
        """Calculate final valuation based on approved terms"""
        ebitda = term_data['EBITDA']['value']
        rate = term_data['Interest Rate']['value']
        multiple = term_data['Multiple']['value']
        factor = term_data['Factor Score']['value']

        valuation = ebitda * multiple * factor
        return f"${valuation:,.2f}"