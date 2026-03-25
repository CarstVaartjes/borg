"""Source tab showing summary stats and tool breakdown chart."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from textual_plotext import PlotextPlot

from borg.db import Database, QueryFilters


class OverviewTab(Static):
    """Source tab with assimilation progress and tool chart."""

    DEFAULT_CSS = """
    OverviewTab {
        height: 1fr;
    }
    #summary-box {
        padding: 1 2;
        margin: 0 0 1 0;
        border: solid #1a3a2e;
        background: #0f0f23;
        height: auto;
    }
    #skynet-box {
        padding: 1 2;
        margin: 0 0 1 0;
        border: solid #ffaa00;
        background: #1a1500;
        color: #ffaa00;
        height: auto;
    }
    #stats-row {
        height: auto;
        margin: 0 0 1 0;
    }
    #stat-left {
        width: 1fr;
        padding: 1 2;
        border: solid #1a3a2e;
        background: #0f0f23;
        height: auto;
    }
    #stat-right {
        width: 1fr;
        padding: 1 2;
        border: solid #1a3a2e;
        background: #0f0f23;
        height: auto;
        margin-left: 1;
    }
    #tool-chart {
        height: 1fr;
        min-height: 10;
    }
    """

    def __init__(self, db: Database) -> None:
        super().__init__()
        self.db = db

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(id="summary-box")
            with Horizontal(id="stats-row"):
                yield Static(id="stat-left")
                yield Static(id="stat-right")
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

        bar_width = 30
        commit_fill = int(bar_width * commit_pct / 100)
        loc_fill = int(bar_width * loc_pct / 100)
        commit_bar = "█" * commit_fill + "░" * (bar_width - commit_fill)
        loc_bar = "█" * loc_fill + "░" * (bar_width - loc_fill)

        summary_text = (
            f"⚡ ASSIMILATION PROGRESS\n\n"
            f"  Commits  {commit_bar}  {commit_pct:.1f}%\n"
            f"           {ai:,} AI / {total:,} total\n\n"
            f"  LOC      {loc_bar}  {loc_pct:.1f}%\n"
            f"           {ai_loc:,} AI / {total_loc:,} total"
        )

        # Stats for the side panels
        try:
            tools = self.db.query_by_tool(filters=f)
            top_tool = tools[0]["tool"] if tools else "none"
            top_tool_count = tools[0]["commits"] if tools else 0
        except Exception:
            top_tool, top_tool_count = "none", 0

        try:
            self.query_one("#summary-box", Static).update(summary_text)
            self.query_one("#stat-left", Static).update(
                f"🔧 Top Tool: {top_tool}\n   {top_tool_count:,} commits"
            )
            self.query_one("#stat-right", Static).update(
                f"📊 {len(tools)} AI tools detected\n   across all repos"
            )
        except Exception:
            pass

    def _update_skynet(self, f: QueryFilters) -> None:
        employee = self.db.query_skynet_employee(filters=f)
        if employee:
            text = (
                f"⭐ SKYNET EMPLOYEE OF THE WEEK\n"
                f"   {employee['author']} — {employee['ai_commits']} AI commits in 7 days"
            )
        else:
            text = "⭐ SKYNET EMPLOYEE OF THE WEEK\n   No AI commits in the last 7 days"
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
        plt.theme("dark")

        if not tools:
            plt.title("No AI commits detected")
        else:
            names = [t["tool"] for t in tools]
            counts = [t["commits"] for t in tools]
            plt.bar(names, counts, orientation="horizontal", color="green")
            plt.title("AI Commits by Tool")

        chart.refresh()
