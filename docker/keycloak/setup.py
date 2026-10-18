"""Идемпотентная настройка User Profile после готовности Keycloak."""
import os

import httpx


def main() -> None:
    with httpx.Client(base_url=os.environ["KEYCLOAK_URL"], timeout=15) as client:
        response = client.post(
            "/realms/master/protocol/openid-connect/token",
            data={
                "grant_type": "password", "client_id": "admin-cli",
                "username": os.environ["KEYCLOAK_ADMIN"],
                "password": os.environ["KEYCLOAK_ADMIN_PASSWORD"],
            },
        )
        response.raise_for_status()
        headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        url = "/admin/realms/product-service/users/profile"
        response = client.get(url, headers=headers)
        response.raise_for_status()
        profile = response.json()
        for attribute in profile["attributes"]:
            if attribute["name"] == "email":
                attribute.pop("required", None)
        existing = {attribute["name"] for attribute in profile["attributes"]}
        for name, label in [("patronymic", "Отчество"), ("phone_number", "Номер телефона"), ("birthday", "Дата рождения")]:
            if name not in existing:
                profile["attributes"].append({
                    "name": name, "displayName": label, "multivalued": False,
                    "permissions": {"view": ["admin", "user"], "edit": ["admin"]},
                    "validations": {"length": {"max": 255}},
                })
        response = client.put(url, headers=headers, json=profile)
        response.raise_for_status()
    print("Keycloak: профиль регистрации настроен.")


if __name__ == "__main__":
    main()
