"""Trends tab with commit and LOC charts, toggleable between weekly/monthly."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static

from textual_plotext import PlotextPlot

from borg.db import Database, QueryFilters


class TrendsTab(Static):
    """Trends tab: commits chart on top, LOC chart below, week/month toggle."""

    def __init__(self, db: Database) -> None:
        super().__init__()
        self.db = db
        self._period = "weekly"

    def compose(self) -> ComposeResult:
        with Vertical():
            with Horizontal(id="trend-toggle"):
                yield Button("Weekly", id="btn-weekly", variant="primary")
                yield Button("Monthly", id="btn-monthly", variant="default")
            yield PlotextPlot(id="commits-chart")
            yield PlotextPlot(id="loc-chart")

    def refresh_data(self, org: str | None = None, filters: QueryFilters | None = None) -> None:
        f = filters or QueryFilters(org=org)
        self._render(f)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-weekly":
            self._period = "weekly"
            self.query_one("#btn-weekly", Button).variant = "primary"
            self.query_one("#btn-monthly", Button).variant = "default"
        elif event.button.id == "btn-monthly":
            self._period = "monthly"
            self.query_one("#btn-monthly", Button).variant = "primary"
            self.query_one("#btn-weekly", Button).variant = "default"
        else:
            return
        self._render(self.app.query_filters)

    def _render(self, f: QueryFilters) -> None:
        data = self.db.query_trends(period=self._period, filters=f)
        label = "Weekly" if self._period == "weekly" else "Monthly"

        if not data:
            self._clear_chart("commits-chart", f"No commit data ({label})")
            self._clear_chart("loc-chart", f"No LOC data ({label})")
            return

        periods = [d["period"] for d in data]
        totals = [d["total"] for d in data]
        ai_counts = [d["ai"] for d in data]
        total_locs = [d["total_loc"] for d in data]
        ai_locs = [d["ai_loc"] for d in data]
        x = list(range(len(periods)))

        # Commits chart
        self._plot_chart(
            "commits-chart", x, periods,
            [(totals, "Total"), (ai_counts, "AI")],
            f"{label} Commits",
        )

        # LOC chart
        self._plot_chart(
            "loc-chart", x, periods,
            [(total_locs, "Total LOC"), (ai_locs, "AI LOC")],
            f"{label} Lines of Code",
        )

    def _plot_chart(
        self, chart_id: str, x: list, labels: list,
        series: list[tuple[list, str]], title: str,
    ) -> None:
        try:
            chart = self.query_one(f"#{chart_id}", PlotextPlot)
        except Exception:
            return
        plt = chart.plt
        plt.clear_figure()
        for values, name in series:
            plt.plot(x, values, label=name, marker="braille")
        plt.xticks(x, labels)
        plt.title(title)
        chart.refresh()

    def _clear_chart(self, chart_id: str, title: str) -> None:
        try:
            chart = self.query_one(f"#{chart_id}", PlotextPlot)
            chart.plt.clear_figure()
            chart.plt.title(title)
            chart.refresh()
        except Exception:
            pass
