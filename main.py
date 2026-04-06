from pathlib import Path

from transformer_client.controller import LiveClientController
from transformer_client.ui import LiveClientApp


def main() -> None:
    workdir = Path.cwd()
    controller = LiveClientController(workdir)
    app = LiveClientApp(controller)
    app.run()


if __name__ == "__main__":
    main()
