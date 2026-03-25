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
        self._suggestions: list[dict] = []

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Author Identity Groups", id="identity-title")
            yield Static(
                "Auto-resolved by shared names/emails. Manual aliases marked with *.",
                id="identity-help",
            )
            yield DataTable(id="identity-table")
            yield Static("")
            yield Static("Suggested Merges", id="suggest-title")
            yield DataTable(id="suggest-table")
            with Horizontal(id="suggest-actions"):
                yield Button("Apply Selected", id="apply-suggest-btn", variant="primary")
                yield Button("Apply All", id="apply-all-btn", variant="warning")
            yield Static("")
            yield Static("Manual Alias")
            with Horizontal(id="alias-form"):
                yield Input(placeholder="email", id="alias-email-input")
                yield Input(placeholder="canonical name", id="alias-name-input")
                yield Button("Set Alias", id="set-alias-btn", variant="primary")
            with Horizontal(id="alias-actions"):
                yield Button("Remove Alias", id="remove-alias-btn", variant="error")
                yield Button("Refresh", id="refresh-btn", variant="default")
            yield Static("", id="identity-result")

    def on_mount(self) -> None:
        # Identity groups table
        table = self.query_one("#identity-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Author", "Emails", "Manual")

        # Suggestions table
        suggest = self.query_one("#suggest-table", DataTable)
        suggest.cursor_type = "row"
        suggest.add_columns("Merge", "Into", "Emails to move")

        self._refresh_all()

    def refresh_data(self, **kwargs) -> None:
        self._refresh_all()

    def _refresh_all(self) -> None:
        self._refresh_table()
        self._refresh_suggestions()

    def _refresh_table(self) -> None:
        table = self.query_one("#identity-table", DataTable)
        table.clear()

        groups = self.db.get_identity_groups()
        manual_aliases = {a["email"]: a["canonical_name"] for a in self.db.get_author_aliases()}

        for group in groups:
            name = group["canonical_name"]
            emails = group["emails"]
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

    def _refresh_suggestions(self) -> None:
        suggest = self.query_one("#suggest-table", DataTable)
        suggest.clear()

        self._suggestions = self.db.suggest_alias_merges()

        for i, s in enumerate(self._suggestions):
            suggest.add_row(
                s["source_name"],
                s["target_name"],
                ", ".join(s["source_emails"]),
                key=str(i),
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "set-alias-btn":
            self._set_alias()
        elif event.button.id == "remove-alias-btn":
            self._remove_alias()
        elif event.button.id == "refresh-btn":
            self._refresh_identities()
        elif event.button.id == "apply-suggest-btn":
            self._apply_selected_suggestion()
        elif event.button.id == "apply-all-btn":
            self._apply_all_suggestions()

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
        self._refresh_all()

    def _remove_alias(self) -> None:
        table = self.query_one("#identity-table", DataTable)
        result = self.query_one("#identity-result", Static)

        if table.row_count == 0:
            result.update("No rows to select")
            return

        try:
            row = table.get_row_at(table.cursor_row)
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
            self._refresh_all()
        except Exception as e:
            result.update(str(e))

    def _apply_selected_suggestion(self) -> None:
        suggest = self.query_one("#suggest-table", DataTable)
        result = self.query_one("#identity-result", Static)

        if not self._suggestions or suggest.row_count == 0:
            result.update("No suggestions to apply")
            return

        try:
            idx = suggest.cursor_row
            if 0 <= idx < len(self._suggestions):
                s = self._suggestions[idx]
                count = self.db.apply_suggested_merges([s])
                self.db.rebuild_author_identities()
                result.update(f"Merged '{s['source_name']}' into '{s['target_name']}' ({count} alias(es))")
                self._refresh_all()
        except Exception as e:
            result.update(str(e))

    def _apply_all_suggestions(self) -> None:
        result = self.query_one("#identity-result", Static)

        if not self._suggestions:
            result.update("No suggestions to apply")
            return

        count = self.db.apply_suggested_merges(self._suggestions)
        self.db.rebuild_author_identities()
        result.update(f"Applied {len(self._suggestions)} merges ({count} aliases)")
        self._refresh_all()

    def _refresh_identities(self) -> None:
        result = self.query_one("#identity-result", Static)
        num = self.db.rebuild_author_identities()
        result.update(f"Refreshed: {num} unique authors")
        self._refresh_all()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Pre-fill alias inputs from identity table selection."""
        # Only handle identity table, not suggest table
        if event.data_table.id != "identity-table":
            return
        table = self.query_one("#identity-table", DataTable)
        row = table.get_row_at(event.cursor_row)
        name = str(row[0])
        emails_str = str(row[1])
        first_email = emails_str.split(",")[0].replace(" *", "").strip()

        self.query_one("#alias-email-input", Input).value = first_email
        self.query_one("#alias-name-input", Input).value = name
