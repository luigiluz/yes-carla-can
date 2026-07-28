import pytest
import yaml

from CARLA_client_module import load_config


VALID_CONFIG = {
    "map": "Town03",
    "vehicle": "vehicle.audi.tt",
    "traffic": {"enabled": False, "cars": 20},
    "pedestrians": {"enabled": False, "count": 20},
}


def write_config(tmp_path, config):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def test_load_config_returns_map_and_vehicle(tmp_path):
    path = write_config(
        tmp_path,
        VALID_CONFIG,
    )

    assert load_config(path) == VALID_CONFIG


@pytest.mark.parametrize(
    "config",
    [
        {**VALID_CONFIG, "vehicle": None},
        {**VALID_CONFIG, "layers": []},
        {**VALID_CONFIG, "map": ""},
        {**VALID_CONFIG, "vehicle": "tesla.model3"},
    ],
)
def test_load_config_rejects_invalid_configuration(tmp_path, config):
    path = write_config(tmp_path, config)

    with pytest.raises(ValueError):
        load_config(path)
