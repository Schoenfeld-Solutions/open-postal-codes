from __future__ import annotations

from pathlib import Path


def write_osm(path: Path, body: str) -> None:
    path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6" generator="open-postal-codes-test">
{body}
</osm>
""",
        encoding="utf-8",
    )


def nodes(start: int, coordinates: list[tuple[float, float]]) -> str:
    return "\n".join(
        f'  <node id="{start + index}" lat="{lat}" lon="{lon}" />'
        for index, (lat, lon) in enumerate(coordinates)
    )


def closed_way(
    way_id: int,
    node_start: int,
    tags: dict[str, str],
) -> str:
    tag_lines = "\n".join(f'    <tag k="{key}" v="{value}" />' for key, value in tags.items())
    return f"""  <way id="{way_id}">
    <nd ref="{node_start}" />
    <nd ref="{node_start + 1}" />
    <nd ref="{node_start + 2}" />
    <nd ref="{node_start + 3}" />
    <nd ref="{node_start}" />
{tag_lines}
    </way>"""


def tagged_node(node_id: int, lat: float, lon: float, tags: dict[str, str]) -> str:
    tag_lines = "".join(f'<tag k="{key}" v="{value}" />' for key, value in tags.items())
    return f'  <node id="{node_id}" lat="{lat}" lon="{lon}">{tag_lines}</node>'


def boundary_fixture(extra: str) -> str:
    return "\n".join(
        [
            nodes(1, [(0, 0), (0, 10), (10, 10), (10, 0)]),
            closed_way(
                100,
                1,
                {
                    "boundary": "administrative",
                    "admin_level": "2",
                    "ISO3166-1:alpha2": "DE",
                },
            ),
            nodes(5, [(0, 0), (0, 10), (10, 10), (10, 0)]),
            closed_way(
                105,
                5,
                {
                    "boundary": "administrative",
                    "admin_level": "4",
                    "ISO3166-2": "DE-HB",
                    "name": "Bremen",
                },
            ),
            nodes(10, [(0, 0), (0, 5), (10, 5), (10, 0)]),
            closed_way(
                110,
                10,
                {
                    "boundary": "administrative",
                    "admin_level": "6",
                    "de:amtlicher_gemeindeschluessel": "04011",
                    "name": "County A",
                },
            ),
            nodes(20, [(0, 5), (0, 10), (10, 10), (10, 5)]),
            closed_way(
                120,
                20,
                {
                    "boundary": "administrative",
                    "admin_level": "6",
                    "de:amtlicher_gemeindeschluessel": "04012",
                    "name": "County B",
                },
            ),
            extra,
        ]
    )


def country_boundary_fixture(
    *,
    country: str,
    county_admin_level: str,
    county_name: str,
    extra: str,
    county_iso_code: str | None = None,
    state_name: str | None = None,
    state_iso_code: str | None = None,
) -> str:
    county_tags = {
        "boundary": "administrative",
        "admin_level": county_admin_level,
        "name": county_name,
    }
    if county_iso_code is not None:
        county_tags["ISO3166-2"] = county_iso_code

    parts = [
        nodes(1, [(0, 0), (0, 10), (10, 10), (10, 0)]),
        closed_way(
            100,
            1,
            {
                "boundary": "administrative",
                "admin_level": "2",
                "ISO3166-1:alpha2": country,
            },
        ),
    ]
    if state_name is not None and state_iso_code is not None:
        parts.extend(
            [
                nodes(5, [(0, 0), (0, 10), (10, 10), (10, 0)]),
                closed_way(
                    105,
                    5,
                    {
                        "boundary": "administrative",
                        "admin_level": "4",
                        "ISO3166-2": state_iso_code,
                        "name": state_name,
                    },
                ),
            ]
        )
    parts.extend(
        [
            nodes(10, [(0, 0), (0, 10), (10, 10), (10, 0)]),
            closed_way(110, 10, county_tags),
            extra,
        ]
    )
    return "\n".join(parts)
