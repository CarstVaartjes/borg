"""Main Textual TUI application for borg tracker."""

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Footer, Header, Label, Select, TabbedContent, TabPane

from borg.db import Database, QueryFilters
from borg.ui.authors import AuthorsTab
from borg.ui.export_tab import ExportTab
from borg.ui.fetch_tab import FetchTab
from borg.ui.identity_tab import IdentityTab
from borg.ui.orgs_tab import OrgsTab
from borg.ui.overview import OverviewTab
from borg.ui.repos import ReposTab
from borg.ui.trends import TrendsTab


class BorgApp(App):
    """Borg TUI — AI commit adoption tracker."""

    TITLE = "Borg"
    SUB_TITLE = "Resistance is futile"

    CSS = """
    /* ── Global theme ────────────────────────────────── */
    Screen {
        background: #0c0c1a;
    }
    Header {
        background: #1a1a2e;
        color: #00ff88;
    }
    Footer {
        background: #1a1a2e;
    }
    TabbedContent {
        height: 1fr;
    }
    TabPane {
        padding: 1 1;
    }
    ContentSwitcher {
        background: #0c0c1a;
    }
    DataTable {
        background: #0f0f23;
    }
    DataTable > .datatable--header {
        background: #1a1a2e;
        color: #00ff88;
        text-style: bold;
    }
    DataTable > .datatable--cursor {
        background: #1a3a2e;
        color: #ffffff;
    }
    Button {
        margin: 0 1 0 0;
    }
    Button.-primary {
        background: #00aa66;
    }

    /* ── Filter bar ──────────────────────────────────── */
    #org-bar {
        height: 3;
        padding: 0 1;
        layout: horizontal;
        background: #12122a;
        border-bottom: solid #1a3a2e;
    }
    #org-bar Label {
        width: auto;
        padding: 1 1 0 0;
        color: #00ff88;
        text-style: bold;
    }
    #org-bar Select {
        width: 1fr;
        max-width: 28;
    }
    #loc-select {
        max-width: 20;
    }

    /* ── Authors tab ─────────────────────────────────── */
    #authors-layout {
        height: 1fr;
    }
    #authors-layout RankingTab {
        width: 2fr;
    }
    #avatar-panel {
        width: 65;
        padding: 1 2;
        border-left: solid #00ff88;
        background: #0f0f23;
        overflow-y: auto;
        color: #00ff88;
    }

    /* ── Trends tab ──────────────────────────────────── */
    #trend-toggle {
        height: 3;
    }
    #trend-toggle Button {
        width: auto;
    }

    /* ── Fetch tab ───────────────────────────────────── */
    #fetch-buttons {
        height: 3;
        margin: 0 0 1 0;
    }
    #fetch-buttons Button {
        width: auto;
    }
    #fetch-log {
        height: 1fr;
        background: #0a0a18;
        border: solid #1a1a2e;
        padding: 1;
    }
    #rules-title {
        margin: 1 0 0 0;
        text-style: bold;
        color: #00ff88;
    }
    #rules-table {
        max-height: 30%;
    }

    /* ── Export tab ───────────────────────────────────── */
    ExportTab Input {
        margin: 0 0 1 0;
    }

    /* ── Identity tab ────────────────────────────────── */
    #identity-title {
        text-style: bold;
        color: #00ff88;
    }
    #identity-help {
        color: $text-muted;
        margin-bottom: 1;
    }
    #identity-table {
        height: 1fr;
        max-height: 40%;
    }
    #suggest-title {
        text-style: bold;
        color: #ffaa00;
        margin: 1 0 0 0;
    }
    #suggest-table {
        max-height: 25%;
    }
    #suggest-actions {
        height: 3;
    }
    #suggest-actions Button {
        width: auto;
    }
    #alias-form {
        height: 3;
        margin: 1 0;
    }
    #alias-form Input {
        width: 1fr;
    }
    #alias-form Button {
        width: auto;
    }
    #alias-actions {
        height: 3;
    }
    #alias-actions Button {
        width: auto;
    }
    #identity-result {
        height: auto;
        color: #ffaa00;
    }

    /* ── Orgs tab ────────────────────────────────────── */
    OrgsTab {
        height: 1fr;
    }
    OrgsTab > Vertical {
        height: 1fr;
    }
    #orgs-table {
        height: 1fr;
        max-height: 60%;
    }
    OrgsTab Horizontal {
        height: 3;
        margin: 1 0;
    }
    OrgsTab Horizontal Input {
        width: 1fr;
    }
    OrgsTab Horizontal Button {
        width: auto;
    }
    #remove-org-btn {
        margin: 0 0 1 0;
    }
    #org-result {
        height: auto;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("1", "show_tab('authors')", "Authors"),
        Binding("2", "show_tab('repos')", "Repos"),
        Binding("3", "show_tab('trends')", "Trends"),
        Binding("4", "show_tab('source')", "Source"),
        Binding("5", "show_tab('fetch')", "Fetch"),
        Binding("6", "show_tab('export')", "Export"),
        Binding("7", "show_tab('identity')", "Identity"),
        Binding("8", "show_tab('orgs')", "Orgs"),
        Binding("q", "quit", "Quit"),
    ]

    org_filter: str | None = None
    repo_filter: str | None = None
    author_filter: str | None = None
    month_filter: str | None = None
    week_filter: str | None = None
    loc_mode: str = "both"

    def __init__(self, db_path: Path) -> None:
        super().__init__()
        self.db = Database(db_path)

    @property
    def query_filters(self) -> QueryFilters:
        """Current filter state as a QueryFilters object."""
        return QueryFilters(
            org=self.org_filter,
            repo=self.repo_filter,
            author=self.author_filter,
            month=self.month_filter,
            week=self.week_filter,
            loc_mode=self.loc_mode,
        )

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="org-bar"):
            yield Label("Org:")
            yield Select([], prompt="All orgs", allow_blank=True, id="org-select")
            yield Label("Repo:")
            yield Select([], prompt="All repos", allow_blank=True, id="repo-select")
            yield Label("Author:")
            yield Select([], prompt="All authors", allow_blank=True, id="author-select")
            yield Label("Month:")
            yield Select([], prompt="All", allow_blank=True, id="month-select")
            yield Label("Week:")
            yield Select([], prompt="All", allow_blank=True, id="week-select")
            yield Label("LOC:")
            yield Select(
                [("Added + Deleted", "both"), ("Added only", "added")],
                value="both",
                allow_blank=False,
                id="loc-select",
            )
        with TabbedContent(id="tabs", initial="authors"):
            with TabPane("Authors", id="authors"):
                yield AuthorsTab(self.db)
            with TabPane("Repos", id="repos"):
                yield ReposTab(self.db)
            with TabPane("Trends", id="trends"):
                yield TrendsTab(self.db)
            with TabPane("Source", id="source"):
                yield OverviewTab(self.db)
            with TabPane("Fetch", id="fetch"):
                yield FetchTab(self.db)
            with TabPane("Export", id="export"):
                yield ExportTab(self.db)
            with TabPane("Identity", id="identity"):
                yield IdentityTab(self.db)
            with TabPane("Orgs", id="orgs"):
                yield OrgsTab(self.db)
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_dropdowns()
        orgs = self.db.org_get_all()
        if not orgs:
            self.query_one(TabbedContent).active = "orgs"
        else:
            self._refresh_active_tab()

    def refresh_dropdowns(self) -> None:
        """Reload all filter dropdowns from the database."""
        # Orgs
        orgs = self.db.org_get_all()
        self.query_one("#org-select", Select).set_options(
            [(o["name"], o["name"]) for o in orgs]
        )
        # Repos
        repos = self.db.conn.execute(
            "SELECT DISTINCT repo FROM commits ORDER BY repo"
        ).fetchall()
        self.query_one("#repo-select", Select).set_options(
            [(r["repo"], r["repo"]) for r in repos]
        )
        # Authors
        try:
            authors = self.db.conn.execute(
                "SELECT DISTINCT canonical_name FROM _author_identity ORDER BY canonical_name"
            ).fetchall()
            self.query_one("#author-select", Select).set_options(
                [(a["canonical_name"], a["canonical_name"]) for a in authors]
            )
        except Exception:
            authors = self.db.conn.execute(
                "SELECT DISTINCT author FROM commits ORDER BY author"
            ).fetchall()
            self.query_one("#author-select", Select).set_options(
                [(a["author"], a["author"]) for a in authors]
            )
        # Months
        months = self.db.conn.execute(
            "SELECT DISTINCT strftime('%Y-%m', date) as m FROM commits ORDER BY m DESC"
        ).fetchall()
        self.query_one("#month-select", Select).set_options(
            [(m["m"], m["m"]) for m in months if m["m"]]
        )
        # Weeks
        weeks = self.db.conn.execute(
            "SELECT DISTINCT strftime('%Y-W%W', date) as w FROM commits ORDER BY w DESC"
        ).fetchall()
        self.query_one("#week-select", Select).set_options(
            [(w["w"], w["w"]) for w in weeks if w["w"]]
        )

    # Keep backward-compatible alias
    def refresh_org_dropdown(self) -> None:
        self.refresh_dropdowns()

    def on_select_changed(self, event: Select.Changed) -> None:
        sid = event.select.id
        raw = event.value
        # Treat BLANK, None, and empty string all as "no filter"
        value = None if raw is Select.BLANK or raw is None or raw == "" else str(raw)
        if sid == "org-select":
            self.org_filter = value
        elif sid == "repo-select":
            self.repo_filter = value
        elif sid == "author-select":
            self.author_filter = value
        elif sid == "month-select":
            self.month_filter = value
        elif sid == "week-select":
            self.week_filter = value
        elif sid == "loc-select":
            self.loc_mode = value or "both"
        self._refresh_active_tab()

    def on_tabbed_content_tab_activated(
        self, event: TabbedContent.TabActivated
    ) -> None:
        """Refresh data when a tab is activated."""
        self._refresh_active_tab()

    def _refresh_active_tab(self) -> None:
        """Refresh the currently active tab's data."""
        tabs = self.query_one(TabbedContent)
        active_pane = tabs.active
        if not active_pane:
            return

        tab_map = {
            "authors": AuthorsTab,
            "repos": ReposTab,
            "trends": TrendsTab,
            "source": OverviewTab,
            "fetch": FetchTab,
            "export": ExportTab,
            "identity": IdentityTab,
            "orgs": OrgsTab,
        }
        widget_class = tab_map.get(active_pane)
        if widget_class:
            try:
                widget = self.query_one(f"#{active_pane} {widget_class.__name__}")
                if hasattr(widget, "refresh_data"):
                    widget.refresh_data(filters=self.query_filters)
            except Exception:
                pass

    def action_show_tab(self, tab_id: str) -> None:
        """Switch to a specific tab by ID.

        Args:
            tab_id: The tab pane ID to activate.
        """
        self.query_one(TabbedContent).active = tab_id
