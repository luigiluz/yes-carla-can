import pytest
import yaml

from CARLA_client_module import load_config


def write_config(tmp_path, config):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def test_load_config_returns_map_and_vehicle(tmp_path):
    path = write_config(
        tmp_path,
        {"map": "Town03", "vehicle": "vehicle.audi.tt"},
    )

    assert load_config(path) == ("Town03", "vehicle.audi.tt")


@pytest.mark.parametrize(
    "config",
    [
        {"map": "Town01"},
        {"map": "Town01", "vehicle": "vehicle.tesla.model3", "layers": []},
        {"map": "", "vehicle": "vehicle.tesla.model3"},
        {"map": "Town01", "vehicle": "tesla.model3"},
    ],
)
def test_load_config_rejects_invalid_configuration(tmp_path, config):
    path = write_config(tmp_path, config)

    with pytest.raises(ValueError):
        load_config(path)
