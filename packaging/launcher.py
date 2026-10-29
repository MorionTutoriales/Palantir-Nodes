"""Punto de entrada del ejecutable (PyInstaller necesita un script, no un paquete)."""

from palantir_nodes.app import main

if __name__ == "__main__":
    raise SystemExit(main())
