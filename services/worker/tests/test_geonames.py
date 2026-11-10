from app.geonames import COLUMNS, parse_city_dump


def _row(
    geonameid: int,
    name: str,
    admin1: str,
    feature_code: str,
    population: int,
) -> str:
    values = [
        str(geonameid), name, name, "", "30.5", "104.0", "P", feature_code,
        "CN", "", admin1, "", "", "", str(population), "", "", "Asia/Shanghai",
        "2026-11-01",
    ]
    assert len(values) == len(COLUMNS)
    return "\t".join(values)


def test_geonames_city_import_uses_expected_admin_area_and_feature_rank() -> None:
    dump = "\n".join([
        _row(1, "Chengdu", "32", "PPLA", 1000000),
        _row(2, "Chengdu", "99", "PPLA", 9000000),
        _row(3, "Chengdu", "32", "PPL", 2000000),
        _row(4, "Chongqing", "33", "PPLA", 3000000),
        *[
            _row(10 + i, name, "32", "PPLA2", 100000)
            for i, name in enumerate([
                "Mianyang", "Deyang", "Suining", "Nanchong", "Guang'an",
                "Ziyang", "Meishan", "Leshan", "Neijiang", "Zigong", "Yibin", "Luzhou",
            ])
        ],
    ])
    admin1 = "CN.32\tSichuan\tSichuan\t1\nCN.33\tChongqing\tChongqing\t2\n"

    cities = parse_city_dump(dump, admin1)

    assert len(cities) == 14
    chengdu = next(city for city in cities if city["slug"] == "chengdu")
    assert chengdu["geoname_id"] == 1
    assert chengdu["admin1"] == "Sichuan"
