"""One parser per source id. To add one: write `parse(snapshot) -> list[Row]` in a module here and register it."""

from scraper.extract import Parser
from scraper.parsers import hhs_fpg, irs_eitc, medicaid_current, medicaid_levels, snap_cola, snap_sua

PARSERS: dict[str, Parser] = {
    "hhs-poverty-guidelines": hhs_fpg.parse,
    "fns-snap-cola-fy27": snap_cola.parse,
    "fns-snap-sua-fy26": snap_sua.parse,
    "irs-eitc-rp-25-32": irs_eitc.parse,
    "medicaid-eligibility-levels": medicaid_levels.parse,
    "medicaid-eligibility-levels-current": medicaid_current.parse,
}
