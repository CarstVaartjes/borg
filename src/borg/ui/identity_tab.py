"""Identity tab — manage author identity groups and manual aliases."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Input, Static

from borg.db import Database


class IdentityTab(Static):
    """Author identity management — view groups, add manual aliases."""

    def __init__(self, db: Database) -> None:
        super().__init__()
        self.db = db

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Author Identity Groups", id="identity-title")
            yield Static(
                "Auto-resolved by shared names/emails. "
                "Add manual aliases below to merge remaining groups.",
                id="identity-help",
            )
            yield DataTable(id="identity-table")
            yield Static("")
            yield Static("Manual Alias")
            with Horizontal(id="alias-form"):
                yield Input(placeholder="email", id="alias-email-input")
                yield Input(placeholder="canonical name", id="alias-name-input")
                yield Button("Set Alias", id="set-alias-btn", variant="primary")
            with Horizontal(id="alias-actions"):
                yield Button("Remove Alias", id="remove-alias-btn", variant="error")
                yield Button("Refresh Identities", id="refresh-btn", variant="default")
            yield Static("", id="identity-result")

    def on_mount(self) -> None:
        table = self.query_one("#identity-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Author", "Emails", "Manual")
        self._refresh_table()

    def refresh_data(self, org: str | None = None) -> None:
        self._refresh_table()

    def _refresh_table(self) -> None:
        table = self.query_one("#identity-table", DataTable)
        table.clear()

        groups = self.db.get_identity_groups()
        manual_aliases = {a["email"]: a["canonical_name"] for a in self.db.get_author_aliases()}

        for group in groups:
            name = group["canonical_name"]
            emails = group["emails"]
            # Mark which emails have manual aliases
            email_display = []
            has_manual = False
            for e in emails:
                if e in manual_aliases:
                    email_display.append(f"{e} *")
                    has_manual = True
                else:
                    email_display.append(e)

            table.add_row(
                name,
                ", ".join(email_display),
                "yes" if has_manual else "",
                key=name,
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "set-alias-btn":
            self._set_alias()
        elif event.button.id == "remove-alias-btn":
            self._remove_alias()
        elif event.button.id == "refresh-btn":
            self._refresh_identities()

    def _set_alias(self) -> None:
        email_input = self.query_one("#alias-email-input", Input)
        name_input = self.query_one("#alias-name-input", Input)
        result = self.query_one("#identity-result", Static)

        email = email_input.value.strip()
        name = name_input.value.strip()

        if not email or not name:
            result.update("Both email and canonical name are required")
            return

        self.db.set_author_alias(email, name)
        self.db.rebuild_author_identities()
        result.update(f"Alias set: {email} → {name}")
        email_input.value = ""
        name_input.value = ""
        self._refresh_table()

    def _remove_alias(self) -> None:
        """Remove alias for the selected author — pre-fill email from selection."""
        table = self.query_one("#identity-table", DataTable)
        result = self.query_one("#identity-result", Static)

        if table.row_count == 0:
            result.update("No rows to select")
            return

        try:
            row = table.get_row_at(table.cursor_row)
            # Emails column has comma-separated emails, find manual ones (marked with *)
            emails_str = str(row[1])
            manual_emails = [
                e.replace(" *", "").strip()
                for e in emails_str.split(",")
                if "*" in e
            ]
            if not manual_emails:
                result.update("No manual aliases for this author")
                return
            for email in manual_emails:
                self.db.remove_author_alias(email)
            self.db.rebuild_author_identities()
            result.update(f"Removed {len(manual_emails)} alias(es)")
            self._refresh_table()
        except Exception as e:
            result.update(str(e))

    def _refresh_identities(self) -> None:
        result = self.query_one("#identity-result", Static)
        num = self.db.rebuild_author_identities()
        result.update(f"Refreshed: {num} unique authors")
        self._refresh_table()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Pre-fill the email input when a row is selected."""
        table = self.query_one("#identity-table", DataTable)
        row = table.get_row_at(event.cursor_row)
        name = str(row[0])
        emails_str = str(row[1])
        # Get first email (without the * marker)
        first_email = emails_str.split(",")[0].replace(" *", "").strip()

        self.query_one("#alias-email-input", Input).value = first_email
        self.query_one("#alias-name-input", Input).value = name
