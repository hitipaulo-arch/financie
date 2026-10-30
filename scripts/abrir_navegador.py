#!/usr/bin/env python
"""Espera a porta responder e abre o navegador no endereço certo.

Os launchers (`run.sh` / `start_backend.bat`) chamam este script num processo à
parte, logo antes de subir o servidor. O motivo é de ordem prática: o `run.sh`
termina em `exec python backend.py`, que substitui o shell — não sobra nada para
abrir o navegador depois. E abrir antes dá "não foi possível conectar", porque o
socket ainda não está escutando.

Por que um arquivo e não um `-c` inline nos dois launchers: a espera precisa de
um laço, e laço não cabe num one-liner separado por `;`. Encaixar isso dentro de
um `start "" /min ...` do cmd.exe, com as aspas que o cmd reinterpreta, é o tipo
de coisa que funciona numa máquina e falha na outra.

Uso:
    python abrir_navegador.py PORTA [HOST] [TENTATIVAS]

  PORTA       porta local a esperar
  HOST        host usado na URL aberta (padrão `localhost`)
  TENTATIVAS  quantas sondagens de 0,5 s fazer (padrão 120, ~60 s)

Sai 0 se abriu, 1 se a porta nunca respondeu, 2 se chamado errado.
"""
from __future__ import annotations

import socket
import sys
import time
import webbrowser

# Endereços de bind, não de destino. `http://0.0.0.0:8000` até abre em alguns
# navegadores de Linux, mas no Windows não é um destino válido — e é justamente
# no Windows que o launcher passa `0.0.0.0` para abrir para a rede.
NAO_SAO_DESTINO = {"0.0.0.0", "::", "", "0"}


def porta_aberta(porta: int, timeout: float = 0.5) -> bool:
    """Sonda 127.0.0.1: funciona tanto com bind em loopback quanto em 0.0.0.0."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        return s.connect_ex(("127.0.0.1", porta)) == 0
    except OSError:
        return False
    finally:
        s.close()


def url_para(host: str, porta: int) -> str:
    if host in NAO_SAO_DESTINO:
        host = "localhost"
    return f"http://{host}:{porta}/"


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[-6], file=sys.stderr)
        return 2
    try:
        porta = int(argv[1])
    except ValueError:
        print(f"porta inválida: {argv[1]!r}", file=sys.stderr)
        return 2

    host = argv[2] if len(argv) > 2 and argv[2] else "localhost"
    tentativas = int(argv[3]) if len(argv) > 3 and argv[3].isdigit() else 120

    url = url_para(host, porta)
    for _ in range(max(1, tentativas)):
        if porta_aberta(porta):
            # webbrowser.open() devolve False quando não acha navegador, e não
            # levanta. Num servidor sem interface gráfica isto simplesmente não
            # abre nada — não é motivo para derrubar o launcher.
            webbrowser.open(url)
            return 0
        time.sleep(0.5)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
