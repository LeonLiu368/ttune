"""One parser per source id. To add one: write `parse(snapshot) -> list[Row]` in a module here and register it."""

from scraper.extract import Parser
from scraper.parsers import medicaid_levels

PARSERS: dict[str, Parser] = {
    "medicaid-eligibility-levels": medicaid_levels.parse,
}
