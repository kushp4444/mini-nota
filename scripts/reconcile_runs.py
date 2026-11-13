"""One operator-triggered bounded reconciliation pass; never an idle keepalive."""
import asyncio
import os
from service.execution import ModalProvider, reconcile
from service.run_repository import RunRepository


def main():
    asyncio.run(reconcile(RunRepository(os.environ['RUN_DATABASE_URL']), ModalProvider()))
    print('Bounded reconciliation pass finished; consult authorized run state for outcomes.')


if __name__ == '__main__':
    main()
