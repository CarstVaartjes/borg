"""Trends tab with monthly and weekly line charts."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from textual_plotext import PlotextPlot

from borg.db import Database, QueryFilters


class TrendsTab(Static):
    """Trends tab showing monthly and weekly commit charts."""

    def __init__(self, db: Database) -> None:
        """Initialize with database reference.

        Args:
            db: Database instance for queries.
        """
        super().__init__()
        self.db = db

    def compose(self) -> ComposeResult:
        """Build trends layout with two charts."""
        with Vertical():
            yield PlotextPlot(id="monthly-chart")
            yield PlotextPlot(id="weekly-chart")

    def refresh_data(self, org: str | None = None, filters: QueryFilters | None = None) -> None:
        f = filters or QueryFilters(org=org)
        self._update_chart("monthly", f)
        self._update_chart("weekly", f)

    def _update_chart(self, period: str, f: QueryFilters) -> None:
        chart_id = f"#{period}-chart"
        try:
            chart = self.query_one(chart_id, PlotextPlot)
        except Exception:
            return

        data = self.db.query_trends(period=period, filters=f)
        plt = chart.plt
        plt.clear_figure()

        if not data:
            plt.title(f"No data ({period})")
        else:
            periods = [d["period"] for d in data]
            totals = [d["total"] for d in data]
            ai_counts = [d["ai"] for d in data]
            x_indices = list(range(len(periods)))

            plt.plot(x_indices, totals, label="Total", marker="braille")
            plt.plot(x_indices, ai_counts, label="AI", marker="braille")
            plt.xticks(x_indices, periods)
            plt.title(f"Commit Trends ({period.capitalize()})")

        chart.refresh()
