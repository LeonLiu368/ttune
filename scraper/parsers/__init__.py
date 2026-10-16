"""One parser per source id. To add one: write `parse(snapshot) -> list[Row]` in a module here and register it."""

from scraper.extract import Parser
from scraper.parsers import irs_eitc, medicaid_levels, snap_sua

PARSERS: dict[str, Parser] = {
    "fns-snap-sua-fy26": snap_sua.parse,
    "irs-eitc-rp-25-32": irs_eitc.parse,
    "medicaid-eligibility-levels": medicaid_levels.parse,
}
