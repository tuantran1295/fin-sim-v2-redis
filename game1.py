from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm, Prompt
import questionary
import database
from redis_utils import redis_manager
import time
from typing import Dict, List

console = Console()


class Game1:
    def __init__(self, team: str):
        self.team = team
        self.terms = ["EBITDA", "Interest Rate", "Multiple", "Factor Score"]
        self.conn = database.get_connection()
        self.redis = redis_manager

    def run(self):
        if self.team == "Team 1":
            self.team1_flow()
        else:
            self.team2_flow()

    def team1_flow(self):
        # Initial input collection
        for term in self.terms:
            self.update_term(term)

        # Show initial outputs
        self.display_outputs()

        # Edit loop
        while True:
            if questionary.confirm("Do you want to edit any term?", default=False).ask():
                term = questionary.select(
                    "Select term to edit:",
                    choices=self.terms
                ).ask()
                self.update_term(term)
                self.redis.publish_update("team1_update", f"{term}_updated")
                self.display_outputs()
            else:
                break

        # Wait for all terms to be approved
        while not self.all_terms_approved():
            console.print("[yellow]Waiting for Team 2 to approve all terms...[/yellow]")
            time.sleep(3)
            self.display_outputs()

        console.print("[green]All terms have been approved![/green]")
        self.display_final_output()

    def team2_flow(self):
        # FIXED: Changed from subscribe() to subscribe_to_channel()
        pubsub = self.redis.subscribe_to_channel("team1_update")

        try:
            # Initial display
            self.display_outputs()

            while not self.all_terms_approved():
                # Check for updates
                message = pubsub.get_message(timeout=1)
                if message and message['type'] == 'message':
                    self.display_outputs()

                term = questionary.select(
                    "Select term to approve/reject:",
                    choices=self.terms + ["Exit"]
                ).ask()

                if term == "Exit":
                    if Confirm.ask("Do you want to exit? The game will continue when all terms are approved."):
                        break
                    continue

                self.update_status(term)
                self.redis.publish_update("team2_update", f"{term}_status_changed")
                self.display_outputs()

            if self.all_terms_approved():
                console.print("[green]You have approved all terms![/green]")
                self.display_final_output()

        finally:
            # FIXED: Changed from unsubscribe() to unsubscribe() method on pubsub
            pubsub.unsubscribe("team1_update")

    def update_term(self, term: str):
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT unit FROM game1_terms WHERE term = %s",
                (term,)
            )
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

    def update_status(self, term: str):
        status = questionary.select(
            f"Approve or reject {term}?",
            choices=[
                "Approve (OK)",
                "Reject (TBD)"
            ]
        ).ask()

        status_code = "OK" if status.startswith("Approve") else "TBD"

        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE game1_terms
                SET team2_status = %s
                WHERE term = %s
            """, (status_code, term))
            self.conn.commit()

    def get_term_data(self) -> Dict:
        with self.conn.cursor() as cur:
            cur.execute("SELECT term, team1_value, unit, team2_status FROM game1_terms")
            return {row[0]: {'value': row[1], 'unit': row[2], 'status': row[3]} for row in cur.fetchall()}

    def all_terms_approved(self) -> bool:
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM game1_terms WHERE team2_status != 'OK'")
            return cur.fetchone()[0] == 0

    def calculate_valuation(self, term_data: Dict) -> str:
        if all(term['status'] == 'OK' for term in term_data.values()):
            ebitda = term_data['EBITDA']['value']
            multiple = term_data['Multiple']['value']
            factor = term_data['Factor Score']['value']
            return f"${ebitda * multiple * factor:,.2f}"
        return "Not yet agreed by Team 2"

    def display_outputs(self):
        term_data = self.get_term_data()

        if self.team == "Team 1":
            self.display_team1_output(term_data)
        else:
            self.display_team2_output(term_data)

    def display_team1_output(self, term_data: Dict):
        table = Table(title="Your Outputs (Team 1)")
        table.add_column("Term", style="cyan")
        table.add_column("Your Value", style="magenta")
        table.add_column("Team 2 Status", style="green")

        for term, data in term_data.items():
            status = "[green]OK[/green]" if data['status'] == 'OK' else "[red]TBD[/red]"
            table.add_row(
                term,
                f"{data['value']} {data['unit']}",
                status
            )

        console.print(table)

        # Show valuation
        valuation = self.calculate_valuation(term_data)
        console.print(f"\n[bold]Valuation:[/bold] {valuation}\n")

    def display_team2_output(self, term_data: Dict):
        table = Table(title="Your Outputs (Team 2)")
        table.add_column("Term", style="cyan")
        table.add_column("Team 1 Value", style="magenta")
        table.add_column("Unit")
        table.add_column("Your Status", style="green")

        for term, data in term_data.items():
            status = "[green]OK[/green]" if data['status'] == 'OK' else "[red]TBD[/red]"
            table.add_row(
                term,
                str(data['value']),
                data['unit'],
                status
            )

        console.print(table)

        # Show valuation
        valuation = self.calculate_valuation(term_data)
        console.print(f"\n[bold]Valuation:[/bold] {valuation}\n")

    def display_final_output(self):
        term_data = self.get_term_data()
        table = Table(title="Final Valuation")
        table.add_column("Term")
        table.add_column("Value")
        table.add_column("Unit")

        for term, data in term_data.items():
            table.add_row(
                term,
                str(data['value']),
                data['unit']
            )

        valuation = self.calculate_valuation(term_data)
        table.add_row("Final Valuation", valuation, "")

        console.print(table)