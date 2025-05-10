from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm
import questionary
import database
from redis_utils import redis_manager
import threading
from typing import Dict

console = Console()


class Game1:
    def __init__(self, team: str):
        self.team = team
        self.terms = ["EBITDA", "Interest Rate", "Multiple", "Factor Score"]
        self.conn = database.get_connection()
        self.redis = redis_manager
        self.update_event = threading.Event()
        self.shutdown_event = threading.Event()

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

        # Start listening for Team 2 updates in background
        pubsub = self.redis.subscribe_to_channel("team2_updates")
        listener_thread = threading.Thread(target=self.listen_for_updates, args=(pubsub, "Team 2"))
        listener_thread.daemon = True
        listener_thread.start()

        try:
            while not self.all_terms_approved() and not self.shutdown_event.is_set():
                self.display_outputs()

                if self.update_event.is_set():
                    self.update_event.clear()
                    console.print("\n[bold green]Update received! Refreshing view...[/bold green]")
                    continue

                # Edit option
                if questionary.confirm("Do you want to edit any term?", default=False).ask():
                    term = questionary.select("Select term to edit:", choices=self.terms).ask()
                    self.update_term(term)
                    self.redis.publish_update("team1_updates", term)
                    console.print(f"\n[bold yellow]Updated {term} - Team 2 notified[/bold yellow]")
        finally:
            self.shutdown_event.set()
            pubsub.unsubscribe("team2_updates")
            listener_thread.join(timeout=1)

        if self.all_terms_approved():
            console.print("\n[green]All terms approved![/green]")
            self.display_final_output()

    def team2_flow(self):
        # Start listening for Team 1 updates in background
        pubsub = self.redis.subscribe_to_channel("team1_updates")
        listener_thread = threading.Thread(target=self.listen_for_updates, args=(pubsub, "Team 1"))
        listener_thread.daemon = True
        listener_thread.start()

        try:
            while not self.all_terms_approved() and not self.shutdown_event.is_set():
                self.display_outputs()

                if self.update_event.is_set():
                    self.update_event.clear()
                    continue

                # Approval interface
                term = questionary.select(
                    "Select term to approve/reject:",
                    choices=self.terms + ["Refresh", "Exit"],
                    default="Refresh"
                ).ask()

                if term == "Exit":
                    if questionary.confirm("Exit now? You can return later.", default=False).ask():
                        break
                    continue
                elif term == "Refresh":
                    continue

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
        finally:
            self.shutdown_event.set()
            pubsub.unsubscribe("team1_updates")
            listener_thread.join(timeout=1)

        if self.all_terms_approved():
            console.print("\n[green]All terms approved![/green]")
            self.display_final_output()

    def listen_for_updates(self, pubsub, team_name: str):
        """Listen for updates in background thread"""
        try:
            for message in pubsub.listen():
                if self.shutdown_event.is_set():
                    break
                if message['type'] == 'message':
                    term = message['data']  # Using data directly without decode
                    console.print(f"\n[bold]Update from {team_name}: {term}[/bold]")
                    self.update_event.set()
        except Exception as e:
            console.print(f"[red]Error in listener thread: {e}[/red]")

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

        if self.team == "Team 1":
            if not self.all_terms_approved():
                console.print("\n[blue]Waiting for Team 2 approvals...[/blue]")
            else:
                console.print("\n[green]All terms approved![/green]")
        else:
            console.print("\n[dim]Select term to approve/reject or 'Exit' to pause[/dim]")

    def display_final_output(self):
        """Show final approved valuation"""
        console.clear()
        term_data = self.get_term_data()

        table = Table(title="🎉 Final Approved Valuation 🎉")
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

    def calculate_valuation(self, term_data: Dict) -> str:
        """Calculate final valuation based on approved terms"""
        if not self.all_terms_approved():
            return "Pending approvals"

        ebitda = term_data['EBITDA']['value']
        rate = term_data['Interest Rate']['value']
        multiple = term_data['Multiple']['value']
        factor = term_data['Factor Score']['value']

        # Sample valuation calculation
        valuation = ebitda * multiple * factor / (1 + rate)
        return f"${valuation:,.2f}"