"""Overview tab showing summary stats and tool breakdown chart."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from textual_plotext import PlotextPlot

from borg.db import Database, QueryFilters


class OverviewTab(Static):
    """Overview tab with assimilation progress and tool chart."""

    def __init__(self, db: Database) -> None:
        """Initialize with database reference.

        Args:
            db: Database instance for queries.
        """
        super().__init__()
        self.db = db

    def compose(self) -> ComposeResult:
        """Build overview layout."""
        with Vertical():
            yield Static(id="summary-box")
            yield Static(id="skynet-box")
            yield PlotextPlot(id="tool-chart")

    def refresh_data(self, org: str | None = None, filters: QueryFilters | None = None) -> None:
        f = filters or QueryFilters(org=org)
        self._update_summary(f)
        self._update_skynet(f)
        self._update_tool_chart(f)

    def _update_summary(self, f: QueryFilters) -> None:
        summary = self.db.query_summary(filters=f)
        total = summary["total_commits"]
        ai = summary["ai_commits"]
        commit_pct = (ai / total * 100) if total > 0 else 0
        total_loc = summary["total_loc"]
        ai_loc = summary["ai_loc"]
        loc_pct = (ai_loc / total_loc * 100) if total_loc > 0 else 0

        text = (
            f"Assimilation Progress\n"
            f"  Commits: {ai:,} / {total:,} ({commit_pct:.1f}%)\n"
            f"  LOC:     {ai_loc:,} / {total_loc:,} ({loc_pct:.1f}%)"
        )
        try:
            self.query_one("#summary-box", Static).update(text)
        except Exception:
            pass

    def _update_skynet(self, f: QueryFilters) -> None:
        employee = self.db.query_skynet_employee(filters=f)
        if employee:
            text = (
                f"Skynet Employee of the Week: "
                f"{employee['author']} ({employee['ai_commits']} AI commits)"
            )
        else:
            text = "Skynet Employee of the Week: No AI commits in the last 7 days"
        try:
            self.query_one("#skynet-box", Static).update(text)
        except Exception:
            pass

    def _update_tool_chart(self, f: QueryFilters) -> None:
        tools = self.db.query_by_tool(filters=f)
        try:
            chart = self.query_one("#tool-chart", PlotextPlot)
        except Exception:
            return

        plt = chart.plt
        plt.clear_figure()

        if not tools:
            plt.title("No AI commits detected")
        else:
            names = [t["tool"] for t in tools]
            counts = [t["commits"] for t in tools]
            plt.bar(names, counts, orientation="horizontal")
            plt.title("AI Commits by Tool")

        chart.refresh()
