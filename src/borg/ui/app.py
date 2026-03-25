"""Main Textual TUI application for borg tracker."""

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Footer, Header, Label, Select, TabbedContent, TabPane

from borg.db import Database
from borg.ui.authors import AuthorsTab
from borg.ui.detect_tab import DetectTab
from borg.ui.export_tab import ExportTab
from borg.ui.fetch_tab import FetchTab
from borg.ui.orgs_tab import OrgsTab
from borg.ui.overview import OverviewTab
from borg.ui.repos import ReposTab
from borg.ui.trends import TrendsTab


class BorgApp(App):
    """Borg TUI — AI commit adoption tracker."""

    TITLE = "Borg"
    SUB_TITLE = "Resistance is futile"

    CSS = """
    #org-bar {
        height: 3;
        padding: 0 1;
        layout: horizontal;
    }
    #org-bar Label {
        width: auto;
        padding: 1 1 0 0;
    }
    #org-select {
        width: 40;
    }
    TabbedContent {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("1", "show_tab('overview')", "Overview"),
        Binding("2", "show_tab('authors')", "Authors"),
        Binding("3", "show_tab('repos')", "Repos"),
        Binding("4", "show_tab('trends')", "Trends"),
        Binding("5", "show_tab('fetch')", "Fetch"),
        Binding("6", "show_tab('detect')", "Detect"),
        Binding("7", "show_tab('export')", "Export"),
        Binding("8", "show_tab('orgs')", "Orgs"),
        Binding("q", "quit", "Quit"),
    ]

    org_filter: str | None = None

    def __init__(self, db_path: Path) -> None:
        """Initialize app with database path.

        Args:
            db_path: Path to the SQLite database file.
        """
        super().__init__()
        self.db = Database(db_path)

    def compose(self) -> ComposeResult:
        """Build the app layout."""
        yield Header()
        with Container(id="org-bar"):
            yield Label("Org:")
            yield Select(
                [],
                prompt="All orgs",
                allow_blank=True,
                id="org-select",
            )
        with TabbedContent(id="tabs"):
            with TabPane("Overview", id="overview"):
                yield OverviewTab(self.db)
            with TabPane("Authors", id="authors"):
                yield AuthorsTab(self.db)
            with TabPane("Repos", id="repos"):
                yield ReposTab(self.db)
            with TabPane("Trends", id="trends"):
                yield TrendsTab(self.db)
            with TabPane("Fetch", id="fetch"):
                yield FetchTab(self.db)
            with TabPane("Detect", id="detect"):
                yield DetectTab(self.db)
            with TabPane("Export", id="export"):
                yield ExportTab(self.db)
            with TabPane("Orgs", id="orgs"):
                yield OrgsTab(self.db)
        yield Footer()

    def on_mount(self) -> None:
        """Initialize after mount: refresh org dropdown, auto-switch to Orgs tab."""
        self.refresh_org_dropdown()
        orgs = self.db.org_get_all()
        if not orgs:
            self.query_one(TabbedContent).active = "orgs"
        else:
            self._refresh_active_tab()

    def refresh_org_dropdown(self) -> None:
        """Reload the org filter dropdown from the database."""
        orgs = self.db.org_get_all()
        select = self.query_one("#org-select", Select)
        options = [(org["name"], org["name"]) for org in orgs]
        select.set_options(options)

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle org filter dropdown change."""
        if event.select.id == "org-select":
            value = event.value
            self.org_filter = None if value is Select.BLANK else str(value)
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
            "overview": OverviewTab,
            "authors": AuthorsTab,
            "repos": ReposTab,
            "trends": TrendsTab,
            "fetch": FetchTab,
            "detect": DetectTab,
            "export": ExportTab,
            "orgs": OrgsTab,
        }
        widget_class = tab_map.get(active_pane)
        if widget_class:
            try:
                widget = self.query_one(f"#{active_pane} {widget_class.__name__}")
                if hasattr(widget, "refresh_data"):
                    widget.refresh_data(org=self.org_filter)
            except Exception:
                pass

    def action_show_tab(self, tab_id: str) -> None:
        """Switch to a specific tab by ID.

        Args:
            tab_id: The tab pane ID to activate.
        """
        self.query_one(TabbedContent).active = tab_id
