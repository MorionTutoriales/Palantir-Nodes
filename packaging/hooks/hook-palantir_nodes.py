"""Gancho de PyInstaller para Palantir Nodes.

El exportador a Python copia al script el código fuente de sus propias funciones
(``inspect.getsource``): los módulos de la aplicación se incluyen, además de comprimidos, como
archivos ``.py``. Sin esto, la versión empaquetada fallaría al arrancar.
"""

module_collection_mode = "pyz+py"
