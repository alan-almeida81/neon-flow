"""neon-flow CLI: `serve` the console, or `pair` with Maestri Wire."""
from __future__ import annotations

import argparse
from pathlib import Path


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="neon-flow", description="Console cyberpunk do fluxo de agentes do Maestri.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="inicia o console local")
    s.add_argument("--port", type=int, default=8770)
    s.add_argument("--snapshot", type=Path, help="JSON de feed do Maestri (em vez de ler o Wire ao vivo)")
    s.add_argument("--runtime", type=Path, help="JSON opcional com estado de runtime dos agentes")
    s.add_argument("--board", type=Path, help="JSON opcional com o quadro (listas, cards, runs)")
    p = sub.add_parser("pair", help="pareia com o Maestri Wire (Settings → Wire → Pairing)")
    p.add_argument("--host", required=True, help="endereço HTTPS do Maestri, ex.: https://meu-mac.local:7434")
    p.add_argument("--key", required=True, help="serverKeyHash mostrado no QR do Maestri")
    p.add_argument("--code", required=True, help="código de 6 dígitos")
    args = parser.parse_args(argv)
    if args.cmd == "pair":
        from .wire import pair
        result = pair(args.host, args.key, args.code)
        print(f"Pareado com {result['name']} (papel: {result['role']}).")
    else:
        from .server import FlowSource, serve
        serve(args.port, FlowSource(args.snapshot, args.runtime, args.board))


if __name__ == "__main__":
    main()
