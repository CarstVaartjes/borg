"""Take automated SVG screenshots of each borg tab for README marketing."""

import asyncio
from pathlib import Path

SCREENSHOTS_DIR = Path(__file__).parent.parent / "docs" / "screenshots"
DB_PATH = Path(__file__).parent.parent / "demo" / "demo.db"

TABS = [
    ("authors", "Authors — AI adoption leaderboard with Skynet Employee avatar"),
    ("repos", "Repos — Which repositories are most AI-assisted"),
    ("trends", "Trends — Weekly adoption curves"),
    ("source", "Source — Assimilation progress overview"),
    ("identity", "Identity — Author identity resolution"),
]


async def take_screenshots() -> None:
    """Launch app headless and screenshot each tab."""
    from borg.ui.app import BorgApp

    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    app = BorgApp(db_path=DB_PATH)

    async with app.run_test(size=(160, 45)) as pilot:
        # Let initial mount settle
        await pilot.pause(1.0)

        for tab_id, title in TABS:
            # Navigate to tab
            tabs = pilot.app.query_one("TabbedContent")
            tabs.active = tab_id
            await pilot.pause(1.0)

            # Export SVG
            svg = pilot.app.export_screenshot(title=f"Borg — {title}")
            out_path = SCREENSHOTS_DIR / f"{tab_id}.svg"
            out_path.write_text(svg)
            print(f"  Saved: {out_path}")

    print(f"\nDone! {len(TABS)} screenshots in {SCREENSHOTS_DIR}")


if __name__ == "__main__":
    asyncio.run(take_screenshots())
