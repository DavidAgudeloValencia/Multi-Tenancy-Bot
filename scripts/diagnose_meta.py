"""Diagnóstico de la integración con Meta (sin exponer secretos).

Con el System User Token valida:
  1. Que el PHONE_NUMBER_ID sea válido (nombre verificado, calidad).
  2. Que el token tenga acceso al Business y a sus WABAs.
  3. Que la app esté suscrita a los webhooks del WABA (subscribed_apps).

Uso:
    python -m scripts.diagnose_meta
"""

import sys
from typing import Any

import requests

from app.config import get_settings


def _try(label: str, fn: Any) -> Any:
    """Ejecuta una consulta e imprime su resultado sin interrumpir el flujo."""
    try:
        result = fn()
        print(f"{label}: OK -> {result}")
        return result
    except Exception as exc:  # noqa: BLE001 - diagnóstico defensivo
        print(f"{label}: ERROR -> {exc}")
        return None


def main() -> None:
    settings = get_settings()
    token = settings.whatsapp_access_token
    phone_id = settings.whatsapp_phone_number_id
    base = f"https://graph.facebook.com/{settings.whatsapp_api_version}"

    if not token or not phone_id:
        print("ERROR: WHATSAPP_ACCESS_TOKEN o WHATSAPP_PHONE_NUMBER_ID vacíos en .env")
        sys.exit(1)

    headers = {"Authorization": f"Bearer {token}"}
    timeout = 20

    def get(path: str, params: dict | None = None) -> dict:
        r = requests.get(f"{base}{path}", headers=headers, params=params, timeout=timeout)
        if r.status_code != 200:
            error = r.json().get("error", {}).get("message", r.text[:200])
            raise RuntimeError(f"HTTP {r.status_code}: {error}")
        return r.json()

    # 1) Número de teléfono
    _try(
        "1) Número",
        lambda: get(
            f"/{phone_id}",
            {"fields": "display_phone_number,verified_name,quality_rating"},
        ),
    )

    # 2) Negocios accesibles con este token
    businesses = _try(
        "2) Negocios",
        lambda: get("/me/businesses", {"fields": "id,name"}).get("data", []),
    )
    if not businesses:
        print("   (no se pudo listar negocios; el token puede requerir permiso "
              "business_management sobre el Business)")
        return

    for business in businesses:
        print(f"   Business: {business.get('name')} ({business.get('id')})")

        # 3) WABAs del negocio
        wabas = _try(
            "   3) WABAs",
            lambda: get(
                f"/{business['id']}/owned_whatsapp_business_accounts",
                {"fields": "id,name,currency,timezone_id"},
            ).get("data", []),
        )
        if not wabas:
            print("   (sin WABAs propios o sin permiso whatsapp_business_management)")
            continue

        for waba in wabas:
            print(f"      WABA: {waba.get('name')} ({waba.get('id')})")

            # 4) Apps suscritas a los webhooks del WABA
            apps = _try(
                "         4) Apps suscritas al webhook",
                lambda: get(f"/{waba['id']}/subscribed_apps").get("data", []),
            )
            if apps:
                for app in apps:
                    print(f"            - app_id: {app.get('id')}")
            else:
                print("            - NINGUNA app suscrita -> los mensajes NO llegan!")


if __name__ == "__main__":
    main()
