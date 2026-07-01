"""
Utilidades para el cálculo del árbol de Merkle.

El Merkle tree se construye de forma iterativa (bottom-up):

1. Se parte de la lista de hashes SHA-256 de los bloques del rango (hojas).
2. Si la cantidad de hojas es impar, el último hash se duplica para formar pares.
3. Cada par se concatena y se aplica SHA-256 para obtener el nodo padre.
4. El proceso se repite hasta que queda un solo hash: la raíz (Merkle root).

Casos especiales:
- Lista vacía  → SHA-256 de cadena vacía.
- Lista con 1 elemento → ese elemento es la raíz (sin ninguna operación adicional).
"""

import hashlib


def _sha256_pair(left: str, right: str) -> str:
    """Calcula SHA-256 de la concatenación directa de dos hashes hexadecimales."""
    combined = (left + right).encode("utf-8")
    return hashlib.sha256(combined).hexdigest()


def compute_merkle_root(block_hashes: list[str]) -> str:
    """
    Calcula el Merkle root a partir de una lista de hashes SHA-256.

    Parámetros:
        block_hashes: Lista de hashes hexadecimales de 64 caracteres,
                      correspondientes a los bloques del rango en orden ASC.

    Retorna:
        Un string hexadecimal de 64 caracteres con la raíz del árbol Merkle.

    Comportamiento:
        - Si ``block_hashes`` está vacío, retorna SHA-256 de cadena vacía.
        - Si contiene un único hash, lo retorna directamente.
        - Si la cantidad es impar en cualquier nivel del árbol, el último
          hash del nivel se duplica antes de combinar pares.

    Raises:
        TypeError: si algún elemento de ``block_hashes`` no es str.
    """
    if not block_hashes:
        return hashlib.sha256(b"").hexdigest()

    # Normalizamos a minúsculas para consistencia con el resto del sistema.
    current_level: list[str] = [h.lower() for h in block_hashes]

    if len(current_level) == 1:
        return current_level[0]

    while len(current_level) > 1:
        # Si la cantidad de nodos en el nivel actual es impar, duplicamos el último.
        if len(current_level) % 2 != 0:
            current_level.append(current_level[-1])

        next_level: list[str] = []
        for i in range(0, len(current_level), 2):
            parent = _sha256_pair(current_level[i], current_level[i + 1])
            next_level.append(parent)

        current_level = next_level

    return current_level[0]
