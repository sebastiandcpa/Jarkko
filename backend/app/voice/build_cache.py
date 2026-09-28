"""Genera el caché de frases de JARKKO con su voz de identidad.

    python -m app.voice.build_cache            # solo las que falten
    python -m app.voice.build_cache --all      # regenera todas
    python -m app.voice.build_cache --dry-run  # solo informa del coste

Se ejecuta **una vez** (y cuando se añadan frases nuevas).  A partir de ahí el
audio sale del disco y no consume ni un crédito.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.config import get_settings
from app.voice.phrases import PHRASES, total_characters
from app.voice.service import get_voice_service


async def run(*, only_missing: bool, dry_run: bool) -> int:
    settings = get_settings()
    voice = get_voice_service()
    elevenlabs = voice.elevenlabs

    print(f"Catálogo: {len(PHRASES)} frases, {total_characters()} caracteres.")
    print(f"Voz de identidad: {settings.elevenlabs_voice_id} · modelo {settings.elevenlabs_model}")

    if elevenlabs is None or not elevenlabs.configured:
        print(
            "\n⚠ Falta la API key. Pon tu clave en backend/.env:\n"
            "    JARVIS_ELEVENLABS_API_KEY=tu_clave\n"
            "Mientras tanto, JARKKO habla con la voz local de Windows (gratis).",
            file=sys.stderr,
        )
        return 1

    check = await elevenlabs.voice_check()
    if not check.get("ok"):
        print(f"\n⚠ La voz no está disponible: {check}", file=sys.stderr)
        if check.get("hint"):
            print(f"  → {check['hint']}", file=sys.stderr)
        return 2
    print(f"Voz verificada en tu cuenta: {check.get('name')}")

    subscription = await elevenlabs.subscription()
    if subscription.get("available"):
        print(
            f"Cuota: {subscription['characters_used']}/{subscription['characters_limit']} usados "
            f"({subscription['characters_left']} disponibles) · plan {subscription.get('tier')}"
        )

    if dry_run:
        pending = [
            key
            for key, text in PHRASES.items()
            if not only_missing or voice.cache.get(elevenlabs.cache_key(text)) is None
        ]
        cost = sum(len(PHRASES[key]) for key in pending)
        print(f"\nSe generarían {len(pending)} frases · {cost} caracteres. Nada se ha gastado.")
        return 0

    report = await voice.build_phrase_cache(only_missing=only_missing)
    print(
        f"\nGeneradas {report['generated']} frases · {report['characters_spent']} caracteres gastados."
    )
    for item in report["phrases"]:
        if item["status"] == "failed":
            print(f"  ✗ {item['phrase']}: {item.get('error')}", file=sys.stderr)
    if report["failed"]:
        print(f"\n{report['failed']} frases fallaron.", file=sys.stderr)
        return 3
    print("Caché listo. JARKKO ya suena con su voz y a partir de ahora es gratis.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Construye el caché de voz de JARKKO.")
    parser.add_argument("--all", action="store_true", help="regenerar todas las frases")
    parser.add_argument("--dry-run", action="store_true", help="solo calcular el coste")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(only_missing=not args.all, dry_run=args.dry_run)))


if __name__ == "__main__":
    main()
