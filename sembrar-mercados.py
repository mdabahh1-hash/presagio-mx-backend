#!/usr/bin/env python
"""Sembrador declarativo de VEREDIKT: lee mercados-pendientes.yaml y siembra en la BD.

  ./venv/bin/python sembrar-mercados.py validar                  # solo esquema, sin BD
  ./venv/bin/python sembrar-mercados.py [sembrar] [--only ID …]  # dry-run contra la BD (default)
  ./venv/bin/python sembrar-mercados.py sembrar --apply          # escribe en UNA transacción
  ./venv/bin/python sembrar-mercados.py prune [--apply]          # lista / quita del YAML los terminados

Todos aceptan --archivo <ruta> (default: mercados-pendientes.yaml).

Contra prod:
  railway run --service Postgres -- bash -c 'DATABASE_URL="$DATABASE_PUBLIC_URL" \\
      ./venv/bin/python sembrar-mercados.py sembrar --apply'

Reglas que aplica el runner (no se desactivan): SKIP si el id ya existe; SKIP si
ends_at ya pasó (un mercado borrado por el cleanup de vencidos no debe resucitar).
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ARCHIVO = "mercados-pendientes.yaml"
SUBCOMANDOS = ("validar", "sembrar", "prune")


def _cargar(archivo: str):
    from seeds.schema import SchemaError, cargar

    try:
        specs, avisos = cargar(archivo)
    except FileNotFoundError:
        sys.exit(f"No existe {archivo}")
    except SchemaError as e:
        print(f"ERRORES en {archivo} ({len(e.errores)}):")
        for x in e.errores:
            print("  -", x)
        sys.exit(1)
    for a in avisos:
        print("  AVISO", a)
    if avisos:
        print()
    return specs


def cmd_validar(args) -> None:
    specs = _cargar(args.archivo)
    for s in specs:
        tipo = "partido" if s.origen == "partido" else s.tipo
        print(f"  OK  {s.id:<45} {tipo:<8} {s.category:<17} {s.subcategory or '-':<18} {s.ends_at:%Y-%m-%d %H:%M}Z")
    print(f"\nOK: {len(specs)} mercados válidos en {args.archivo}.")


async def cmd_sembrar(args) -> None:
    specs = _cargar(args.archivo)
    if args.only:
        pedidos = set(args.only)
        faltan = pedidos - {s.id for s in specs}
        if faltan:
            sys.exit(f"--only: estos ids no están en {args.archivo}: {', '.join(sorted(faltan))}")
        specs = [s for s in specs if s.id in pedidos]

    from app.database import AsyncSessionLocal, engine
    from seeds.runner import sembrar

    print(f"MODO: {'APPLY' if args.apply else 'DRY-RUN (agrega --apply para escribir)'}\n")
    async with AsyncSessionLocal() as db:
        r = await sembrar(specs, db, apply=args.apply)
    await engine.dispose()
    saltados = len(r.existentes) + len(r.vencidos)
    print(f"\nListo: {len(r.insertados)} insertados, {saltados} saltados "
          f"({len(r.existentes)} existentes, {len(r.vencidos)} vencidos), {len(specs)} en total.")
    if not args.apply:
        print("DRY-RUN: no se escribió nada.")


async def cmd_prune(args) -> None:
    specs = _cargar(args.archivo)

    from app.database import AsyncSessionLocal, engine
    from seeds.prune import clasificar, quitar_documentos

    async with AsyncSessionLocal() as db:
        veredictos = await clasificar(specs, db, datetime.now(timezone.utc))
    await engine.dispose()

    for v in veredictos:
        print(f"  {'QUITAR' if v.terminado else 'DEJAR ':6} {v.id:<45} {v.motivo}")
    quitar = {v.id for v in veredictos if v.terminado}
    print(f"\n{len(quitar)} terminados, {len(veredictos) - len(quitar)} se quedan.")
    if not args.apply:
        print("DRY-RUN: el archivo no cambió (agrega --apply para quitarlos).")
        return
    if not quitar:
        return
    with open(args.archivo, encoding="utf-8") as f:
        texto = f.read()
    with open(args.archivo, "w", encoding="utf-8") as f:
        f.write(quitar_documentos(texto, quitar))
    print(f"Escrito {args.archivo} sin {len(quitar)} documentos.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd")
    for nombre in SUBCOMANDOS:
        sp = sub.add_parser(nombre)
        sp.add_argument("--archivo", default=ARCHIVO)
        if nombre != "validar":
            sp.add_argument("--apply", action="store_true", help="escribir de verdad (default: dry-run)")
        if nombre == "sembrar":
            sp.add_argument("--only", nargs="+", metavar="ID", help="sembrar solo estos ids")
    argv = sys.argv[1:]
    if not argv or argv[0] not in SUBCOMANDOS and argv[0] not in ("-h", "--help"):
        argv = ["sembrar", *argv]  # sin subcomando = sembrar en dry-run
    args = parser.parse_args(argv)
    if args.cmd == "validar":
        cmd_validar(args)
    elif args.cmd == "sembrar":
        asyncio.run(cmd_sembrar(args))
    else:
        asyncio.run(cmd_prune(args))


if __name__ == "__main__":
    main()
