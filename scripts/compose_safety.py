"""Validate private production-like topology without starting any container."""

from __future__ import annotations

import json
import subprocess


def main() -> None:
    model = json.loads(
        subprocess.check_output(
            [
                "docker",
                "compose",
                "--env-file",
                ".env.example",
                "-p",
                "sports-readiness-check",
                "-f",
                "compose.yaml",
                "-f",
                "compose.production-example.yaml",
                "--profile",
                "telegram",
                "config",
                "--format",
                "json",
            ]
        )
    )
    assert model["name"] == "sports-readiness-check"
    for name, service in model["services"].items():
        assert name.startswith("sports-") and not service.get("ports")
        assert not service.get("container_name") and service["restart"] == "unless-stopped"
        assert service["logging"]["options"]["max-size"] == "10m"
        if service.get("build"):
            assert service["build"]["target"] == "production"
            assert service["environment"]["PRODUCTION_LIKE"] == "true"
            assert service["environment"]["LOG_LEVEL"] != "DEBUG"
    assert all(
        volume["name"].startswith("sports-readiness-check_") for volume in model["volumes"].values()
    )
    assert all(
        network["name"].startswith("sports-readiness-check_")
        for network in model["networks"].values()
    )
    print(
        "PASS: private project-scoped containers/network/volumes, "
        "zero host ports, production targets"
    )


if __name__ == "__main__":
    main()
